"""WhatsApp notification service: message formatting, E.164 validation, and delivery with retry.

Sends WhatsApp messages for medium/high severity deviations to verified
phone numbers, with exponential backoff retry logic.
"""

import os
import re
import time
from typing import Optional

import httpx
import structlog
from dotenv import load_dotenv

from app.models.schemas import NotificationResult, DeviationSeverity

# Load .env file explicitly
load_dotenv()

logger = structlog.get_logger(__name__)

# --- Configuration ---

WHATSAPP_API_URL = os.environ.get(
    "WHATSAPP_API_URL", "https://graph.facebook.com/v18.0"
)
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")

# --- Constants ---

MAX_MESSAGE_LENGTH = 4096
"""Maximum WhatsApp message length (Req 5.2)."""

MAX_RETRIES = 3
"""Maximum retry attempts (Req 5.3)."""

INITIAL_BACKOFF_SECONDS = 5
"""Initial backoff delay for retries (Req 5.3): 5s, 10s, 20s."""

# E.164 format: + followed by country code + subscriber number (8-15 digits total)
E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


# --- E.164 Phone Number Validation ---


def validate_e164(phone_number: str) -> tuple[bool, Optional[str]]:
    """Validate that a phone number conforms to E.164 international format.

    E.164 format (Req 5.5, 5.6):
    - Starts with '+' followed by country code
    - Total digits (after +) between 8 and 15

    Args:
        phone_number: The phone number string to validate.

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    if not phone_number:
        return False, "Phone number cannot be empty."

    # Strip whitespace
    number = phone_number.strip()

    if not number.startswith("+"):
        return False, (
            "Phone number must start with '+' followed by the country code. "
            "Expected format: +[country code][subscriber number] (e.g., +14155552671)."
        )

    if not E164_PATTERN.match(number):
        # Determine specific error
        digits_only = number[1:]  # Remove the +
        if not digits_only.isdigit():
            return False, (
                "Phone number must contain only digits after the '+'. "
                "Expected format: +[country code][subscriber number] (e.g., +14155552671)."
            )
        if len(digits_only) < 8:
            return False, (
                f"Phone number is too short ({len(digits_only)} digits). "
                "Must be between 8 and 15 digits after the country code prefix."
            )
        if len(digits_only) > 15:
            return False, (
                f"Phone number is too long ({len(digits_only)} digits). "
                "Must be between 8 and 15 digits after the country code prefix."
            )
        if digits_only.startswith("0"):
            return False, (
                "Country code cannot start with 0. "
                "Expected format: +[country code][subscriber number] (e.g., +14155552671)."
            )
        return False, (
            "Invalid phone number format. "
            "Expected E.164 format: +[country code][subscriber number] (e.g., +14155552671)."
        )

    return True, None


# --- Message Formatting ---


def format_message(
    report_name: str,
    metric_name: str,
    severity: str,
    expected_value: float,
    actual_value: float,
    deviation_score: float = 0.0,
) -> str:
    """Format a WhatsApp notification message for a detected deviation.

    Includes report name, metric name, severity, expected/actual values (Req 5.2).
    Message is truncated to 4096 characters max.

    Args:
        report_name: Name of the report.
        metric_name: Name of the deviating metric.
        severity: Deviation severity level.
        expected_value: The expected (historical mean) value.
        actual_value: The actual (latest) value.
        deviation_score: Z-score of the deviation.

    Returns:
        Formatted message string (max 4096 chars).
    """
    severity_emoji = {
        "low": "⚠️",
        "medium": "🔶",
        "high": "🔴",
    }
    emoji = severity_emoji.get(severity, "⚠️")

    message = (
        f"{emoji} Deviation Alert - {severity.upper()} Severity\n"
        f"\n"
        f"Report: {report_name}\n"
        f"Metric: {metric_name}\n"
        f"Severity: {severity.capitalize()}\n"
        f"\n"
        f"Expected Value: {expected_value:.4f}\n"
        f"Actual Value: {actual_value:.4f}\n"
        f"Deviation Score: {deviation_score:.2f}σ\n"
        f"\n"
        f"Please review the Dashboard for detailed analysis."
    )

    # Truncate to max length if needed
    if len(message) > MAX_MESSAGE_LENGTH:
        message = message[: MAX_MESSAGE_LENGTH - 3] + "..."

    return message


# --- Message Sending with Retry ---


def send_with_retry(
    phone_number: str,
    message: str,
    max_retries: int = MAX_RETRIES,
) -> tuple[bool, Optional[str]]:
    """Send a WhatsApp message with exponential backoff retry.

    Retry logic (Req 5.3): up to 3 retries with backoff 5s, 10s, 20s.

    Args:
        phone_number: E.164 formatted recipient number.
        message: Message text to send.
        max_retries: Maximum retry attempts.

    Returns:
        Tuple of (success, error_message).
    """
    log = logger.bind(
        operation="send_whatsapp",
        recipient=phone_number[-4:],  # Log only last 4 digits for privacy
    )

    backoff = INITIAL_BACKOFF_SECONDS
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            success, error = _send_message(phone_number, message)
            if success:
                log.info("message_sent_successfully", attempt=attempt)
                return True, None
            else:
                last_error = error
                log.warning(
                    "message_send_failed",
                    attempt=attempt,
                    error=error,
                    next_retry_in=backoff if attempt < max_retries else None,
                )
        except Exception as e:
            last_error = str(e)
            log.warning(
                "message_send_exception",
                attempt=attempt,
                error=str(e),
                next_retry_in=backoff if attempt < max_retries else None,
            )

        # Wait before retry (exponential backoff: 5s, 10s, 20s)
        if attempt < max_retries:
            time.sleep(backoff)
            backoff *= 2

    log.error("all_retries_exhausted", total_attempts=max_retries, last_error=last_error)
    return False, last_error


def _send_message(phone_number: str, message: str) -> tuple[bool, Optional[str]]:
    """Send a single WhatsApp message via the Cloud API.

    Args:
        phone_number: E.164 formatted recipient number.
        message: Message text.

    Returns:
        Tuple of (success, error_message).
    """
    if not WHATSAPP_PHONE_NUMBER_ID or not WHATSAPP_ACCESS_TOKEN:
        return False, "WhatsApp API credentials not configured."

    url = f"{WHATSAPP_API_URL}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            # Send plain text message (works in open 24h conversation window)
            text_payload = {
                "messaging_product": "whatsapp",
                "to": phone_number.lstrip("+"),
                "type": "text",
                "text": {"body": message},
            }
            response = client.post(url, json=text_payload, headers=headers)

            if response.status_code in (200, 201):
                return True, None

            # If text fails (no open conversation), try template to open one
            template_payload = {
                "messaging_product": "whatsapp",
                "to": phone_number.lstrip("+"),
                "type": "template",
                "template": {
                    "name": "hello_world",
                    "language": {"code": "en_US"},
                },
            }
            response = client.post(url, json=template_payload, headers=headers)

            if response.status_code in (200, 201):
                return True, None
            else:
                error_detail = response.text[:500]
                return False, f"API returned {response.status_code}: {error_detail}"

    except httpx.TimeoutException:
        return False, "Request timed out."
    except httpx.RequestError as e:
        return False, f"Request error: {e}"


# --- Notification Orchestration ---


def send_deviation_notifications(
    deviation_id: str,
    report_name: str,
    metric_name: str,
    severity: str,
    expected_value: float,
    actual_value: float,
    deviation_score: float,
    verified_phone_numbers: list[str],
) -> NotificationResult:
    """Send WhatsApp notifications to all verified recipients for a deviation.

    Only sends for medium/high severity to verified numbers (Req 5.1).

    Args:
        deviation_id: UUID of the DeviationRecord.
        report_name: Report name for the message.
        metric_name: Metric name for the message.
        severity: Deviation severity.
        expected_value: Expected value.
        actual_value: Actual value.
        deviation_score: Z-score.
        verified_phone_numbers: List of verified E.164 numbers to notify.

    Returns:
        NotificationResult with delivery stats.
    """
    from uuid import UUID

    log = logger.bind(
        operation="send_deviation_notifications",
        deviation_id=deviation_id,
        severity=severity,
        recipients=len(verified_phone_numbers),
    )

    # Only send for medium/high (Req 5.1)
    if severity not in (DeviationSeverity.MEDIUM.value, DeviationSeverity.HIGH.value):
        log.info("skipping_low_severity_notification")
        return NotificationResult(
            deviation_id=UUID(deviation_id),
            success=True,
        )

    # Handle no verified recipients (Req 5.7)
    if not verified_phone_numbers:
        log.warning("no_verified_recipients")
        return NotificationResult(
            deviation_id=UUID(deviation_id),
            success=False,
            errors=["No verified phone numbers configured for this user."],
        )

    # Format the message
    message = format_message(
        report_name=report_name,
        metric_name=metric_name,
        severity=severity,
        expected_value=expected_value,
        actual_value=actual_value,
        deviation_score=deviation_score,
    )

    succeeded = 0
    failed = 0
    errors = []

    for number in verified_phone_numbers:
        success, error = send_with_retry(number, message)
        if success:
            succeeded += 1
        else:
            failed += 1
            errors.append(f"{number[-4:]}: {error}")

    log.info(
        "notifications_sent",
        succeeded=succeeded,
        failed=failed,
    )

    return NotificationResult(
        deviation_id=UUID(deviation_id),
        recipients_attempted=len(verified_phone_numbers),
        recipients_succeeded=succeeded,
        recipients_failed=failed,
        success=failed == 0,
        errors=errors,
    )
