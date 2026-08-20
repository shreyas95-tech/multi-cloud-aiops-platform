"""IngestionRule model for mapping incoming emails to existing reports."""

import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import GUID


class IngestionRule(Base):
    """Rule for matching incoming emails to existing reports.

    When an email arrives, rules are checked in priority order.
    If a rule matches, the attachment data is appended to the target report.
    """

    __tablename__ = "ingestion_rule"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    target_report_name: Mapped[str] = mapped_column(String(500), nullable=False)
    
    # Match conditions (any matching condition triggers the rule)
    subject_contains: Mapped[str | None] = mapped_column(String(500), nullable=True)
    filename_contains: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sender_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    
    # Settings
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(default=10)  # Lower = higher priority
    
    # Who created this rule
    created_by: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("user.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def matches(self, subject: str, filename: str, sender: str) -> bool:
        """Check if an email matches this rule.

        Returns True if ANY of the configured conditions match.
        """
        subject_lower = subject.lower()
        filename_lower = filename.lower()
        sender_lower = sender.lower()

        if self.subject_contains and self.subject_contains.lower() in subject_lower:
            return True
        if self.filename_contains and self.filename_contains.lower() in filename_lower:
            return True
        if self.sender_email and self.sender_email.lower() == sender_lower:
            return True

        return False

    def __repr__(self) -> str:
        return f"<IngestionRule(name={self.name}, target={self.target_report_name})>"
