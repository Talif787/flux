from __future__ import annotations

from typing import Protocol

from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from flux.auth.domain import Principal
from flux.db import Base


class TenantRow(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")


class ApiKeyRow(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    roles: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")


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
