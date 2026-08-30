"""initial control-plane schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-01-01 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("roles", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
    )
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)

    op.create_table(
        "models",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("family", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_models_tenant_name"),
    )
    op.create_index("ix_models_tenant_id", "models", ["tenant_id"])
    op.create_index("ix_models_family", "models", ["family"])

    op.create_table(
        "model_versions",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("model_id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("precision", sa.String(length=16), nullable=False),
        sa.Column("context_length", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("model_id", "version", name="uq_versions_model_version"),
    )
    op.create_index("ix_model_versions_model_id", "model_versions", ["model_id"])
    op.create_index("ix_model_versions_tenant_id", "model_versions", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("model_versions")
    op.drop_table("models")
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_index("ix_api_keys_tenant_id", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_table("tenants")
