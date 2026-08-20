"""Celery tasks for email ingestion pipeline.

Implements periodic IMAP polling and triggers the report parsing pipeline
for each valid extracted attachment.
"""

import asyncio
import uuid

import structlog

from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _run_async(coro):
    """Run an async coroutine in a synchronous Celery task context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@celery_app.task(name="app.workers.email_tasks.poll_mailbox", bind=True)
def poll_mailbox(self):
    """Periodic task: poll IMAP mailbox and process unread emails.

    For each valid attachment extracted, queues a report parsing task.
    Uses structured JSON logging with correlation IDs.
    """
    correlation_id = str(uuid.uuid4())
    log = logger.bind(
        task="poll_mailbox",
        correlation_id=correlation_id,
        celery_task_id=self.request.id,
    )

    log.info("imap_poll_started")

    try:
        from app.services.email_ingestion import poll_mailbox as fetch_emails

        emails = fetch_emails()
        log.info("emails_fetched", count=len(emails))

        if not emails:
            log.info("no_new_emails")
            return {"status": "complete", "emails_processed": 0, "correlation_id": correlation_id}

        # Process each email
        results = _run_async(_process_all_emails(emails, correlation_id))

        total_extracted = sum(r.attachments_extracted for r in results if r.success)
        log.info(
            "imap_poll_completed",
            emails_processed=len(emails),
            total_attachments_extracted=total_extracted,
        )

        return {
            "status": "complete",
            "emails_processed": len(emails),
            "attachments_extracted": total_extracted,
            "correlation_id": correlation_id,
        }

    except Exception as e:
        log.error("imap_poll_failed", error=str(e), exc_info=True)
        raise self.retry(exc=e, countdown=30, max_retries=3)


async def _process_all_emails(emails: list[dict], correlation_id: str):
    """Process all fetched emails and queue parsing tasks for valid attachments."""
    from app.database import async_session
    from app.services.email_ingestion import process_email
    from app.models.report import Report
    from sqlalchemy import select

    results = []

    async with async_session() as db:
        for msg_data in emails:
            result = await process_email(msg_data, db, correlation_id)
            results.append(result)

        # Get report IDs that were just created (status=received) for this batch
        stmt = select(Report).where(Report.status == "received")
        report_results = await db.execute(stmt)
        new_reports = report_results.scalars().all()

        await db.commit()

    # Queue parsing tasks for each new report
    for report in new_reports:
        _queue_parse_task(str(report.id), correlation_id)

    return results


def _queue_parse_task(report_id: str, correlation_id: str):
    """Queue a report parsing task for a successfully ingested attachment."""
    from app.workers.celery_app import celery_app

    log = logger.bind(
        operation="queue_parse_task",
        report_id=report_id,
        correlation_id=correlation_id,
    )

    celery_app.send_task(
        "app.workers.parse_tasks.parse_report",
        args=[report_id, correlation_id],
        queue="report_parsing",
    )
    log.info("parse_task_queued", report_id=report_id)
