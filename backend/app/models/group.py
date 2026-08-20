"""Group model for organizing users and reports."""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import GUID


class Group(Base):
    """Group that users belong to. Reports are scoped to groups."""

    __tablename__ = "group"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    members: Mapped[list["User"]] = relationship("User", back_populates="group")  # noqa: F821
    reports: Mapped[list["Report"]] = relationship("Report", back_populates="group")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Group(id={self.id}, name={self.name})>"
