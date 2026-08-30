from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class ApiKeyStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class Role(StrEnum):
    """Canonical role vocabulary for the control plane.

    PLATFORM_ADMIN is a superuser: it satisfies every role check and may act
    across all tenants. The remaining roles are tenant-scoped capabilities.
    """

    PLATFORM_ADMIN = "platform.admin"
    TENANT_ADMIN = "tenant.admin"
    MODEL_READ = "model.read"
    MODEL_WRITE = "model.write"


@dataclass(frozen=True)
class Principal:
    """The authenticated caller: a tenant identity plus its granted roles."""

    tenant_id: str
    api_key_id: str
    roles: frozenset[str] = field(default_factory=frozenset)

    def has_role(self, role: str) -> bool:
        return role in self.roles

    @property
    def is_platform_admin(self) -> bool:
        return Role.PLATFORM_ADMIN in self.roles
