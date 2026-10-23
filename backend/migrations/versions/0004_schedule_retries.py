"""schedule retries

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "investigation_tasks",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "outbox_events",
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.drop_index(
        op.f("ix_outbox_events_unpublished"),
        table_name="outbox_events",
        postgresql_where="(published_at IS NULL)",
    )
    op.create_index(
        "ix_outbox_events_unpublished_due",
        "outbox_events",
        ["available_at"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outbox_events_unpublished_due",
        table_name="outbox_events",
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_index(
        op.f("ix_outbox_events_unpublished"),
        "outbox_events",
        ["created_at"],
        unique=False,
        postgresql_where="(published_at IS NULL)",
    )
    op.drop_column("outbox_events", "available_at")
    op.drop_column("investigation_tasks", "next_attempt_at")
