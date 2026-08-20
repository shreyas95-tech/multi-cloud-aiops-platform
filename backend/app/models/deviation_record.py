"""DeviationRecord model for storing detected statistical deviations."""

import uuid
from datetime import datetime

from sqlalchemy import String, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import GUID


class DeviationRecord(Base):
    """Record of a detected statistical deviation from established trends."""

    __tablename__ = "deviation_record"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("report.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    expected_value: Mapped[float] = mapped_column(Float, nullable=False)
    actual_value: Mapped[float] = mapped_column(Float, nullable=False)
    deviation_score: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    threshold_used: Mapped[float] = mapped_column(Float, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    report: Mapped["Report"] = relationship("Report", back_populates="deviation_records")  # noqa: F821
    notification_logs: Mapped[list["NotificationLog"]] = relationship(  # noqa: F821
        "NotificationLog", back_populates="deviation", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<DeviationRecord(id={self.id}, metric={self.metric_name}, "
            f"severity={self.severity})>"
        )
