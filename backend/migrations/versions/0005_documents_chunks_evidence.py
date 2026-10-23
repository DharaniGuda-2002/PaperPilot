"""documents chunks evidence

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-23

Requires the pgvector extension (bundled in the pgvector/pgvector image and on Neon).
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "paper_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("content_kind", sa.String(length=16), nullable=False),
        sa.Column("full_text_unavailable_reason", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("final_url", sa.Text(), nullable=True),
        sa.Column("license", sa.String(length=64), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("extractor", sa.String(length=32), nullable=False),
        sa.Column("extractor_version", sa.String(length=32), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "content_kind IN ('full_text', 'abstract', 'none')",
            name=op.f("ck_paper_documents_kind_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["paper_id"],
            ["papers.id"],
            name=op.f("fk_paper_documents_paper_id_papers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_paper_documents")),
        sa.UniqueConstraint("paper_id", name="uq_paper_documents_paper_id"),
    )
    op.create_table(
        "paper_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', text)", persisted=True),
            nullable=False,
        ),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["paper_documents.id"],
            name=op.f("fk_paper_chunks_document_id_paper_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_paper_chunks")),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_paper_chunks_document_ordinal"),
    )
    op.create_index(
        "ix_paper_chunks_embedding",
        "paper_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_paper_chunks_tsv", "paper_chunks", ["tsv"], unique=False, postgresql_using="gin"
    )
    op.create_table(
        "evidence_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("investigation_id", sa.Uuid(), nullable=False),
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=True),
        sa.Column("field", sa.String(length=32), nullable=False),
        sa.Column("finding_status", sa.String(length=16), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("passage", sa.Text(), nullable=True),
        sa.Column("passage_kind", sa.String(length=16), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("extraction_method", sa.String(length=32), nullable=False),
        sa.Column("extraction_version", sa.String(length=32), nullable=False),
        sa.Column("retrieval_method", sa.String(length=32), nullable=True),
        sa.Column("retrieval_score", sa.Float(), nullable=True),
        sa.Column("validation_status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "field IN ('method', 'dataset', 'split', 'baseline', 'metric_result', 'limitation', 'code_availability')",
            name=op.f("ck_evidence_records_field_valid"),
        ),
        sa.CheckConstraint(
            "finding_status IN ('reported', 'not_found', 'uncertain', 'unavailable', 'not_applicable')",
            name=op.f("ck_evidence_records_finding_status_valid"),
        ),
        sa.CheckConstraint(
            "passage_kind IN ('quotation', 'paraphrase')",
            name=op.f("ck_evidence_records_passage_kind_valid"),
        ),
        sa.CheckConstraint(
            "validation_status IN ('unvalidated', 'verified', 'rejected')",
            name=op.f("ck_evidence_records_validation_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["paper_chunks.id"],
            name=op.f("fk_evidence_records_chunk_id_paper_chunks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["investigations.id"],
            name=op.f("fk_evidence_records_investigation_id_investigations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["paper_id"],
            ["papers.id"],
            name=op.f("fk_evidence_records_paper_id_papers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_records")),
    )
    op.create_index(
        "ix_evidence_records_investigation_paper",
        "evidence_records",
        ["investigation_id", "paper_id"],
        unique=False,
    )
    op.create_table(
        "evidence_validations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("rule", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=8), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("validator_version", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('pass', 'fail')", name=op.f("ck_evidence_validations_outcome_valid")
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence_records.id"],
            name=op.f("fk_evidence_validations_evidence_id_evidence_records"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_validations")),
    )
    op.create_index(
        "ix_evidence_validations_evidence_id", "evidence_validations", ["evidence_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_validations_evidence_id", table_name="evidence_validations")
    op.drop_table("evidence_validations")
    op.drop_index("ix_evidence_records_investigation_paper", table_name="evidence_records")
    op.drop_table("evidence_records")
    op.drop_index("ix_paper_chunks_tsv", table_name="paper_chunks", postgresql_using="gin")
    op.drop_index(
        "ix_paper_chunks_embedding",
        table_name="paper_chunks",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_table("paper_chunks")
    op.drop_table("paper_documents")
    op.execute("DROP EXTENSION IF EXISTS vector")
