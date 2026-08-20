"""Report model for tracking ingested email attachments."""

import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import GUID


class Report(Base):
    """Report metadata for an ingested email attachment."""

    __tablename__ = "report"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("group.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    source_email: Mapped[str] = mapped_column(String(320), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="received")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    parsed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="reports")  # noqa: F821
    group: Mapped["Group | None"] = relationship("Group", back_populates="reports")  # noqa: F821
    data_points: Mapped[list["DataPoint"]] = relationship(  # noqa: F821
        "DataPoint", back_populates="report", cascade="all, delete-orphan"
    )
    trend_results: Mapped[list["TrendResult"]] = relationship(  # noqa: F821
        "TrendResult", back_populates="report", cascade="all, delete-orphan"
    )
    deviation_records: Mapped[list["DeviationRecord"]] = relationship(  # noqa: F821
        "DeviationRecord", back_populates="report", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Report(id={self.id}, name={self.name}, status={self.status})>"
