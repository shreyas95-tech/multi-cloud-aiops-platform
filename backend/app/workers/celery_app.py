"""
Celery application configuration for the Email Report Analysis pipeline.

Configures Celery with Redis as broker and result backend, defines task routing,
autodiscovery, and the beat schedule for periodic IMAP polling.
"""

import os

from celery import Celery

# Redis connection URLs from environment variables
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

# IMAP polling interval from environment (default: 60 seconds)
IMAP_POLL_INTERVAL_SECONDS = int(
    os.environ.get("IMAP_POLL_INTERVAL_SECONDS", "60")
)

# Create the Celery application
celery_app = Celery(
    "email_report_analysis",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

# ---------------------------------------------------------------------------
# Celery configuration
# ---------------------------------------------------------------------------
celery_app.conf.update(
    # Serialization settings
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # Result expiry (24 hours)
    result_expires=86400,
    # Task autodiscovery - scans worker modules for @celery_app.task definitions
    include=[
        "app.workers.email_tasks",
        "app.workers.parse_tasks",
        "app.workers.trend_tasks",
        "app.workers.deviation_tasks",
        "app.workers.notification_tasks",
    ],
)

# ---------------------------------------------------------------------------
# Task routing - each pipeline stage gets its own queue for isolation
# ---------------------------------------------------------------------------
celery_app.conf.task_routes = {
    "app.workers.email_tasks.*": {"queue": "email_ingestion"},
    "app.workers.parse_tasks.*": {"queue": "report_parsing"},
    "app.workers.trend_tasks.*": {"queue": "trend_analysis"},
    "app.workers.deviation_tasks.*": {"queue": "deviation_detection"},
    "app.workers.notification_tasks.*": {"queue": "whatsapp_notification"},
}

# ---------------------------------------------------------------------------
# Beat schedule - periodic tasks
# ---------------------------------------------------------------------------
celery_app.conf.beat_schedule = {
    "poll-imap-mailbox": {
        "task": "app.workers.email_tasks.poll_mailbox",
        "schedule": IMAP_POLL_INTERVAL_SECONDS,
        "options": {"queue": "email_ingestion"},
    },
}

# ---------------------------------------------------------------------------
# Pipeline chain definition
# ---------------------------------------------------------------------------
# The processing pipeline follows this sequence:
#   email_ingestion → report_parsing → trend_analysis → deviation_detection → whatsapp_notification
#
# Each stage triggers the next via task chaining. The chain is initiated when
# the email ingestion worker extracts a valid attachment:
#
#   from celery import chain
#   pipeline = chain(
#       parse_report.s(attachment_id),
#       analyze_trends.s(),
#       detect_deviations.s(),
#       send_notifications.s(),
#   )
#   pipeline.apply_async()
#
# This ensures sequential processing while keeping each stage independently
# scalable and retryable.

PIPELINE_STAGES = [
    "app.workers.email_tasks.poll_mailbox",
    "app.workers.parse_tasks.parse_report",
    "app.workers.trend_tasks.analyze_trends",
    "app.workers.deviation_tasks.detect_deviations",
    "app.workers.notification_tasks.send_notifications",
]
