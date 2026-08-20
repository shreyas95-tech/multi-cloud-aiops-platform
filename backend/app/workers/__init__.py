"""Celery worker tasks for the Email Report Analysis pipeline.

Pipeline: email_ingestion -> parse -> trend -> deviation -> notify
All stages propagate correlation IDs for structured JSON log tracing.
"""

# Initialize structured logging on worker startup
import app.logging_config  # noqa: F401

from app.workers.celery_app import celery_app
from app.workers.pipeline import trigger_full_pipeline, trigger_reanalysis

__all__ = [
    "celery_app",
    "trigger_full_pipeline",
    "trigger_reanalysis",
]
