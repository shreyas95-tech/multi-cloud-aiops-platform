"""Full Celery pipeline wiring: email_ingestion -> parse -> trend -> deviation -> notify.

This module provides helper functions to trigger the complete pipeline chain
with proper correlation ID propagation and structured logging.
"""

import uuid

import structlog

from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def trigger_full_pipeline(report_id: str, correlation_id: str = None) -> str:
    """Trigger the full analysis pipeline for a report.

    Pipeline stages:
    1. parse_report - Extract structured data from attachment
    2. analyze_trends - Run ML algorithms on historical data
    3. detect_deviations - Statistical outlier detection
    4. send_notifications - WhatsApp alerts for medium/high deviations

    Each stage automatically triggers the next on success.
    Correlation ID propagates through all stages for log tracing.

    Args:
        report_id: UUID of the Report record to process.
        correlation_id: Optional correlation ID. Generated if not provided.

    Returns:
        The correlation_id used for this pipeline run.
    """
    if not correlation_id:
        correlation_id = str(uuid.uuid4())

    log = logger.bind(
        operation="trigger_pipeline",
        report_id=report_id,
        correlation_id=correlation_id,
    )

    log.info("pipeline_triggered")

    # Start with parsing - each subsequent stage is triggered by the previous one
    celery_app.send_task(
        "app.workers.parse_tasks.parse_report",
        args=[report_id, correlation_id],
        queue="report_parsing",
    )

    return correlation_id


def trigger_reanalysis(report_id: str, correlation_id: str = None) -> str:
    """Re-trigger analysis from the trend stage (skip parsing).

    Useful when historical data changes or algorithms are updated.

    Args:
        report_id: UUID of the Report record.
        correlation_id: Optional correlation ID.

    Returns:
        The correlation_id used.
    """
    if not correlation_id:
        correlation_id = str(uuid.uuid4())

    logger.info(
        "reanalysis_triggered",
        report_id=report_id,
        correlation_id=correlation_id,
    )

    celery_app.send_task(
        "app.workers.trend_tasks.analyze_trends",
        args=[report_id, correlation_id],
        queue="trend_analysis",
    )

    return correlation_id


# --- Pipeline Stage Reference ---
# This documents the complete chain for reference:
#
# Stage 1: app.workers.email_tasks.poll_mailbox
#   - Polls IMAP for unread emails
#   - Validates sender, filters attachments
#   - Creates Report records
#   - Triggers: parse_report for each valid attachment
#
# Stage 2: app.workers.parse_tasks.parse_report
#   - Routes to PDF/Excel/CSV parser
#   - Stores DataPoint records
#   - Updates Report status
#   - Triggers: analyze_trends
#
# Stage 3: app.workers.trend_tasks.analyze_trends
#   - Fetches historical data by report name
#   - Runs linear_regression / moving_average / seasonal_decomposition
#   - Stores TrendResult records
#   - Triggers: detect_deviations
#
# Stage 4: app.workers.deviation_tasks.detect_deviations
#   - Computes z-score and IQR for each metric
#   - Classifies severity (low/medium/high)
#   - Records DeviationRecords
#   - Pushes WebSocket updates
#   - Triggers: send_notifications (for medium/high)
#
# Stage 5: app.workers.notification_tasks.send_notifications
#   - Fetches verified phone numbers for user
#   - Formats WhatsApp message
#   - Sends with exponential backoff retry
#   - Logs NotificationLog records
#
# All stages receive and pass correlation_id for end-to-end tracing.
