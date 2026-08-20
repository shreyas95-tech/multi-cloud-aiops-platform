"""Background scheduler for automatic email polling.

Uses APScheduler to poll the configured email inbox at regular intervals.
Works in-process (no separate service needed) and runs in production.

Set EMAIL_POLL_ENABLED=true and EMAIL_POLL_INTERVAL_MINUTES in .env to activate.
"""

import os
import asyncio

import structlog
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()

logger = structlog.get_logger(__name__)

POLL_ENABLED = os.environ.get("EMAIL_POLL_ENABLED", "false").lower() == "true"
POLL_INTERVAL_MINUTES = int(os.environ.get("EMAIL_POLL_INTERVAL_MINUTES", "5"))

_scheduler: BackgroundScheduler | None = None


def _run_email_poll():
    """Background job: poll email and process reports."""
    log = logger.bind(operation="scheduled_email_poll")
    log.info("email_poll_triggered")

    try:
        asyncio.run(_async_poll())
    except Exception as e:
        log.error("email_poll_failed", error=str(e))


async def _async_poll():
    """Async email poll logic — same as the check-email endpoint."""
    from app.database import async_session
    from app.services.report_parser import parse_report as do_parse
    from app.services.trend_analyzer import analyze
    from app.services.deviation_detector import detect
    from app.models.report import Report
    from app.models.data_point import DataPoint
    from app.models.user import User
    from app.models.phone_number import PhoneNumber
    from app.services.whatsapp_notifier import send_deviation_notifications
    from sqlalchemy import select
    from datetime import datetime, timezone
    from pathlib import Path
    from dateutil import parser as date_parser

    email_provider = os.environ.get("EMAIL_PROVIDER", "imap")

    if email_provider == "outlook_graph":
        from app.services.outlook_graph import is_configured, poll_mailbox, get_attachments, mark_as_read, save_attachment

        if not is_configured():
            return

        emails = poll_mailbox()
        if not emails:
            return

        async with async_session() as db:
            for email_msg in emails:
                sender = email_msg["sender"]
                user_result = await db.execute(select(User).where(User.email == sender))
                sender_user = user_result.scalar_one_or_none()

                if sender_user is None:
                    mark_as_read(email_msg["id"])
                    continue

                attachments = get_attachments(email_msg["id"])
                for att in attachments:
                    filename = att["filename"]
                    ext = Path(filename).suffix.lower().lstrip(".")
                    report_name = Path(filename).stem
                    file_path = save_attachment(filename, att["content"])

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

                    parse_result = do_parse(file_path, ext)
                    if not parse_result.success:
                        report.status = "parse_failed"
                        await db.flush()
                        continue

                    # Store data points
                    now = datetime.now(timezone.utc)
                    for table in parse_result.tables:
                        date_col_idx = None
                        for idx, h in enumerate(table.headers):
                            if h.lower().strip() in ('date', 'time', 'datetime', 'timestamp', 'month', 'period'):
                                date_col_idx = idx
                                break
                        for row in table.rows:
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
                                try:
                                    num = float(str(value).strip().replace(",", ""))
                                    dp = DataPoint(report_id=report.id, metric_name=table.headers[col_idx], value=num, data_timestamp=row_timestamp)
                                    db.add(dp)
                                except (ValueError, TypeError):
                                    pass

                    report.status = "active"
                    report.parsed_at = now
                    await db.flush()

                    # Analysis
                    trends = await analyze(db, str(report.id))
                    deviations = await detect(db, str(report.id))

                    # WhatsApp alerts
                    notifiable = [d for d in deviations if d.get("severity") in ("medium", "high")]
                    if notifiable:
                        phone_result = await db.execute(
                            select(PhoneNumber).where(PhoneNumber.user_id == sender_user.id, PhoneNumber.status == "verified")
                        )
                        verified_numbers = [pn.number for pn in phone_result.scalars().all()]
                        if verified_numbers:
                            for dev in notifiable:
                                try:
                                    send_deviation_notifications(
                                        deviation_id=str(dev["deviation_id"]),
                                        report_name=report.name,
                                        metric_name=dev["metric_name"],
                                        severity=dev["severity"],
                                        expected_value=dev["expected_value"],
                                        actual_value=dev["actual_value"],
                                        deviation_score=dev.get("deviation_score", 0.0),
                                        verified_phone_numbers=verified_numbers,
                                    )
                                except Exception:
                                    pass

                mark_as_read(email_msg["id"])

            await db.commit()

    else:
        # IMAP flow
        from app.services.email_ingestion import poll_mailbox as imap_poll, process_email

        try:
            emails = imap_poll()
        except Exception:
            return

        if not emails:
            return

        async with async_session() as db:
            for msg_data in emails:
                await process_email(msg_data, db, str(os.urandom(8).hex()))
            await db.commit()

    logger.info("scheduled_email_poll_complete")


def start_scheduler():
    """Start the background email polling scheduler."""
    global _scheduler

    if not POLL_ENABLED:
        logger.info("email_poll_disabled", hint="Set EMAIL_POLL_ENABLED=true to activate")
        return

    if _scheduler is not None:
        return  # Already running

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _run_email_poll,
        "interval",
        minutes=POLL_INTERVAL_MINUTES,
        id="email_poll",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("email_scheduler_started", interval_minutes=POLL_INTERVAL_MINUTES)


def stop_scheduler():
    """Stop the background scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("email_scheduler_stopped")
