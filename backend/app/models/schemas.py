"""Core data classes, enums, and interfaces for the Email Report Analysis system.

This module defines Pydantic models for data exchange between pipeline components,
enumerations for classification values, and system-wide constants.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# --- Enums ---


class TrendDirection(str, Enum):
    """Direction of a computed trend."""

    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"


class DeviationSeverity(str, Enum):
    """Severity classification for detected deviations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PhoneNumberStatus(str, Enum):
    """Verification status of a configured phone number."""

    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"


# --- Constants ---


MAX_ATTACHMENT_SIZE_MB: int = 25
"""Maximum allowed email attachment size in megabytes."""

MAX_PARSE_SIZE_MB: int = 50
"""Maximum file size accepted by the report parser in megabytes."""

SUPPORTED_EXTENSIONS: set[str] = {".pdf", ".xlsx", ".xls", ".csv"}
"""File extensions accepted by the email ingestion service."""

SEVERITY_THRESHOLDS: dict[str, tuple[float, float]] = {
    "low": (2.0, 2.5),
    "medium": (2.5, 3.5),
    "high": (3.5, float("inf")),
}
"""Deviation severity classification thresholds in standard deviations.

Each key maps to a (lower_bound, upper_bound) tuple where a deviation score
falling within the range is classified at that severity level.
"""


# --- Pydantic Models ---


class DataTable(BaseModel):
    """Structured output from report parsing representing a single table."""

    sheet_name: Optional[str] = None
    headers: list[str]
    rows: list[list]
    row_count: int
    column_count: int


class TrendResult(BaseModel):
    """Output of a trend analysis computation."""

    report_name: str
    metric_name: str
    direction: TrendDirection
    rate_of_change_pct: float
    algorithm_used: str
    data_points_used: list[dict]
    computed_at: datetime


class DeviationRecord(BaseModel):
    """Record of a detected statistical deviation."""

    id: UUID = Field(default_factory=uuid4)
    report_name: str
    metric_name: str
    expected_value: float
    actual_value: float
    deviation_score: float
    severity: DeviationSeverity
    threshold_used: float
    detected_at: datetime


class ParseResult(BaseModel):
    """Output of the report parsing stage."""

    tables: list[DataTable]
    file_type: str
    parse_duration_seconds: float
    success: bool
    error: Optional[str] = None


class IngestionResult(BaseModel):
    """Result of processing a single email through the ingestion service."""

    email_id: str
    sender: str
    attachments_extracted: int = 0
    attachments_skipped: int = 0
    success: bool
    error: Optional[str] = None


class AuthResult(BaseModel):
    """Result of an authentication attempt."""

    success: bool
    token: Optional[str] = None
    user_id: Optional[UUID] = None
    error: Optional[str] = None


class NotificationResult(BaseModel):
    """Result of a WhatsApp notification attempt."""

    deviation_id: UUID
    recipients_attempted: int = 0
    recipients_succeeded: int = 0
    recipients_failed: int = 0
    success: bool
    errors: list[str] = Field(default_factory=list)
