"""tenancy: created_at, api-key metadata, unique tenant name

Revision ID: 0002_tenancy
Revises: 0001_initial
Create Date: 2026-01-02 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_tenancy"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_unique_constraint("uq_tenants_name", "tenants", ["name"])

    op.add_column(
        "api_keys",
        sa.Column("name", sa.String(length=128), server_default="", nullable=False),
    )
    op.add_column(
        "api_keys",
        sa.Column("prefix", sa.String(length=16), server_default="", nullable=False),
    )
    op.add_column(
        "api_keys",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "api_keys",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "revoked_at")
    op.drop_column("api_keys", "created_at")
    op.drop_column("api_keys", "prefix")
    op.drop_column("api_keys", "name")
    op.drop_constraint("uq_tenants_name", "tenants", type_="unique")
    op.drop_column("tenants", "created_at")
