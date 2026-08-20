"""TrendResult model for storing computed trend analysis outputs."""

import uuid
from datetime import datetime

from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import GUID, JSONType


class TrendResult(Base):
    """Computed trend analysis result for a report metric."""

    __tablename__ = "trend_result"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("report.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    rate_of_change_pct: Mapped[float] = mapped_column(Float, nullable=False)
    algorithm_used: Mapped[str] = mapped_column(String(50), nullable=False)
    data_points_count: Mapped[int] = mapped_column(Integer, nullable=False)
    trend_data: Mapped[dict | None] = mapped_column(JSONType(), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    report: Mapped["Report"] = relationship("Report", back_populates="trend_results")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<TrendResult(id={self.id}, metric={self.metric_name}, "
            f"direction={self.direction})>"
        )
