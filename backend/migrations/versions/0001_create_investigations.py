"""create investigations

Revision ID: 0001
Revises:
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "investigations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'partially_completed', 'failed', 'cancelled')",
            name=op.f("ck_investigations_status_valid"),
        ),
        sa.CheckConstraint(
            "char_length(question) BETWEEN 10 AND 500",
            name=op.f("ck_investigations_question_length"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_investigations")),
    )
    op.create_index("ix_investigations_created_at", "investigations", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_investigations_created_at", table_name="investigations")
    op.drop_table("investigations")
