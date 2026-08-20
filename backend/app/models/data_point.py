"""DataPoint model for time-series report data."""

import uuid
from datetime import datetime

from sqlalchemy import String, Float, DateTime, Index, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import GUID, JSONType


class DataPoint(Base):
    """Individual data point extracted from a parsed report."""

    __tablename__ = "data_point"
    __table_args__ = (
        Index(
            "ix_data_point_report_metric_timestamp",
            "report_id",
            "metric_name",
            "data_timestamp",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("report.id", ondelete="CASCADE"), nullable=False
    )
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    data_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    extra_data: Mapped[dict | None] = mapped_column(JSONType(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    report: Mapped["Report"] = relationship("Report", back_populates="data_points")  # noqa: F821

    def __repr__(self) -> str:
        return f"<DataPoint(id={self.id}, metric={self.metric_name}, value={self.value})>"
