"""metering: usage records and model prices

Revision ID: 0005_metering
Revises: 0004_workers
Create Date: 2026-01-05 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_metering"
down_revision: str | None = "0004_workers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usage_records",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_usage_records"),
    )
    op.create_index("ix_usage_records_tenant_id", "usage_records", ["tenant_id"])
    op.create_index("ix_usage_records_model_name", "usage_records", ["model_name"])
    op.create_index("ix_usage_records_recorded_at", "usage_records", ["recorded_at"])
    op.create_table(
        "model_prices",
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("prompt_per_1k", sa.String(length=32), nullable=False),
        sa.Column("completion_per_1k", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("model_name", name="pk_model_prices"),
    )


def downgrade() -> None:
    op.drop_table("model_prices")
    op.drop_index("ix_usage_records_recorded_at", table_name="usage_records")
    op.drop_index("ix_usage_records_model_name", table_name="usage_records")
    op.drop_index("ix_usage_records_tenant_id", table_name="usage_records")
    op.drop_table("usage_records")
