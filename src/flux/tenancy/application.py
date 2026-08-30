from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from flux.auth.domain import Principal, Role
from flux.auth.hashing import generate_api_key, key_prefix
from flux.errors import ConflictError, ForbiddenError, NotFoundError
from flux.events import EventBus
from flux.pagination import Page, PageParams
from flux.tenancy.domain import (
    ApiKey,
    ApiKeyRepository,
    Tenant,
    TenantRepository,
)


@dataclass(frozen=True)
class IssuedApiKey:
    """The result of issuing a key: the entity plus its one-time plaintext."""

    api_key: ApiKey
    plaintext: str


class TenantService:
    """Platform-level tenant lifecycle use cases (platform-admin gated)."""

    def __init__(self, tenants: TenantRepository, event_bus: EventBus) -> None:
        self._tenants = tenants
        self._events = event_bus

    async def create_tenant(self, name: str) -> Tenant:
        if await self._tenants.get_by_name(name.strip()):
            raise ConflictError(f"tenant already exists: {name}")
        tenant, event = Tenant.create(name)
        await self._tenants.add(tenant)
        await self._events.publish(event)
        return tenant

    async def get_tenant(self, tenant_id: str) -> Tenant:
        tenant = await self._tenants.get(tenant_id)
        if tenant is None:
            raise NotFoundError("tenant", tenant_id)
        return tenant

    async def list_tenants(self, *, page: PageParams) -> Page[Tenant]:
        return await self._tenants.list(page=page)

    async def suspend_tenant(self, tenant_id: str) -> Tenant:
        tenant = await self.get_tenant(tenant_id)
        event = tenant.suspend()
        await self._tenants.update(tenant)
        await self._events.publish(event)
        return tenant

    async def reactivate_tenant(self, tenant_id: str) -> Tenant:
        tenant = await self.get_tenant(tenant_id)
        event = tenant.reactivate()
        await self._tenants.update(tenant)
        await self._events.publish(event)
        return tenant


class ApiKeyService:
    """API-key lifecycle use cases with tenant-scoped authorization."""

    def __init__(
        self,
        api_keys: ApiKeyRepository,
        tenants: TenantRepository,
        event_bus: EventBus,
        hasher: Callable[[str], str],
    ) -> None:
        self._api_keys = api_keys
        self._tenants = tenants
        self._events = event_bus
        self._hasher = hasher

    @staticmethod
    def _authorize_tenant(actor: Principal, tenant_id: str) -> None:
        if actor.is_platform_admin:
            return
        if actor.has_role(Role.TENANT_ADMIN) and actor.tenant_id == tenant_id:
            return
        raise ForbiddenError("not permitted to manage keys for this tenant")

    @staticmethod
    def _authorize_roles(actor: Principal, roles: list[str]) -> None:
        if Role.PLATFORM_ADMIN in roles and not actor.is_platform_admin:
            raise ForbiddenError("only a platform admin may grant platform.admin")

    async def _require_tenant(self, tenant_id: str) -> Tenant:
        tenant = await self._tenants.get(tenant_id)
        if tenant is None:
            raise NotFoundError("tenant", tenant_id)
        return tenant

    async def issue_key(
        self, actor: Principal, tenant_id: str, name: str, roles: list[str]
    ) -> IssuedApiKey:
        self._authorize_tenant(actor, tenant_id)
        self._authorize_roles(actor, roles)
        await self._require_tenant(tenant_id)
        raw = generate_api_key()
        api_key, event = ApiKey.issue(
            tenant_id=tenant_id, name=name, prefix=key_prefix(raw), roles=roles
        )
        await self._api_keys.add(api_key, key_hash=self._hasher(raw))
        await self._events.publish(event)
        return IssuedApiKey(api_key=api_key, plaintext=raw)

    async def list_keys(
        self, actor: Principal, tenant_id: str, *, page: PageParams
    ) -> Page[ApiKey]:
        self._authorize_tenant(actor, tenant_id)
        await self._require_tenant(tenant_id)
        return await self._api_keys.list_by_tenant(tenant_id, page=page)

    async def revoke_key(self, actor: Principal, tenant_id: str, api_key_id: str) -> ApiKey:
        self._authorize_tenant(actor, tenant_id)
        api_key = await self._api_keys.get(api_key_id)
        if api_key is None or api_key.tenant_id != tenant_id:
            raise NotFoundError("api_key", api_key_id)
        event = api_key.revoke()
        await self._api_keys.update(api_key)
        await self._events.publish(event)
        return api_key
