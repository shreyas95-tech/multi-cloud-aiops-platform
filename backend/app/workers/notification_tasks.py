"""Celery tasks for WhatsApp notification delivery.

Triggered by deviation detection for medium/high severity deviations.
Fetches verified phone numbers, sends messages, and logs results.
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


@celery_app.task(name="app.workers.notification_tasks.send_notifications", bind=True)
def send_notifications(self, report_id: str, deviations: list[dict], correlation_id: str = None):
    """Send WhatsApp notifications for detected deviations.

    Fetches verified phone numbers for the report owner, sends notifications
    for each medium/high severity deviation, and logs results.

    Args:
        report_id: UUID of the Report record.
        deviations: List of deviation dicts from deviation detection.
        correlation_id: Correlation ID for log tracing.
    """
    if not correlation_id:
        correlation_id = str(uuid.uuid4())

    log = logger.bind(
        task="send_notifications",
        report_id=report_id,
        correlation_id=correlation_id,
        celery_task_id=self.request.id,
        deviations_count=len(deviations),
    )

    log.info("notification_task_started")

    try:
        result = _run_async(_do_notify(report_id, deviations, correlation_id, log))
        return result
    except Exception as e:
        log.error("notification_task_failed", error=str(e), exc_info=True)
        # Don't retry notification tasks aggressively to avoid spam
        raise self.retry(exc=e, countdown=60, max_retries=1)


async def _do_notify(report_id: str, deviations: list[dict], correlation_id: str, log):
    """Execute notification sending asynchronously."""
    from app.database import async_session
    from app.models.report import Report
    from app.models.phone_number import PhoneNumber
    from app.models.notification_log import NotificationLog
    from app.services.whatsapp_notifier import send_deviation_notifications
    from sqlalchemy import select

    async with async_session() as db:
        # Fetch report to get user
        report_result = await db.execute(
            select(Report).where(Report.id == report_id)
        )
        report = report_result.scalar_one_or_none()

        if report is None:
            log.error("report_not_found")
            return {"status": "error", "error": "Report not found"}

        # Fetch verified phone numbers for the user (Req 8.6)
        phone_result = await db.execute(
            select(PhoneNumber).where(
                PhoneNumber.user_id == report.user_id,
                PhoneNumber.status == "verified",
            )
        )
        verified_numbers = [pn.number for pn in phone_result.scalars().all()]

        # Send notifications for each deviation
        total_sent = 0
        total_failed = 0
        all_errors = []

        for deviation in deviations:
            result = send_deviation_notifications(
                deviation_id=deviation["deviation_id"],
                report_name=deviation.get("report_name", report.name),
                metric_name=deviation["metric_name"],
                severity=deviation["severity"],
                expected_value=deviation["expected_value"],
                actual_value=deviation["actual_value"],
                deviation_score=deviation.get("deviation_score", 0.0),
                verified_phone_numbers=verified_numbers,
            )

            total_sent += result.recipients_succeeded
            total_failed += result.recipients_failed
            all_errors.extend(result.errors)

            # Log notification attempt
            for number in verified_numbers:
                status = "sent" if result.success else "failed"
                notification_log = NotificationLog(
                    user_id=report.user_id,
                    deviation_id=deviation["deviation_id"],
                    phone_number=number,
                    status=status,
                    retry_count=0 if result.success else 3,
                    error_message="; ".join(result.errors)[:1000] if result.errors else None,
                )
                db.add(notification_log)

        await db.commit()

    log.info(
        "notification_task_completed",
        total_sent=total_sent,
        total_failed=total_failed,
        errors_count=len(all_errors),
    )

    return {
        "status": "success" if total_failed == 0 else "partial_failure",
        "report_id": report_id,
        "notifications_sent": total_sent,
        "notifications_failed": total_failed,
        "errors": all_errors[:10],  # Limit error list
        "correlation_id": correlation_id,
    }
