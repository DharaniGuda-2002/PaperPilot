"""fetch host schedule

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fetch_host_schedule",
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("next_slot_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("host", name=op.f("pk_fetch_host_schedule")),
    )


def downgrade() -> None:
    op.drop_table("fetch_host_schedule")
