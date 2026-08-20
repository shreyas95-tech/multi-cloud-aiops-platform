"""Email ingestion service: IMAP polling, attachment extraction, and user association.

Connects to an IMAP mailbox, fetches unread emails, validates senders against
registered users, filters attachments by type/size, and queues valid attachments
for parsing.
"""

import email
import os
import uuid
from email.message import Message
from pathlib import Path
from typing import Optional

import structlog
from imapclient import IMAPClient
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import SUPPORTED_EXTENSIONS, MAX_ATTACHMENT_SIZE_MB, IngestionResult
from app.models.user import User
from app.models.report import Report

logger = structlog.get_logger(__name__)

# Maximum attachment size in bytes
MAX_ATTACHMENT_SIZE_BYTES = MAX_ATTACHMENT_SIZE_MB * 1024 * 1024
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "./uploads")


def _get_imap_config():
    """Load IMAP config fresh from .env each time."""
    load_dotenv(override=True)
    return {
        "host": os.environ.get("IMAP_HOST", "imap.gmail.com"),
        "port": int(os.environ.get("IMAP_PORT", "993")),
        "username": os.environ.get("IMAP_USERNAME", ""),
        "password": os.environ.get("IMAP_PASSWORD", ""),
        "use_ssl": os.environ.get("IMAP_USE_SSL", "true").lower() == "true",
    }


def _get_imap_connection() -> IMAPClient:
    """Create and return an authenticated IMAP connection."""
    config = _get_imap_config()
    client = IMAPClient(config["host"], port=config["port"], ssl=config["use_ssl"])
    client.login(config["username"], config["password"])
    return client


def poll_mailbox() -> list[dict]:
    """Poll the IMAP mailbox for unread emails.

    Returns:
        List of dicts with keys: uid, sender, subject, message (email.message.Message).
    """
    log = logger.bind(operation="poll_mailbox")
    emails = []

    try:
        client = _get_imap_connection()
        client.select_folder("INBOX")

        # Search for unseen (unread) messages
        uids = client.search(["UNSEEN"])
        log.info("fetched_unread_emails", count=len(uids))

        if not uids:
            client.logout()
            return emails

        # Fetch message data
        messages = client.fetch(uids, ["RFC822", "ENVELOPE"])

        for uid, data in messages.items():
            raw_email = data[b"RFC822"]
            msg = email.message_from_bytes(raw_email)
            envelope = data[b"ENVELOPE"]

            # Extract sender email
            sender_address = _extract_sender(msg, envelope)
            subject = msg.get("Subject", "(no subject)")

            emails.append({
                "uid": uid,
                "sender": sender_address,
                "subject": subject,
                "message": msg,
            })

        # Mark as seen
        client.add_flags(uids, [b"\\Seen"])
        client.logout()

    except Exception as e:
        log.error("imap_poll_failed", error=str(e))
        raise

    return emails


def _extract_sender(msg: Message, envelope) -> str:
    """Extract sender email address from message or envelope."""
    # Try envelope first
    if envelope and envelope.from_:
        addr = envelope.from_[0]
        if addr.mailbox and addr.host:
            mailbox = addr.mailbox.decode() if isinstance(addr.mailbox, bytes) else addr.mailbox
            host = addr.host.decode() if isinstance(addr.host, bytes) else addr.host
            return f"{mailbox}@{host}".lower()

    # Fallback to From header
    from_header = msg.get("From", "")
    if "<" in from_header and ">" in from_header:
        return from_header.split("<")[1].split(">")[0].lower()
    return from_header.lower().strip()


async def process_email(
    msg_data: dict,
    db: AsyncSession,
    correlation_id: str,
) -> IngestionResult:
    """Process a single email: validate sender and extract valid attachments.

    Args:
        msg_data: Dict with uid, sender, subject, message.
        db: Async database session.
        correlation_id: Correlation ID for log tracing.

    Returns:
        IngestionResult with extraction details.
    """
    log = logger.bind(
        operation="process_email",
        correlation_id=correlation_id,
        sender=msg_data["sender"],
        subject=msg_data["subject"],
    )

    sender = msg_data["sender"]
    msg: Message = msg_data["message"]

    # Validate sender against registered users (Req 1.4, 1.5)
    user = await _find_user_by_email(db, sender)
    if user is None:
        log.warning("unregistered_sender_discarded", sender=sender)
        return IngestionResult(
            email_id=str(msg_data["uid"]),
            sender=sender,
            success=False,
            error="Sender email does not match any registered user.",
        )

    # Check if email has attachments (Req 1.3)
    attachments = _extract_attachments(msg)
    if not attachments:
        log.info("email_no_attachments_discarded", sender=sender)
        return IngestionResult(
            email_id=str(msg_data["uid"]),
            sender=sender,
            success=False,
            error="Email contains no attachments.",
        )

    # Filter attachments by type and size (Req 1.1, 1.2, 1.6)
    valid_attachments = []
    skipped_count = 0

    for att in attachments:
        filename = att["filename"]
        content = att["content"]
        ext = Path(filename).suffix.lower()

        if ext not in SUPPORTED_EXTENSIONS:
            log.info("attachment_unsupported_format", filename=filename, extension=ext)
            skipped_count += 1
            continue

        if len(content) > MAX_ATTACHMENT_SIZE_BYTES:
            log.warning(
                "attachment_exceeds_size_limit",
                filename=filename,
                size_mb=round(len(content) / (1024 * 1024), 2),
                limit_mb=MAX_ATTACHMENT_SIZE_MB,
            )
            skipped_count += 1
            continue

        valid_attachments.append(att)

    if not valid_attachments:
        log.info("no_valid_attachments", sender=sender, skipped=skipped_count)
        return IngestionResult(
            email_id=str(msg_data["uid"]),
            sender=sender,
            attachments_skipped=skipped_count,
            success=False,
            error="No valid attachments found after filtering.",
        )

    # Save valid attachments and create report records
    report_ids = []
    for att in valid_attachments:
        report_id = await _save_attachment(db, user, att, sender, correlation_id)
        report_ids.append(report_id)

    log.info(
        "email_processed_successfully",
        sender=sender,
        extracted=len(valid_attachments),
        skipped=skipped_count,
        report_ids=[str(rid) for rid in report_ids],
    )

    return IngestionResult(
        email_id=str(msg_data["uid"]),
        sender=sender,
        attachments_extracted=len(valid_attachments),
        attachments_skipped=skipped_count,
        success=True,
    )


def _extract_attachments(msg: Message) -> list[dict]:
    """Extract all attachments from an email message.

    Returns:
        List of dicts with keys: filename, content (bytes), content_type.
    """
    attachments = []

    for part in msg.walk():
        content_disposition = part.get("Content-Disposition", "")
        if "attachment" not in content_disposition:
            continue

        filename = part.get_filename()
        if not filename:
            continue

        content = part.get_payload(decode=True)
        if content is None:
            continue

        attachments.append({
            "filename": filename,
            "content": content,
            "content_type": part.get_content_type(),
        })

    return attachments


def filter_attachments(attachments: list[dict]) -> tuple[list[dict], list[dict]]:
    """Filter attachments by supported extension and size limit.

    Public utility for testing.

    Args:
        attachments: List of dicts with filename and content.

    Returns:
        Tuple of (valid_attachments, skipped_attachments).
    """
    valid = []
    skipped = []

    for att in attachments:
        filename = att.get("filename", "")
        content = att.get("content", b"")
        ext = Path(filename).suffix.lower()

        if ext not in SUPPORTED_EXTENSIONS:
            skipped.append(att)
        elif len(content) > MAX_ATTACHMENT_SIZE_BYTES:
            skipped.append(att)
        else:
            valid.append(att)

    return valid, skipped


async def _find_user_by_email(db: AsyncSession, sender_email: str) -> Optional[User]:
    """Look up a registered user by their email address."""
    result = await db.execute(
        select(User).where(User.email == sender_email.lower())
    )
    return result.scalar_one_or_none()


async def _save_attachment(
    db: AsyncSession,
    user: User,
    attachment: dict,
    sender_email: str,
    correlation_id: str,
) -> uuid.UUID:
    """Save attachment to disk and create a Report record in the database.

    Returns:
        The report ID (UUID).
    """
    filename = attachment["filename"]
    content = attachment["content"]
    ext = Path(filename).suffix.lower()

    # Ensure upload directory exists
    upload_path = Path(UPLOAD_DIR)
    upload_path.mkdir(parents=True, exist_ok=True)

    # Generate unique filename to avoid collisions
    stored_filename = f"{uuid.uuid4().hex}_{filename}"
    file_path = upload_path / stored_filename

    # Write file to disk
    file_path.write_bytes(content)

    # Derive report name from filename (without extension)
    report_name = Path(filename).stem

    # Create Report record
    report = Report(
        user_id=user.id,
        name=report_name,
        source_email=sender_email,
        original_filename=filename,
        file_type=ext.lstrip("."),
        file_size_bytes=len(content),
        status="received",
    )
    db.add(report)
    await db.flush()

    logger.info(
        "attachment_saved",
        correlation_id=correlation_id,
        report_id=str(report.id),
        filename=filename,
        stored_as=stored_filename,
        size_bytes=len(content),
    )

    return report.id
