from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from flux.api.deps import get_event_bus, get_session
from flux.auth.dependencies import require_roles
from flux.auth.domain import Principal, Role
from flux.auth.hashing import hash_api_key
from flux.config import Settings, get_settings
from flux.events import EventBus
from flux.pagination import DEFAULT_LIMIT, MAX_LIMIT, PageParams
from flux.tenancy.application import ApiKeyService, TenantService
from flux.tenancy.persistence import (
    SqlAlchemyApiKeyRepository,
    SqlAlchemyTenantRepository,
)
from flux.tenancy.schemas import (
    ApiKeyIssuedResponse,
    ApiKeyIssueRequest,
    ApiKeyListResponse,
    ApiKeyResponse,
    PageMeta,
    TenantCreateRequest,
    TenantListResponse,
    TenantResponse,
)

router = APIRouter(prefix="/v1/tenants", tags=["tenancy"])

LimitQuery = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
OffsetQuery = Annotated[int, Query(ge=0)]

PlatformAdmin = Annotated[Principal, Depends(require_roles(Role.PLATFORM_ADMIN))]
KeyManager = Annotated[Principal, Depends(require_roles(Role.PLATFORM_ADMIN, Role.TENANT_ADMIN))]


def get_tenant_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    event_bus: Annotated[EventBus, Depends(get_event_bus)],
) -> TenantService:
    return TenantService(SqlAlchemyTenantRepository(session), event_bus)


def get_api_key_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    event_bus: Annotated[EventBus, Depends(get_event_bus)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApiKeyService:
    def hasher(raw: str) -> str:
        return hash_api_key(raw, settings.api_key_pepper)

    return ApiKeyService(
        SqlAlchemyApiKeyRepository(session),
        SqlAlchemyTenantRepository(session),
        event_bus,
        hasher,
    )


TenantSvc = Annotated[TenantService, Depends(get_tenant_service)]
ApiKeySvc = Annotated[ApiKeyService, Depends(get_api_key_service)]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TenantResponse)
async def create_tenant(
    payload: TenantCreateRequest, _: PlatformAdmin, service: TenantSvc
) -> TenantResponse:
    tenant = await service.create_tenant(payload.name)
    return TenantResponse.from_domain(tenant)


@router.get("", response_model=TenantListResponse)
async def list_tenants(
    _: PlatformAdmin,
    service: TenantSvc,
    limit: LimitQuery = DEFAULT_LIMIT,
    offset: OffsetQuery = 0,
) -> TenantListResponse:
    page = await service.list_tenants(page=PageParams(limit=limit, offset=offset))
    return TenantListResponse(
        items=[TenantResponse.from_domain(t) for t in page.items],
        meta=PageMeta(total=page.total, limit=page.limit, offset=page.offset),
    )


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: str, _: PlatformAdmin, service: TenantSvc) -> TenantResponse:
    return TenantResponse.from_domain(await service.get_tenant(tenant_id))


@router.post("/{tenant_id}/suspend", response_model=TenantResponse)
async def suspend_tenant(tenant_id: str, _: PlatformAdmin, service: TenantSvc) -> TenantResponse:
    return TenantResponse.from_domain(await service.suspend_tenant(tenant_id))


@router.post("/{tenant_id}/reactivate", response_model=TenantResponse)
async def reactivate_tenant(tenant_id: str, _: PlatformAdmin, service: TenantSvc) -> TenantResponse:
    return TenantResponse.from_domain(await service.reactivate_tenant(tenant_id))


@router.post(
    "/{tenant_id}/api-keys",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiKeyIssuedResponse,
)
async def issue_api_key(
    tenant_id: str,
    payload: ApiKeyIssueRequest,
    principal: KeyManager,
    service: ApiKeySvc,
) -> ApiKeyIssuedResponse:
    issued = await service.issue_key(
        principal, tenant_id, payload.name, [r.value for r in payload.roles]
    )
    return ApiKeyIssuedResponse.from_issued(issued)


@router.get("/{tenant_id}/api-keys", response_model=ApiKeyListResponse)
async def list_api_keys(
    tenant_id: str,
    principal: KeyManager,
    service: ApiKeySvc,
    limit: LimitQuery = DEFAULT_LIMIT,
    offset: OffsetQuery = 0,
) -> ApiKeyListResponse:
    page = await service.list_keys(
        principal, tenant_id, page=PageParams(limit=limit, offset=offset)
    )
    return ApiKeyListResponse(
        items=[ApiKeyResponse.from_domain(k) for k in page.items],
        meta=PageMeta(total=page.total, limit=page.limit, offset=page.offset),
    )


@router.post("/{tenant_id}/api-keys/{api_key_id}/revoke", response_model=ApiKeyResponse)
async def revoke_api_key(
    tenant_id: str, api_key_id: str, principal: KeyManager, service: ApiKeySvc
) -> ApiKeyResponse:
    api_key = await service.revoke_key(principal, tenant_id, api_key_id)
    return ApiKeyResponse.from_domain(api_key)
