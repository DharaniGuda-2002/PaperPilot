import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class InvestigationReport(Base):
    """An immutable report version. A rebuilt report gets the next version
    number; earlier versions are kept as history. The comparison (matrix,
    groups, claims) is stored inside `content` with its own version."""

    __tablename__ = "investigation_reports"
    __table_args__ = (
        UniqueConstraint("investigation_id", "version", name="uq_investigation_reports_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer)
    generator_version: Mapped[str] = mapped_column(String(32))
    overall_strength: Mapped[str] = mapped_column(String(16))
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
