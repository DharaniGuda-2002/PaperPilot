"""create papers and search cache

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paper_search_cache",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("request", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_paper_search_cache")),
    )
    op.create_index(
        "ix_paper_search_cache_fetched_at", "paper_search_cache", ["fetched_at"], unique=False
    )
    op.create_table(
        "papers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_id", sa.String(length=64), nullable=False),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("authors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("venue", sa.Text(), nullable=True),
        sa.Column("work_type", sa.String(length=64), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("cited_by_count", sa.Integer(), nullable=True),
        sa.Column("is_open_access", sa.Boolean(), nullable=False),
        sa.Column("oa_status", sa.String(length=32), nullable=True),
        sa.Column("pdf_url", sa.Text(), nullable=True),
        sa.Column("landing_page_url", sa.Text(), nullable=True),
        sa.Column("license", sa.String(length=64), nullable=True),
        sa.Column("metadata_fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_papers")),
        sa.UniqueConstraint("provider", "provider_id", name="uq_papers_provider_provider_id"),
    )
    op.create_index("ix_papers_doi", "papers", ["doi"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_papers_doi", table_name="papers")
    op.drop_table("papers")
    op.drop_index("ix_paper_search_cache_fetched_at", table_name="paper_search_cache")
    op.drop_table("paper_search_cache")
