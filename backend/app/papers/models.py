import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
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


class Paper(Base):
    """Normalized paper metadata from a research metadata provider.

    Provenance: (provider, provider_id) identifies the source record and
    metadata_fetched_at records when it was last refreshed.
    """

    __tablename__ = "papers"
    __table_args__ = (
        UniqueConstraint("provider", "provider_id", name="uq_papers_provider_provider_id"),
        # Not unique: providers sometimes hold duplicate records for one DOI.
        Index("ix_papers_doi", "doi"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32))
    provider_id: Mapped[str] = mapped_column(String(64))
    doi: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(Text)
    authors: Mapped[list[str]] = mapped_column(JSONB)
    publication_year: Mapped[int | None] = mapped_column(Integer)
    venue: Mapped[str | None] = mapped_column(Text)
    work_type: Mapped[str | None] = mapped_column(String(64))
    abstract: Mapped[str | None] = mapped_column(Text)
    cited_by_count: Mapped[int | None] = mapped_column(Integer)
    is_open_access: Mapped[bool] = mapped_column(Boolean)
    oa_status: Mapped[str | None] = mapped_column(String(32))
    pdf_url: Mapped[str | None] = mapped_column(Text)
    landing_page_url: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(String(64))
    metadata_fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SearchCacheEntry(Base):
    """One provider search response, stored as ordered paper references.

    Serves repeated searches without spending provider quota, and counting
    recent rows gives the number of provider calls for the daily cap.
    """

    __tablename__ = "paper_search_cache"
    __table_args__ = (Index("ix_paper_search_cache_fetched_at", "fetched_at"),)

    key: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of the request
    provider: Mapped[str] = mapped_column(String(32))
    request: Mapped[dict[str, Any]] = mapped_column(JSONB)
    total: Mapped[int] = mapped_column(Integer)
    # [{"paper_id": "...", "relevance_score": 12.3 | null}, ...] in provider order
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
