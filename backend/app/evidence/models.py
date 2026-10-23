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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class EvidenceField(StrEnum):
    METHOD = "method"
    DATASET = "dataset"
    SPLIT = "split"  # train/test split or evaluation protocol
    BASELINE = "baseline"
    METRIC_RESULT = "metric_result"  # a metric with a reported value
    LIMITATION = "limitation"
    CODE_AVAILABILITY = "code_availability"


class FindingStatus(StrEnum):
    REPORTED = "reported"
    NOT_FOUND = "not_found"  # full text searched, nothing matched; not proof of absence
    UNCERTAIN = "uncertain"
    UNAVAILABLE = "unavailable"  # no full text to search
    NOT_APPLICABLE = "not_applicable"


class ValidationStatus(StrEnum):
    UNVALIDATED = "unvalidated"
    VERIFIED = "verified"
    REJECTED = "rejected"


def _in(values: type[StrEnum]) -> str:
    return ", ".join(f"'{v.value}'" for v in values)


class EvidenceRecord(Base):
    """One extracted fact with its provenance. `passage` is an exact quotation
    from the chunk (passage_kind = 'quotation'); it is never paraphrased."""

    __tablename__ = "evidence_records"
    __table_args__ = (
        CheckConstraint(f"field IN ({_in(EvidenceField)})", name="field_valid"),
        CheckConstraint(f"finding_status IN ({_in(FindingStatus)})", name="finding_status_valid"),
        CheckConstraint(
            f"validation_status IN ({_in(ValidationStatus)})", name="validation_status_valid"
        ),
        CheckConstraint("passage_kind IN ('quotation', 'paraphrase')", name="passage_kind_valid"),
        Index("ix_evidence_records_investigation_paper", "investigation_id", "paper_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE")
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"))
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("paper_chunks.id", ondelete="CASCADE")
    )
    field: Mapped[str] = mapped_column(String(32))
    finding_status: Mapped[str] = mapped_column(String(16))
    value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    passage: Mapped[str | None] = mapped_column(Text)
    passage_kind: Mapped[str | None] = mapped_column(String(16))
    page_number: Mapped[int | None] = mapped_column(Integer)
    extraction_method: Mapped[str] = mapped_column(String(32))
    extraction_version: Mapped[str] = mapped_column(String(32))
    # How the chunk was found for this question: 'fts', 'vector', or 'fts+vector'.
    retrieval_method: Mapped[str | None] = mapped_column(String(32))
    retrieval_score: Mapped[float | None] = mapped_column(Float)
    validation_status: Mapped[str] = mapped_column(
        String(16), default=ValidationStatus.UNVALIDATED.value
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceValidation(Base):
    """Append-only validation history for an evidence record."""

    __tablename__ = "evidence_validations"
    __table_args__ = (
        CheckConstraint("outcome IN ('pass', 'fail')", name="outcome_valid"),
        Index("ix_evidence_validations_evidence_id", "evidence_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_records.id", ondelete="CASCADE")
    )
    rule: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(8))
    details: Mapped[str | None] = mapped_column(Text)
    validator_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
