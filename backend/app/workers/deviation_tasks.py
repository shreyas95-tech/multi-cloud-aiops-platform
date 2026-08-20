"""Celery tasks for deviation detection pipeline.

Triggered after trend analysis. Detects deviations, pushes WebSocket updates
to connected Dashboard clients, and queues WhatsApp notifications for
medium/high severity deviations.
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


@celery_app.task(name="app.workers.deviation_tasks.detect_deviations", bind=True)
def detect_deviations(self, report_id: str, correlation_id: str = None):
    """Detect deviations for a report after trend analysis.

    On detection of medium/high severity, queues WhatsApp notification.
    Pushes deviation updates via WebSocket to connected clients.

    Args:
        report_id: UUID of the Report record.
        correlation_id: Correlation ID for log tracing.
    """
    if not correlation_id:
        correlation_id = str(uuid.uuid4())

    log = logger.bind(
        task="detect_deviations",
        report_id=report_id,
        correlation_id=correlation_id,
        celery_task_id=self.request.id,
    )

    log.info("deviation_detection_started")

    try:
        result = _run_async(_do_detect(report_id, correlation_id, log))
        return result
    except Exception as e:
        log.error("deviation_detection_failed", error=str(e), exc_info=True)
        raise self.retry(exc=e, countdown=30, max_retries=2)


async def _do_detect(report_id: str, correlation_id: str, log):
    """Execute deviation detection asynchronously."""
    from app.database import async_session
    from app.services.deviation_detector import detect

    async with async_session() as db:
        deviations = await detect(db, report_id, correlation_id)
        await db.commit()

    log.info(
        "deviation_detection_completed",
        deviations_found=len(deviations),
    )

    # Queue WhatsApp notifications for medium/high severity deviations
    notifiable = [
        d for d in deviations
        if d["severity"] in ("medium", "high")
    ]

    if notifiable:
        _queue_notification_task(report_id, notifiable, correlation_id)

    # Push WebSocket updates for real-time dashboard (best effort)
    try:
        _push_websocket_updates(deviations, report_id)
    except Exception as e:
        log.warning("websocket_push_failed", error=str(e))

    return {
        "status": "success",
        "report_id": report_id,
        "deviations_found": len(deviations),
        "notifications_queued": len(notifiable),
        "correlation_id": correlation_id,
    }


def _queue_notification_task(
    report_id: str,
    deviations: list[dict],
    correlation_id: str,
):
    """Queue WhatsApp notification task for medium/high severity deviations."""
    celery_app.send_task(
        "app.workers.notification_tasks.send_notifications",
        args=[report_id, deviations, correlation_id],
        queue="whatsapp_notification",
    )
    logger.info(
        "notification_task_queued",
        report_id=report_id,
        deviations_count=len(deviations),
        correlation_id=correlation_id,
    )


def _push_websocket_updates(deviations: list[dict], report_id: str):
    """Push deviation updates to WebSocket connected clients.

    This is a best-effort operation; failures are logged but don't
    break the pipeline.
    """
    if not deviations:
        return

    # Import here to avoid circular dependency
    try:
        from app.api.websocket import broadcast_deviation_update
        _run_async(broadcast_deviation_update(report_id, deviations))
    except ImportError:
        # WebSocket module not yet available
        pass
    except Exception as e:
        logger.warning("websocket_broadcast_error", error=str(e))
