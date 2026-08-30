from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from flux.api.deps import get_session
from flux.auth.dependencies import require_roles
from flux.auth.domain import Principal, Role
from flux.pagination import DEFAULT_LIMIT, MAX_LIMIT, PageParams
from flux.workers.application import WorkerRegistry
from flux.workers.persistence import SqlAlchemyWorkerRepository
from flux.workers.schemas import (
    PageMeta,
    WorkerListResponse,
    WorkerRegisterRequest,
    WorkerResponse,
)

router = APIRouter(prefix="/v1/workers", tags=["workers"])

LimitQuery = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
OffsetQuery = Annotated[int, Query(ge=0)]

WorkerManager = Annotated[Principal, Depends(require_roles(Role.WORKER))]


def get_worker_registry(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WorkerRegistry:
    return WorkerRegistry(SqlAlchemyWorkerRepository(session))


WorkerSvc = Annotated[WorkerRegistry, Depends(get_worker_registry)]


@router.put("/{worker_id}", response_model=WorkerResponse)
async def register_worker(
    worker_id: str,
    payload: WorkerRegisterRequest,
    _: WorkerManager,
    service: WorkerSvc,
) -> WorkerResponse:
    worker = await service.register(
        worker_id,
        name=payload.name,
        base_url=payload.base_url,
        served_models=payload.served_models,
        max_concurrency=payload.max_concurrency,
    )
    return WorkerResponse.from_domain(worker)


@router.post("/{worker_id}/heartbeat", response_model=WorkerResponse)
async def heartbeat(worker_id: str, _: WorkerManager, service: WorkerSvc) -> WorkerResponse:
    return WorkerResponse.from_domain(await service.heartbeat(worker_id))


@router.delete("/{worker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deregister_worker(worker_id: str, _: WorkerManager, service: WorkerSvc) -> Response:
    await service.deregister(worker_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=WorkerListResponse)
async def list_workers(
    _: WorkerManager,
    service: WorkerSvc,
    limit: LimitQuery = DEFAULT_LIMIT,
    offset: OffsetQuery = 0,
) -> WorkerListResponse:
    page = await service.list_workers(PageParams(limit=limit, offset=offset))
    return WorkerListResponse(
        items=[WorkerResponse.from_domain(w) for w in page.items],
        meta=PageMeta(total=page.total, limit=page.limit, offset=page.offset),
    )
