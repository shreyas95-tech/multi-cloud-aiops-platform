"""Microsoft Graph API email ingestion service.

Reads emails from Outlook/M365 mailboxes using the Microsoft Graph API
with app-only authentication (client credentials flow). No user login needed.

Setup:
1. Register an app in Azure AD (portal.azure.com → App registrations)
2. Add API permission: Microsoft Graph → Application → Mail.Read
3. Grant admin consent
4. Create a client secret
5. Set GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_MAILBOX in .env
"""

import base64
import os
import uuid
from pathlib import Path
from typing import Optional

import httpx
import structlog
from dotenv import load_dotenv

load_dotenv()

logger = structlog.get_logger(__name__)

# --- Configuration ---

GRAPH_TENANT_ID = os.environ.get("GRAPH_TENANT_ID", "")
GRAPH_CLIENT_ID = os.environ.get("GRAPH_CLIENT_ID", "")
GRAPH_CLIENT_SECRET = os.environ.get("GRAPH_CLIENT_SECRET", "")
GRAPH_MAILBOX = os.environ.get("GRAPH_MAILBOX", "")  # e.g., reports@company.com
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "./uploads")
SUPPORTED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv"}
MAX_ATTACHMENT_SIZE_MB = 25
MAX_ATTACHMENT_SIZE_BYTES = MAX_ATTACHMENT_SIZE_MB * 1024 * 1024


# --- Token Management ---


_access_token: Optional[str] = None
_token_expiry: float = 0


def _get_access_token() -> str:
    """Get an access token using client credentials flow (app-only auth)."""
    global _access_token, _token_expiry
    import time

    # Return cached token if still valid
    if _access_token and time.time() < _token_expiry - 60:
        return _access_token

    token_url = f"https://login.microsoftonline.com/{GRAPH_TENANT_ID}/oauth2/v2.0/token"
    payload = {
        "client_id": GRAPH_CLIENT_ID,
        "client_secret": GRAPH_CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }

    with httpx.Client(timeout=15.0) as client:
        response = client.post(token_url, data=payload)

    if response.status_code != 200:
        error = response.text[:500]
        logger.error("graph_token_failed", status=response.status_code, error=error)
        raise Exception(f"Failed to get Graph API token: {error}")

    data = response.json()
    _access_token = data["access_token"]
    _token_expiry = time.time() + data.get("expires_in", 3600)

    logger.info("graph_token_acquired", expires_in=data.get("expires_in"))
    return _access_token


def _graph_headers() -> dict:
    """Get authorization headers for Graph API requests."""
    token = _get_access_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


# --- Email Operations ---


def is_configured() -> bool:
    """Check if Microsoft Graph API is configured."""
    return all([GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_MAILBOX])


def poll_mailbox() -> list[dict]:
    """Fetch unread emails with attachments from the configured mailbox.

    Returns:
        List of dicts with: id, sender, subject, received_at, attachments.
    """
    if not is_configured():
        logger.warning("graph_not_configured")
        return []

    log = logger.bind(operation="graph_poll_mailbox", mailbox=GRAPH_MAILBOX)

    # Fetch unread messages that have attachments
    url = (
        f"{GRAPH_BASE_URL}/users/{GRAPH_MAILBOX}/messages"
        f"?$filter=isRead eq false and hasAttachments eq true"
        f"&$select=id,from,subject,receivedDateTime"
        f"&$orderby=receivedDateTime desc"
        f"&$top=20"
    )

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=_graph_headers())

        if response.status_code != 200:
            log.error("graph_fetch_failed", status=response.status_code, body=response.text[:300])
            return []

        messages = response.json().get("value", [])
        log.info("graph_emails_fetched", count=len(messages))

        results = []
        for msg in messages:
            sender_email = msg.get("from", {}).get("emailAddress", {}).get("address", "").lower()
            results.append({
                "id": msg["id"],
                "sender": sender_email,
                "subject": msg.get("subject", "(no subject)"),
                "received_at": msg.get("receivedDateTime", ""),
            })

        return results

    except Exception as e:
        log.error("graph_poll_error", error=str(e))
        return []


def get_attachments(message_id: str) -> list[dict]:
    """Download attachments for a specific email message.

    Returns:
        List of dicts with: filename, content (bytes), content_type, size.
    """
    url = f"{GRAPH_BASE_URL}/users/{GRAPH_MAILBOX}/messages/{message_id}/attachments"

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(url, headers=_graph_headers())

        if response.status_code != 200:
            logger.error("graph_attachments_failed", message_id=message_id, status=response.status_code)
            return []

        attachments = response.json().get("value", [])
        results = []

        for att in attachments:
            # Only process file attachments (skip inline images, etc.)
            if att.get("@odata.type") != "#microsoft.graph.fileAttachment":
                continue

            filename = att.get("name", "unknown")
            ext = Path(filename).suffix.lower()

            # Filter by supported extensions
            if ext not in SUPPORTED_EXTENSIONS:
                logger.info("graph_attachment_skipped_format", filename=filename, ext=ext)
                continue

            # Decode content (base64)
            content_bytes = base64.b64decode(att.get("contentBytes", ""))

            # Check size
            if len(content_bytes) > MAX_ATTACHMENT_SIZE_BYTES:
                logger.warning("graph_attachment_too_large", filename=filename, size_mb=len(content_bytes) / (1024*1024))
                continue

            results.append({
                "filename": filename,
                "content": content_bytes,
                "content_type": att.get("contentType", ""),
                "size": len(content_bytes),
            })

        return results

    except Exception as e:
        logger.error("graph_get_attachments_error", error=str(e), message_id=message_id)
        return []


def mark_as_read(message_id: str) -> bool:
    """Mark an email as read after processing."""
    url = f"{GRAPH_BASE_URL}/users/{GRAPH_MAILBOX}/messages/{message_id}"
    payload = {"isRead": True}

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.patch(url, json=payload, headers=_graph_headers())
        return response.status_code == 200
    except Exception:
        return False


def save_attachment(filename: str, content: bytes) -> str:
    """Save attachment content to disk.

    Returns:
        The file path where the attachment was saved.
    """
    upload_path = Path(UPLOAD_DIR)
    upload_path.mkdir(parents=True, exist_ok=True)

    stored_filename = f"{uuid.uuid4().hex}_{filename}"
    file_path = upload_path / stored_filename
    file_path.write_bytes(content)

    return str(file_path)
