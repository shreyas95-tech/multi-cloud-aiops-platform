"""Celery tasks for trend analysis pipeline.

Triggers trend analysis after report parsing and queues deviation
detection on successful computation.
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


@celery_app.task(name="app.workers.trend_tasks.analyze_trends", bind=True)
def analyze_trends(self, report_id: str, correlation_id: str = None):
    """Analyze trends for a parsed report.

    Triggered after successful report parsing. On completion,
    queues deviation detection.

    Args:
        report_id: UUID of the Report record.
        correlation_id: Correlation ID for log tracing.
    """
    if not correlation_id:
        correlation_id = str(uuid.uuid4())

    log = logger.bind(
        task="analyze_trends",
        report_id=report_id,
        correlation_id=correlation_id,
        celery_task_id=self.request.id,
    )

    log.info("trend_analysis_started")

    try:
        result = _run_async(_do_analyze(report_id, correlation_id, log))
        return result
    except Exception as e:
        log.error("trend_analysis_failed", error=str(e), exc_info=True)
        raise self.retry(exc=e, countdown=30, max_retries=2)


async def _do_analyze(report_id: str, correlation_id: str, log):
    """Execute trend analysis asynchronously."""
    from app.database import async_session
    from app.services.trend_analyzer import analyze

    async with async_session() as db:
        results = await analyze(db, report_id, correlation_id)
        await db.commit()

    log.info(
        "trend_analysis_completed",
        metrics_analyzed=len(results),
    )

    # Queue deviation detection
    _queue_deviation_task(report_id, correlation_id)

    return {
        "status": "success",
        "report_id": report_id,
        "trends_computed": len(results),
        "results": results,
        "correlation_id": correlation_id,
    }


def _queue_deviation_task(report_id: str, correlation_id: str):
    """Queue deviation detection task after trend analysis."""
    celery_app.send_task(
        "app.workers.deviation_tasks.detect_deviations",
        args=[report_id, correlation_id],
        queue="deviation_detection",
    )
    logger.info(
        "deviation_task_queued",
        report_id=report_id,
        correlation_id=correlation_id,
    )
