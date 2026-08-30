from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from flux.auth.domain import ApiKeyStatus, TenantStatus
from flux.auth.persistence import ApiKeyRow, TenantRow
from flux.errors import ConflictError
from flux.pagination import Page, PageParams
from flux.tenancy.domain import ApiKey, Tenant


def _to_tenant(row: TenantRow) -> Tenant:
    return Tenant(
        id=row.id,
        name=row.name,
        status=TenantStatus(row.status),
        created_at=row.created_at,
    )


def _to_api_key(row: ApiKeyRow) -> ApiKey:
    roles = frozenset(r for r in row.roles.split(",") if r)
    return ApiKey(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        prefix=row.prefix,
        roles=roles,
        status=ApiKeyStatus(row.status),
        created_at=row.created_at,
        revoked_at=row.revoked_at,
    )


class SqlAlchemyTenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, tenant: Tenant) -> None:
        self._session.add(
            TenantRow(
                id=tenant.id,
                name=tenant.name,
                status=tenant.status.value,
                created_at=tenant.created_at,
            )
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(f"tenant already exists: {tenant.name}") from exc

    async def get(self, tenant_id: str) -> Tenant | None:
        row = await self._session.get(TenantRow, tenant_id)
        return _to_tenant(row) if row is not None else None

    async def get_by_name(self, name: str) -> Tenant | None:
        stmt = select(TenantRow).where(TenantRow.name == name)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_tenant(row) if row is not None else None

    async def list(self, *, page: PageParams) -> Page[Tenant]:
        total = int(
            (await self._session.execute(select(func.count()).select_from(TenantRow))).scalar_one()
        )
        rows = (
            (
                await self._session.execute(
                    select(TenantRow)
                    .order_by(TenantRow.created_at.desc())
                    .limit(page.limit)
                    .offset(page.offset)
                )
            )
            .scalars()
            .all()
        )
        return Page(
            items=[_to_tenant(r) for r in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )

    async def update(self, tenant: Tenant) -> None:
        row = await self._session.get(TenantRow, tenant.id)
        if row is None:
            return
        row.name = tenant.name
        row.status = tenant.status.value
        await self._session.commit()


class SqlAlchemyApiKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, api_key: ApiKey, *, key_hash: str) -> None:
        self._session.add(
            ApiKeyRow(
                id=api_key.id,
                tenant_id=api_key.tenant_id,
                key_hash=key_hash,
                name=api_key.name,
                prefix=api_key.prefix,
                roles=",".join(sorted(api_key.roles)),
                status=api_key.status.value,
                created_at=api_key.created_at,
                revoked_at=api_key.revoked_at,
            )
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("api key hash collision") from exc

    async def get(self, api_key_id: str) -> ApiKey | None:
        row = await self._session.get(ApiKeyRow, api_key_id)
        return _to_api_key(row) if row is not None else None

    async def list_by_tenant(self, tenant_id: str, *, page: PageParams) -> Page[ApiKey]:
        predicate = ApiKeyRow.tenant_id == tenant_id
        total = int(
            (
                await self._session.execute(
                    select(func.count()).select_from(ApiKeyRow).where(predicate)
                )
            ).scalar_one()
        )
        rows = (
            (
                await self._session.execute(
                    select(ApiKeyRow)
                    .where(predicate)
                    .order_by(ApiKeyRow.created_at.desc())
                    .limit(page.limit)
                    .offset(page.offset)
                )
            )
            .scalars()
            .all()
        )
        return Page(
            items=[_to_api_key(r) for r in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )

    async def update(self, api_key: ApiKey) -> None:
        row = await self._session.get(ApiKeyRow, api_key.id)
        if row is None:
            return
        row.status = api_key.status.value
        row.revoked_at = api_key.revoked_at
        await self._session.commit()
