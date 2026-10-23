import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

EMBEDDING_DIMENSIONS = 384


class PaperDocument(Base):
    """The text PaperPilot holds for a paper: an open-access PDF's full text,
    or the provider abstract when full text is not available or not permitted.
    One current document per paper, shared by every investigation."""

    __tablename__ = "paper_documents"
    __table_args__ = (
        UniqueConstraint("paper_id", name="uq_paper_documents_paper_id"),
        CheckConstraint("content_kind IN ('full_text', 'abstract', 'none')", name="kind_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    paper_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"))
    content_kind: Mapped[str] = mapped_column(String(16))
    # Why full text is missing, when it is (e.g. "not open access", "fetch failed: ...").
    full_text_unavailable_reason: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    final_url: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(String(64))
    sha256: Mapped[str | None] = mapped_column(String(64))
    byte_size: Mapped[int | None] = mapped_column(Integer)
    page_count: Mapped[int | None] = mapped_column(Integer)
    extractor: Mapped[str] = mapped_column(String(32))
    extractor_version: Mapped[str] = mapped_column(String(32))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaperChunk(Base):
    """A passage of a document. Never crosses a page, so page_number is exact
    (None for abstracts, which have no pages)."""

    __tablename__ = "paper_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal", name="uq_paper_chunks_document_ordinal"),
        Index("ix_paper_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_paper_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("paper_documents.id", ondelete="CASCADE")
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', text)", persisted=True)
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    embedding_model: Mapped[str | None] = mapped_column(String(128))
