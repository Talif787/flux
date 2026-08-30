from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from flux.auth.domain import ApiKeyStatus, Role, TenantStatus
from flux.errors import DomainError
from flux.events import DomainEvent
from flux.ids import new_id
from flux.pagination import Page, PageParams

MAX_NAME_LENGTH = 255
_VALID_ROLES = {r.value for r in Role}


@dataclass(frozen=True, kw_only=True)
class TenantCreated(DomainEvent):
    tenant_id: str
    name: str


@dataclass(frozen=True, kw_only=True)
class TenantSuspended(DomainEvent):
    tenant_id: str


@dataclass(frozen=True, kw_only=True)
class TenantReactivated(DomainEvent):
    tenant_id: str


@dataclass(frozen=True, kw_only=True)
class ApiKeyIssued(DomainEvent):
    api_key_id: str
    tenant_id: str


@dataclass(frozen=True, kw_only=True)
class ApiKeyRevoked(DomainEvent):
    api_key_id: str
    tenant_id: str


@dataclass
class Tenant:
    """Aggregate root: an isolated customer or team owning models and keys."""

    id: str
    name: str
    status: TenantStatus
    created_at: datetime

    @staticmethod
    def create(name: str) -> tuple[Tenant, TenantCreated]:
        clean = name.strip()
        if not clean:
            raise DomainError("tenant name must not be empty")
        if len(clean) > MAX_NAME_LENGTH:
            raise DomainError("tenant name too long")
        tenant = Tenant(
            id=new_id(),
            name=clean,
            status=TenantStatus.ACTIVE,
            created_at=datetime.now(UTC),
        )
        return tenant, TenantCreated(tenant_id=tenant.id, name=clean)

    def suspend(self) -> TenantSuspended:
        if self.status is TenantStatus.SUSPENDED:
            raise DomainError("tenant already suspended")
        self.status = TenantStatus.SUSPENDED
        return TenantSuspended(tenant_id=self.id)

    def reactivate(self) -> TenantReactivated:
        if self.status is TenantStatus.ACTIVE:
            raise DomainError("tenant already active")
        self.status = TenantStatus.ACTIVE
        return TenantReactivated(tenant_id=self.id)


@dataclass
class ApiKey:
    """Aggregate root: a credential granting a set of roles within a tenant.

    The secret itself is never held here; only its non-secret display prefix.
    The hash is a persistence concern handled by the repository.
    """

    id: str
    tenant_id: str
    name: str
    prefix: str
    roles: frozenset[str]
    status: ApiKeyStatus
    created_at: datetime
    revoked_at: datetime | None = field(default=None)

    @staticmethod
    def issue(
        *, tenant_id: str, name: str, prefix: str, roles: Iterable[str]
    ) -> tuple[ApiKey, ApiKeyIssued]:
        clean_name = name.strip()
        if not clean_name:
            raise DomainError("api key name must not be empty")
        role_set = frozenset(roles)
        unknown = role_set - _VALID_ROLES
        if unknown:
            raise DomainError(f"unknown roles: {sorted(unknown)}")
        api_key = ApiKey(
            id=new_id(),
            tenant_id=tenant_id,
            name=clean_name,
            prefix=prefix,
            roles=role_set,
            status=ApiKeyStatus.ACTIVE,
            created_at=datetime.now(UTC),
        )
        return api_key, ApiKeyIssued(api_key_id=api_key.id, tenant_id=tenant_id)

    def revoke(self) -> ApiKeyRevoked:
        if self.status is ApiKeyStatus.REVOKED:
            raise DomainError("api key already revoked")
        self.status = ApiKeyStatus.REVOKED
        self.revoked_at = datetime.now(UTC)
        return ApiKeyRevoked(api_key_id=self.id, tenant_id=self.tenant_id)


class TenantRepository(Protocol):
    async def add(self, tenant: Tenant) -> None: ...
    async def get(self, tenant_id: str) -> Tenant | None: ...
    async def get_by_name(self, name: str) -> Tenant | None: ...
    async def list(self, *, page: PageParams) -> Page[Tenant]: ...
    async def update(self, tenant: Tenant) -> None: ...


class ApiKeyRepository(Protocol):
    async def add(self, api_key: ApiKey, *, key_hash: str) -> None: ...
    async def get(self, api_key_id: str) -> ApiKey | None: ...
    async def list_by_tenant(self, tenant_id: str, *, page: PageParams) -> Page[ApiKey]: ...
    async def update(self, api_key: ApiKey) -> None: ...
