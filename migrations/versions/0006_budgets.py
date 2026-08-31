"""budgets: per-tenant monthly spend limits

Revision ID: 0006_budgets
Revises: 0005_metering
Create Date: 2026-01-06 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_budgets"
down_revision: str | None = "0005_metering"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "budgets",
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("monthly_limit", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", name="pk_budgets"),
    )


def downgrade() -> None:
    op.drop_table("budgets")
