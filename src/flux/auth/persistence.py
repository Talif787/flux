from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy import DateTime, String, UniqueConstraint, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from flux.auth.domain import Principal
from flux.db import Base


class TenantRow(Base):
    __tablename__ = "tenants"
    __table_args__ = (UniqueConstraint("name", name="uq_tenants_name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ApiKeyRow(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False, server_default="")
    prefix: Mapped[str] = mapped_column(String(16), nullable=False, server_default="")
    roles: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthRepository(Protocol):
    async def find_principal_by_key_hash(self, key_hash: str) -> Principal | None: ...


class SqlAlchemyAuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_principal_by_key_hash(self, key_hash: str) -> Principal | None:
        stmt = (
            select(ApiKeyRow, TenantRow)
            .join(TenantRow, TenantRow.id == ApiKeyRow.tenant_id)
            .where(
                ApiKeyRow.key_hash == key_hash,
                ApiKeyRow.status == "active",
                TenantRow.status == "active",
            )
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        api_key, _tenant = row
        roles = frozenset(r for r in api_key.roles.split(",") if r)
        return Principal(tenant_id=api_key.tenant_id, api_key_id=api_key.id, roles=roles)
