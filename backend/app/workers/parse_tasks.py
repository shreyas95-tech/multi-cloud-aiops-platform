"""Celery tasks for report parsing pipeline.

Routes attachments to the correct parser, stores parsed DataTable to database,
and queues trend analysis on success or notifies user on failure.
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog

from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "./uploads")


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


@celery_app.task(name="app.workers.parse_tasks.parse_report", bind=True)
def parse_report(self, report_id: str, correlation_id: str = None):
    """Parse a report attachment and store structured data.

    Dispatches to the correct parser based on file type, stores DataPoint
    records in the database, and queues trend analysis on success.

    Args:
        report_id: UUID of the Report record.
        correlation_id: Correlation ID for log tracing.
    """
    if not correlation_id:
        correlation_id = str(uuid.uuid4())

    log = logger.bind(
        task="parse_report",
        report_id=report_id,
        correlation_id=correlation_id,
        celery_task_id=self.request.id,
    )

    log.info("parse_task_started")

    try:
        result = _run_async(_do_parse(report_id, correlation_id, log))
        return result
    except Exception as e:
        log.error("parse_task_failed", error=str(e), exc_info=True)
        # Update report status to failed
        _run_async(_mark_report_failed(report_id, str(e)))
        raise self.retry(exc=e, countdown=60, max_retries=2)


async def _do_parse(report_id: str, correlation_id: str, log):
    """Execute the parsing logic asynchronously."""
    from app.database import async_session
    from app.models.report import Report
    from app.models.data_point import DataPoint
    from app.services.report_parser import parse_report as do_parse
    from sqlalchemy import select

    async with async_session() as db:
        # Fetch report record
        result = await db.execute(
            select(Report).where(Report.id == report_id)
        )
        report = result.scalar_one_or_none()

        if report is None:
            log.error("report_not_found", report_id=report_id)
            return {"status": "error", "error": "Report not found"}

        # Locate the file on disk
        upload_path = Path(UPLOAD_DIR)
        # Find the file by report's original filename pattern
        matching_files = list(upload_path.glob(f"*_{report.original_filename}"))
        if not matching_files:
            # Fallback: try exact filename
            matching_files = list(upload_path.glob(report.original_filename))

        if not matching_files:
            error_msg = f"Attachment file not found on disk for report {report_id}"
            log.error("file_not_found", report_id=report_id)
            report.status = "parse_failed"
            await db.commit()
            return {"status": "error", "error": error_msg}

        file_path = str(matching_files[0])

        # Parse the file
        log.info("parsing_file", file_path=file_path, file_type=report.file_type)
        parse_result = do_parse(file_path, report.file_type)

        if not parse_result.success:
            log.warning("parse_failed", error=parse_result.error)
            report.status = "parse_failed"
            await db.commit()
            return {
                "status": "error",
                "report_id": report_id,
                "error": parse_result.error,
                "correlation_id": correlation_id,
            }

        # Store parsed data as DataPoint records
        now = datetime.now(timezone.utc)
        data_points_created = 0

        for table in parse_result.tables:
            for row_idx, row in enumerate(table.rows):
                for col_idx, value in enumerate(row):
                    # Attempt to parse numeric values as data points
                    numeric_value = _try_parse_numeric(value)
                    if numeric_value is not None:
                        metric_name = table.headers[col_idx] if col_idx < len(table.headers) else f"col_{col_idx}"
                        dp = DataPoint(
                            report_id=report.id,
                            metric_name=metric_name,
                            value=numeric_value,
                            data_timestamp=now,
                            extra_data={
                                "sheet": table.sheet_name,
                                "row": row_idx + 1,
                                "col": col_idx,
                                "correlation_id": correlation_id,
                            },
                        )
                        db.add(dp)
                        data_points_created += 1

        # Update report status
        report.status = "parsed"
        report.parsed_at = now
        await db.commit()

        log.info(
            "parse_completed",
            tables=len(parse_result.tables),
            data_points=data_points_created,
            duration_s=round(parse_result.parse_duration_seconds, 2),
        )

    # Queue trend analysis task
    _queue_trend_task(report_id, correlation_id)

    return {
        "status": "success",
        "report_id": report_id,
        "data_points_created": data_points_created,
        "tables_parsed": len(parse_result.tables),
        "correlation_id": correlation_id,
    }


async def _mark_report_failed(report_id: str, error: str):
    """Mark a report as failed in the database."""
    from app.database import async_session
    from app.models.report import Report
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(
            select(Report).where(Report.id == report_id)
        )
        report = result.scalar_one_or_none()
        if report:
            report.status = "parse_failed"
            await db.commit()


def _queue_trend_task(report_id: str, correlation_id: str):
    """Queue a trend analysis task after successful parsing."""
    celery_app.send_task(
        "app.workers.trend_tasks.analyze_trends",
        args=[report_id, correlation_id],
        queue="trend_analysis",
    )
    logger.info(
        "trend_task_queued",
        report_id=report_id,
        correlation_id=correlation_id,
    )


def _try_parse_numeric(value) -> float | None:
    """Try to parse a value as a float. Returns None if not numeric."""
    if value is None or value == "":
        return None
    try:
        # Handle string values
        if isinstance(value, str):
            # Remove common formatting
            cleaned = value.strip().replace(",", "").replace(" ", "")
            # Handle percentage
            if cleaned.endswith("%"):
                return float(cleaned[:-1])
            return float(cleaned)
        return float(value)
    except (ValueError, TypeError):
        return None
