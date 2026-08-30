from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from flux.errors import ConflictError
from flux.pagination import PageParams
from flux.tenancy.domain import ApiKey, Tenant
from flux.tenancy.persistence import (
    SqlAlchemyApiKeyRepository,
    SqlAlchemyTenantRepository,
)


async def test_tenant_add_get_and_name_lookup(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant, _ = Tenant.create("acme")
    async with sessionmaker() as s:
        await SqlAlchemyTenantRepository(s).add(tenant)
    async with sessionmaker() as s:
        repo = SqlAlchemyTenantRepository(s)
        assert (await repo.get(tenant.id)).name == "acme"
        assert (await repo.get_by_name("acme")).id == tenant.id


async def test_tenant_name_uniqueness(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    a, _ = Tenant.create("dup")
    b, _ = Tenant.create("dup")
    async with sessionmaker() as s:
        await SqlAlchemyTenantRepository(s).add(a)
    with pytest.raises(ConflictError):
        async with sessionmaker() as s:
            await SqlAlchemyTenantRepository(s).add(b)


async def test_tenant_status_update_persists(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant, _ = Tenant.create("acme")
    async with sessionmaker() as s:
        await SqlAlchemyTenantRepository(s).add(tenant)
    tenant.suspend()
    async with sessionmaker() as s:
        await SqlAlchemyTenantRepository(s).update(tenant)
    async with sessionmaker() as s:
        reloaded = await SqlAlchemyTenantRepository(s).get(tenant.id)
    assert reloaded.status.value == "suspended"


async def test_api_key_add_list_and_revoke(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant, _ = Tenant.create("acme")
    key, _ = ApiKey.issue(tenant_id=tenant.id, name="ci", prefix="flux_abc", roles=["model.read"])
    async with sessionmaker() as s:
        await SqlAlchemyTenantRepository(s).add(tenant)
        await SqlAlchemyApiKeyRepository(s).add(key, key_hash="deadbeef")
    async with sessionmaker() as s:
        page = await SqlAlchemyApiKeyRepository(s).list_by_tenant(tenant.id, page=PageParams())
    assert page.total == 1
    assert page.items[0].prefix == "flux_abc"

    key.revoke()
    async with sessionmaker() as s:
        await SqlAlchemyApiKeyRepository(s).update(key)
    async with sessionmaker() as s:
        reloaded = await SqlAlchemyApiKeyRepository(s).get(key.id)
    assert reloaded.status.value == "revoked"
    assert reloaded.revoked_at is not None
