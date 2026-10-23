import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

QUESTION_MIN_LENGTH = 10
QUESTION_MAX_LENGTH = 500


class InvestigationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_status_values = ", ".join(f"'{s.value}'" for s in InvestigationStatus)


class Investigation(Base):
    __tablename__ = "investigations"
    __table_args__ = (
        CheckConstraint(f"status IN ({_status_values})", name="status_valid"),
        CheckConstraint(
            f"char_length(question) BETWEEN {QUESTION_MIN_LENGTH} AND {QUESTION_MAX_LENGTH}",
            name="question_length",
        ),
        Index("ix_investigations_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default=InvestigationStatus.QUEUED.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
