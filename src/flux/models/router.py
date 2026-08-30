from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from flux.api.deps import get_event_bus, get_session
from flux.auth.dependencies import get_current_principal
from flux.auth.domain import Principal
from flux.events import EventBus
from flux.models.application import (
    ModelService,
    RegisterModelCommand,
    RegisterModelVersionCommand,
)
from flux.models.persistence import SqlAlchemyModelRepository
from flux.models.schemas import (
    ModelCreateRequest,
    ModelListResponse,
    ModelResponse,
    ModelVersionCreateRequest,
    ModelVersionListResponse,
    ModelVersionResponse,
    PageMeta,
)
from flux.pagination import DEFAULT_LIMIT, MAX_LIMIT, PageParams

router = APIRouter(prefix="/v1/models", tags=["models"])

LimitQuery = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
OffsetQuery = Annotated[int, Query(ge=0)]


def get_model_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    event_bus: Annotated[EventBus, Depends(get_event_bus)],
) -> ModelService:
    return ModelService(SqlAlchemyModelRepository(session), event_bus)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ModelResponse)
async def register_model(
    payload: ModelCreateRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ModelService, Depends(get_model_service)],
) -> ModelResponse:
    model = await service.register_model(
        RegisterModelCommand(
            tenant_id=principal.tenant_id, name=payload.name, family=payload.family
        )
    )
    return ModelResponse.from_domain(model)


@router.get("", response_model=ModelListResponse)
async def list_models(
    principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ModelService, Depends(get_model_service)],
    family: str | None = None,
    limit: LimitQuery = DEFAULT_LIMIT,
    offset: OffsetQuery = 0,
) -> ModelListResponse:
    page = await service.list_models(
        principal.tenant_id, family=family, page=PageParams(limit=limit, offset=offset)
    )
    return ModelListResponse(
        items=[ModelResponse.from_domain(m) for m in page.items],
        meta=PageMeta(total=page.total, limit=page.limit, offset=page.offset),
    )


@router.get("/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: str,
    principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ModelService, Depends(get_model_service)],
) -> ModelResponse:
    model = await service.get_model(principal.tenant_id, model_id)
    return ModelResponse.from_domain(model)


@router.post(
    "/{model_id}/versions",
    status_code=status.HTTP_201_CREATED,
    response_model=ModelVersionResponse,
)
async def register_version(
    model_id: str,
    payload: ModelVersionCreateRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ModelService, Depends(get_model_service)],
) -> ModelVersionResponse:
    version = await service.register_version(
        RegisterModelVersionCommand(
            tenant_id=principal.tenant_id,
            model_id=model_id,
            version=payload.version,
            precision=payload.precision,
            context_length=payload.context_length,
        )
    )
    return ModelVersionResponse.from_domain(version)


@router.get("/{model_id}/versions", response_model=ModelVersionListResponse)
async def list_versions(
    model_id: str,
    principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ModelService, Depends(get_model_service)],
    limit: LimitQuery = DEFAULT_LIMIT,
    offset: OffsetQuery = 0,
) -> ModelVersionListResponse:
    page = await service.list_versions(
        principal.tenant_id, model_id, page=PageParams(limit=limit, offset=offset)
    )
    return ModelVersionListResponse(
        items=[ModelVersionResponse.from_domain(v) for v in page.items],
        meta=PageMeta(total=page.total, limit=page.limit, offset=page.offset),
    )
