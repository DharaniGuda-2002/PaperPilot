import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
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


class TaskKind(StrEnum):
    DISCOVER_PAPERS = "discover_papers"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_PERMANENT = "failed_permanent"
    SKIPPED = "skipped"


_task_status_values = ", ".join(f"'{s.value}'" for s in TaskStatus)


class InvestigationTask(Base):
    """One unit of pipeline work. subject_key identifies what the task acts on
    ('' for investigation-wide tasks, a paper id for per-paper tasks)."""

    __tablename__ = "investigation_tasks"
    __table_args__ = (
        UniqueConstraint(
            "investigation_id", "kind", "subject_key", name="uq_investigation_tasks_subject"
        ),
        CheckConstraint(f"status IN ({_task_status_values})", name="status_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(64))
    subject_key: Mapped[str] = mapped_column(String(64), server_default="")
    status: Mapped[str] = mapped_column(String(32), default=TaskStatus.PENDING.value)
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InvestigationPaper(Base):
    """A paper discovered for an investigation, with how it was found."""

    __tablename__ = "investigation_papers"
    __table_args__ = (Index("ix_investigation_papers_paper_id", "paper_id"),)

    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), primary_key=True
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    rank: Mapped[int] = mapped_column(Integer)
    relevance_score: Mapped[float | None] = mapped_column(Float)
    retrieval_method: Mapped[str] = mapped_column(String(64))
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
