"""Business logic services for the Email Report Analysis system."""

from app.services.auth_service import (
    hash_password,
    verify_password,
    validate_password_strength,
    register_user,
)
from app.services.email_ingestion import poll_mailbox, process_email, filter_attachments
from app.services.report_parser import parse_pdf, parse_excel, parse_csv, parse_report
from app.services.trend_analyzer import (
    linear_regression,
    moving_average,
    seasonal_decomposition,
    select_algorithm,
    analyze,
)
from app.services.deviation_detector import (
    compute_zscore,
    compute_iqr_outlier,
    classify_severity,
    detect,
)
from app.services.whatsapp_notifier import (
    validate_e164,
    format_message,
    send_with_retry,
    send_deviation_notifications,
)

__all__ = [
    "hash_password",
    "verify_password",
    "validate_password_strength",
    "register_user",
    "poll_mailbox",
    "process_email",
    "filter_attachments",
    "parse_pdf",
    "parse_excel",
    "parse_csv",
    "parse_report",
    "linear_regression",
    "moving_average",
    "seasonal_decomposition",
    "select_algorithm",
    "analyze",
    "compute_zscore",
    "compute_iqr_outlier",
    "classify_severity",
    "detect",
    "validate_e164",
    "format_message",
    "send_with_retry",
    "send_deviation_notifications",
]
