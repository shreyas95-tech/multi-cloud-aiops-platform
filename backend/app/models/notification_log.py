"""NotificationLog model for tracking WhatsApp notification delivery."""

import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import GUID


class NotificationLog(Base):
    """Log entry for each WhatsApp notification attempt."""

    __tablename__ = "notification_log"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    deviation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("deviation_record.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="notification_logs")  # noqa: F821
    deviation: Mapped["DeviationRecord"] = relationship(  # noqa: F821
        "DeviationRecord", back_populates="notification_logs"
    )

    def __repr__(self) -> str:
        return (
            f"<NotificationLog(id={self.id}, status={self.status}, "
            f"retry_count={self.retry_count})>"
        )
