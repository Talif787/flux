from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from flux.auth.domain import Role
from flux.tenancy.application import IssuedApiKey
from flux.tenancy.domain import ApiKey, Tenant


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class TenantResponse(BaseModel):
    id: str
    name: str
    status: str
    created_at: datetime

    @classmethod
    def from_domain(cls, tenant: Tenant) -> TenantResponse:
        return cls(
            id=tenant.id,
            name=tenant.name,
            status=tenant.status.value,
            created_at=tenant.created_at,
        )


class ApiKeyIssueRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    roles: list[Role] = Field(min_length=1)


class ApiKeyResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    prefix: str
    roles: list[str]
    status: str
    created_at: datetime
    revoked_at: datetime | None

    @classmethod
    def from_domain(cls, api_key: ApiKey) -> ApiKeyResponse:
        return cls(
            id=api_key.id,
            tenant_id=api_key.tenant_id,
            name=api_key.name,
            prefix=api_key.prefix,
            roles=sorted(api_key.roles),
            status=api_key.status.value,
            created_at=api_key.created_at,
            revoked_at=api_key.revoked_at,
        )


class ApiKeyIssuedResponse(ApiKeyResponse):
    """Issue response: includes the plaintext key, returned exactly once."""

    api_key: str

    @classmethod
    def from_issued(cls, issued: IssuedApiKey) -> ApiKeyIssuedResponse:
        base = ApiKeyResponse.from_domain(issued.api_key)
        return cls(**base.model_dump(), api_key=issued.plaintext)


class PageMeta(BaseModel):
    total: int
    limit: int
    offset: int


class TenantListResponse(BaseModel):
    items: list[TenantResponse]
    meta: PageMeta


class ApiKeyListResponse(BaseModel):
    items: list[ApiKeyResponse]
    meta: PageMeta
