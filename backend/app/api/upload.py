"""File upload and data append endpoints.

- POST /upload: Create a new report by uploading a baseline CSV/Excel/PDF
- POST /reports/{report_id}/append: Add new daily data to an existing report
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dateutil import parser as date_parser
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.report import Report
from app.models.data_point import DataPoint
from app.models.phone_number import PhoneNumber
from app.models.schemas import SUPPORTED_EXTENSIONS, MAX_ATTACHMENT_SIZE_MB
from app.services.report_parser import parse_report as do_parse
from app.services.trend_analyzer import analyze
from app.services.deviation_detector import detect
from app.services.whatsapp_notifier import send_deviation_notifications

router = APIRouter(prefix="/upload", tags=["upload"])

UPLOAD_DIR = "./uploads"
MAX_SIZE_BYTES = MAX_ATTACHMENT_SIZE_MB * 1024 * 1024


@router.post("")
async def create_report(
    file: UploadFile = File(...),
    report_name: str = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new report by uploading baseline/historical data (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can upload reports.")
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Accepted: .pdf, .xlsx, .xls, .csv",
        )

    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail=f"File exceeds {MAX_ATTACHMENT_SIZE_MB}MB limit.")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty.")

    # Save to disk
    upload_path = Path(UPLOAD_DIR)
    upload_path.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid.uuid4().hex}_{filename}"
    file_path = upload_path / stored_filename
    file_path.write_bytes(content)

    # Parse
    parse_result = do_parse(str(file_path), ext.lstrip("."))
    if not parse_result.success:
        return {"status": "parse_failed", "error": parse_result.error}

    # Create single report record
    final_name = report_name or Path(filename).stem
    report = Report(
        user_id=current_user.id,
        group_id=current_user.group_id,
        name=final_name,
        source_email=current_user.email,
        original_filename=filename,
        file_type=ext.lstrip("."),
        file_size_bytes=len(content),
        status="active",
        parsed_at=datetime.now(timezone.utc),
    )
    db.add(report)
    await db.flush()

    # Store each row as a data point with proper timestamps
    data_points_created = _store_data_points(db, report.id, parse_result.tables)
    await db.flush()

    return {
        "status": "success",
        "report_id": str(report.id),
        "report_name": final_name,
        "data_points_created": data_points_created,
        "tables_parsed": len(parse_result.tables),
        "message": f"Report '{final_name}' created with {data_points_created} historical data points. Use 'Add Data' to append daily entries.",
    }


@router.post("/reports/{report_id}/append")
async def append_data(
    report_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Append new daily data to an existing report and trigger analysis (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can upload reports.")
    # Verify report exists and belongs to user
    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.user_id == current_user.id)
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")

    # Parse the uploaded file
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext}'.")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty.")

    upload_path = Path(UPLOAD_DIR)
    upload_path.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid.uuid4().hex}_{filename}"
    file_path = upload_path / stored_filename
    file_path.write_bytes(content)

    parse_result = do_parse(str(file_path), ext.lstrip("."))
    if not parse_result.success:
        return {"status": "parse_failed", "error": parse_result.error}

    # Store new data points
    new_points_count = _store_data_points(db, report.id, parse_result.tables)
    await db.flush()

    # Run trend analysis
    trends = await analyze(db, str(report.id))

    # Run deviation detection
    deviations = await detect(db, str(report.id))

    # Send WhatsApp alerts for medium/high severity
    whatsapp_sent = 0
    notifiable = [d for d in deviations if d.get("severity") in ("medium", "high")]
    if notifiable:
        phone_result = await db.execute(
            select(PhoneNumber).where(
                PhoneNumber.user_id == current_user.id,
                PhoneNumber.status == "verified",
            )
        )
        verified_numbers = [pn.number for pn in phone_result.scalars().all()]

        if verified_numbers:
            for dev in notifiable:
                try:
                    notif_result = send_deviation_notifications(
                        deviation_id=str(dev["deviation_id"]),
                        report_name=report.name,
                        metric_name=dev["metric_name"],
                        severity=dev["severity"],
                        expected_value=dev["expected_value"],
                        actual_value=dev["actual_value"],
                        deviation_score=dev.get("deviation_score", 0.0),
                        verified_phone_numbers=verified_numbers,
                    )
                    whatsapp_sent += notif_result.recipients_succeeded
                except Exception as e:
                    import structlog
                    structlog.get_logger().error("whatsapp_notification_error", error=str(e), metric=dev["metric_name"])

    await db.flush()

    return {
        "status": "success",
        "report_id": str(report.id),
        "report_name": report.name,
        "new_data_points": new_points_count,
        "trends_computed": len(trends),
        "deviations_found": len(deviations),
        "deviations": deviations,
        "whatsapp_alerts_sent": whatsapp_sent,
    }


@router.post("/test-whatsapp")
async def test_whatsapp(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a test WhatsApp message to verify the API connection."""
    from app.services.whatsapp_notifier import send_with_retry, format_message

    test_message = format_message(
        report_name="Daily Operations",
        metric_name="Create Customer",
        severity="medium",
        expected_value=50.0,
        actual_value=12.0,
        deviation_score=3.1,
    )

    phone_result = await db.execute(
        select(PhoneNumber).where(
            PhoneNumber.user_id == current_user.id,
            PhoneNumber.status == "verified",
        )
    )
    verified_numbers = [pn.number for pn in phone_result.scalars().all()]

    if not verified_numbers:
        return {
            "status": "no_recipients",
            "message": "No verified phone numbers. Go to Settings and add your WhatsApp number first.",
        }

    results = []
    for number in verified_numbers:
        success, error = send_with_retry(number, test_message, max_retries=1)
        results.append({"number": number[-4:], "success": success, "error": error})

    return {
        "status": "sent" if any(r["success"] for r in results) else "failed",
        "results": results,
        "message_preview": test_message[:200],
    }


# --- Helpers ---


def _store_data_points(db, report_id, tables) -> int:
    """Store parsed table rows as data points with proper timestamps."""
    now = datetime.now(timezone.utc)
    count = 0

    for table in tables:
        # Find date column
        date_col_idx = None
        for idx, h in enumerate(table.headers):
            if h.lower().strip() in ('date', 'time', 'datetime', 'timestamp', 'month', 'period'):
                date_col_idx = idx
                break

        for row in table.rows:
            # Determine timestamp
            row_timestamp = now
            if date_col_idx is not None and date_col_idx < len(row):
                try:
                    row_timestamp = date_parser.parse(str(row[date_col_idx]))
                    if row_timestamp.tzinfo is None:
                        row_timestamp = row_timestamp.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    row_timestamp = now

            for col_idx, value in enumerate(row):
                if col_idx == date_col_idx:
                    continue
                numeric_value = _try_parse_numeric(value)
                if numeric_value is not None:
                    metric_name = table.headers[col_idx] if col_idx < len(table.headers) else f"col_{col_idx}"
                    dp = DataPoint(
                        report_id=report_id,
                        metric_name=metric_name,
                        value=numeric_value,
                        data_timestamp=row_timestamp,
                    )
                    db.add(dp)
                    count += 1

    return count


def _try_parse_numeric(value) -> float | None:
    """Try to parse a value as a float."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, str):
            cleaned = value.strip().replace(",", "").replace(" ", "")
            if cleaned.endswith("%"):
                return float(cleaned[:-1])
            return float(cleaned)
        return float(value)
    except (ValueError, TypeError):
        return None


@router.post("/check-email")
async def check_email(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger email poll and process any report attachments (admin only).

    Supports both IMAP (Gmail) and Microsoft Graph API (Outlook/M365).
    Set EMAIL_PROVIDER=outlook_graph in .env for Microsoft Graph.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can check email.")

    from dotenv import load_dotenv
    load_dotenv()

    email_provider = os.environ.get("EMAIL_PROVIDER", "imap")

    if email_provider == "outlook_graph":
        return await _check_email_graph(current_user, db)
    else:
        return await _check_email_imap(current_user, db)


async def _check_email_graph(current_user: User, db: AsyncSession):
    """Process emails via Microsoft Graph API."""
    from app.services.outlook_graph import is_configured, poll_mailbox, get_attachments, mark_as_read, save_attachment
    from app.services.report_parser import parse_report as do_parse
    from app.services.trend_analyzer import analyze
    from app.services.deviation_detector import detect
    from app.models.data_point import DataPoint
    from dateutil import parser as date_parser

    if not is_configured():
        return {
            "status": "error",
            "message": "Microsoft Graph API not configured. Set GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, and GRAPH_MAILBOX in .env",
        }

    # Poll mailbox
    try:
        emails = poll_mailbox()
    except Exception as e:
        return {"status": "error", "message": f"Failed to connect to Outlook: {e}"}

    if not emails:
        return {"status": "success", "message": "No new emails with attachments found.", "emails_processed": 0}

    # Process each email
    reports_created = []
    emails_processed = []

    for email_msg in emails:
        sender = email_msg["sender"]

        # Validate sender against registered users
        user_result = await db.execute(select(User).where(User.email == sender))
        sender_user = user_result.scalar_one_or_none()

        if sender_user is None:
            emails_processed.append({
                "sender": sender,
                "subject": email_msg["subject"],
                "success": False,
                "error": "Sender not a registered user.",
            })
            mark_as_read(email_msg["id"])
            continue

        # Get attachments
        attachments = get_attachments(email_msg["id"])
        if not attachments:
            emails_processed.append({
                "sender": sender,
                "subject": email_msg["subject"],
                "success": False,
                "error": "No valid attachments found.",
            })
            mark_as_read(email_msg["id"])
            continue

        # Process each attachment
        for att in attachments:
            filename = att["filename"]
            ext = Path(filename).suffix.lower().lstrip(".")
            
            # Match to existing report or create new
            from app.services.report_matcher import match_email_to_report
            match = await match_email_to_report(
                db=db,
                subject=email_msg["subject"],
                filename=filename,
                sender=sender,
                user_id=str(sender_user.id),
                group_id=str(sender_user.group_id) if sender_user.group_id else None,
            )

            if match:
                report_name = match["report_name"]
                match_type = match["match_type"]
            else:
                report_name = Path(filename).stem
                match_type = "new"

            # Save to disk
            file_path = save_attachment(filename, att["content"])

            # Check if report already exists (append) or create new
            existing_report = None
            if match:
                existing_stmt = select(Report).where(Report.name == report_name)
                if sender_user.group_id:
                    existing_stmt = existing_stmt.where(Report.group_id == sender_user.group_id)
                else:
                    existing_stmt = existing_stmt.where(Report.user_id == sender_user.id)
                existing_result = await db.execute(existing_stmt)
                existing_report = existing_result.scalar_one_or_none()

            if existing_report:
                report = existing_report
            else:
                # Create new report record
                report = Report(
                    user_id=sender_user.id,
                    group_id=sender_user.group_id,
                    name=report_name,
                    source_email=sender,
                    original_filename=filename,
                    file_type=ext,
                    file_size_bytes=att["size"],
                    status="received",
                )
                db.add(report)
                await db.flush()

            # Parse
            parse_result = do_parse(file_path, ext)
            if not parse_result.success:
                report.status = "parse_failed"
                await db.flush()
                continue

            # Store data points
            now = datetime.now(timezone.utc)
            data_points_created = _store_data_points(db, report.id, parse_result.tables)
            report.status = "active"
            report.parsed_at = now
            await db.flush()

            # Trend + Deviation analysis
            trends = await analyze(db, str(report.id))
            deviations = await detect(db, str(report.id))

            # WhatsApp notifications
            whatsapp_sent = 0
            notifiable = [d for d in deviations if d.get("severity") in ("medium", "high")]
            if notifiable:
                phone_result = await db.execute(
                    select(PhoneNumber).where(
                        PhoneNumber.user_id == sender_user.id,
                        PhoneNumber.status == "verified",
                    )
                )
                verified_numbers = [pn.number for pn in phone_result.scalars().all()]
                if verified_numbers:
                    for dev in notifiable:
                        try:
                            notif_result = send_deviation_notifications(
                                deviation_id=str(dev["deviation_id"]),
                                report_name=report.name,
                                metric_name=dev["metric_name"],
                                severity=dev["severity"],
                                expected_value=dev["expected_value"],
                                actual_value=dev["actual_value"],
                                deviation_score=dev.get("deviation_score", 0.0),
                                verified_phone_numbers=verified_numbers,
                            )
                            whatsapp_sent += notif_result.recipients_succeeded
                        except Exception:
                            pass

            reports_created.append({
                "name": report.name,
                "file_type": ext,
                "sender": sender,
                "match_type": match_type,
                "data_points": data_points_created,
                "trends": len(trends),
                "deviations": len(deviations),
                "whatsapp_sent": whatsapp_sent,
            })

        # Mark email as read
        mark_as_read(email_msg["id"])
        emails_processed.append({
            "sender": sender,
            "subject": email_msg["subject"],
            "success": True,
            "attachments": len(attachments),
        })

    await db.flush()

    return {
        "status": "success",
        "provider": "Microsoft Graph (Outlook)",
        "emails_found": len(emails),
        "emails_processed": emails_processed,
        "reports_created": reports_created,
    }


async def _check_email_imap(current_user: User, db: AsyncSession):
    """Process emails via IMAP (Gmail or other)."""
    from app.services.email_ingestion import poll_mailbox, _extract_attachments, _extract_sender, _find_user_by_email, _save_attachment, filter_attachments
    from app.services.report_matcher import match_email_to_report
    from app.services.report_parser import parse_report as do_parse
    from app.services.trend_analyzer import analyze
    from app.services.deviation_detector import detect
    from app.models.data_point import DataPoint
    from dateutil import parser as date_parser

    # Check if IMAP is configured
    from dotenv import load_dotenv
    load_dotenv(override=True)
    imap_user = os.environ.get("IMAP_USERNAME", "")
    if not imap_user:
        return {"status": "error", "message": "IMAP not configured. Set IMAP_USERNAME and IMAP_PASSWORD in .env"}

    # Poll mailbox
    try:
        emails = poll_mailbox()
    except Exception as e:
        return {"status": "error", "message": f"Failed to connect to mailbox: {e}"}

    if not emails:
        return {"status": "success", "message": "No new emails found.", "emails_processed": 0}

    # Process each email with report matching
    emails_processed = []
    reports_created = []

    for msg_data in emails:
        sender = msg_data["sender"]
        subject = msg_data["subject"]
        msg = msg_data["message"]

        # Validate sender
        sender_user = await _find_user_by_email(db, sender)
        if sender_user is None:
            emails_processed.append({"sender": sender, "subject": subject, "success": False, "error": "Sender not registered."})
            continue

        # Extract attachments
        from app.services.email_ingestion import _extract_attachments as extract_atts
        attachments = extract_atts(msg)
        valid, skipped = filter_attachments(attachments)

        if not valid:
            emails_processed.append({"sender": sender, "subject": subject, "success": False, "error": "No valid attachments."})
            continue

        for att in valid:
            filename = att["filename"]
            content = att["content"]
            ext = Path(filename).suffix.lower().lstrip(".")

            # Match to existing report
            match = await match_email_to_report(
                db=db,
                subject=subject,
                filename=filename,
                sender=sender,
                user_id=str(sender_user.id),
                group_id=str(sender_user.group_id) if sender_user.group_id else None,
            )

            if match:
                report_name = match["report_name"]
                match_type = match["match_type"]
            else:
                report_name = Path(filename).stem
                match_type = "new"

            # Save file
            upload_path = Path(UPLOAD_DIR)
            upload_path.mkdir(parents=True, exist_ok=True)
            stored_filename = f"{uuid.uuid4().hex}_{filename}"
            file_path = upload_path / stored_filename
            file_path.write_bytes(content)

            # Find existing report or create new
            existing_report = None
            if match:
                existing_stmt = select(Report).where(Report.name == report_name)
                if sender_user.group_id:
                    existing_stmt = existing_stmt.where(Report.group_id == sender_user.group_id)
                else:
                    existing_stmt = existing_stmt.where(Report.user_id == sender_user.id)
                existing_result = await db.execute(existing_stmt)
                existing_report = existing_result.scalar_one_or_none()

            if existing_report:
                report = existing_report
            else:
                report = Report(
                    user_id=sender_user.id,
                    group_id=sender_user.group_id,
                    name=report_name,
                    source_email=sender,
                    original_filename=filename,
                    file_type=ext,
                    file_size_bytes=len(content),
                    status="received",
                )
                db.add(report)
                await db.flush()

            # Parse and store data
            parse_result = do_parse(str(file_path), ext)
            if not parse_result.success:
                if not existing_report:
                    report.status = "parse_failed"
                continue

            now = datetime.now(timezone.utc)
            data_points_created = _store_data_points(db, report.id, parse_result.tables)
            report.status = "active"
            report.parsed_at = now
            await db.flush()

            # Trend + Deviation analysis
            trends = await analyze(db, str(report.id))
            deviations = await detect(db, str(report.id))

            # WhatsApp alerts
            whatsapp_sent = 0
            notifiable = [d for d in deviations if d.get("severity") in ("medium", "high")]
            if notifiable:
                phone_result = await db.execute(
                    select(PhoneNumber).where(
                        PhoneNumber.user_id == sender_user.id,
                        PhoneNumber.status == "verified",
                    )
                )
                verified_numbers = [pn.number for pn in phone_result.scalars().all()]
                if verified_numbers:
                    for dev in notifiable:
                        try:
                            notif_result = send_deviation_notifications(
                                deviation_id=str(dev["deviation_id"]),
                                report_name=report.name,
                                metric_name=dev["metric_name"],
                                severity=dev["severity"],
                                expected_value=dev["expected_value"],
                                actual_value=dev["actual_value"],
                                deviation_score=dev.get("deviation_score", 0.0),
                                verified_phone_numbers=verified_numbers,
                            )
                            whatsapp_sent += notif_result.recipients_succeeded
                        except Exception:
                            pass

            reports_created.append({
                "name": report.name,
                "file_type": ext,
                "match_type": match_type,
                "data_points": data_points_created,
                "trends": len(trends),
                "deviations": len(deviations),
                "whatsapp_sent": whatsapp_sent,
            })

        emails_processed.append({"sender": sender, "subject": subject, "success": True, "attachments": len(valid)})

    await db.flush()

    return {
        "status": "success",
        "provider": "IMAP (Gmail)",
        "emails_found": len(emails),
        "emails_processed": emails_processed,
        "reports_created": reports_created,
    }
