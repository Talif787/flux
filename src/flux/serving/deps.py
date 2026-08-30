from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from flux.api.deps import (
    get_inference_engine,
    get_rate_limiter,
    get_scheduler,
    get_session,
    get_worker_selector,
)
from flux.config import Settings, get_settings
from flux.metering.persistence import SqlAlchemyUsageRecorder
from flux.serving.application import InferenceService
from flux.serving.domain import (
    IdempotencyStore,
    InferenceEngine,
    ModelCatalog,
    RateLimiter,
    Router,
    Scheduler,
    UsageRecorder,
)
from flux.serving.persistence import (
    SqlAlchemyIdempotencyStore,
    SqlAlchemyModelCatalog,
    SqlAlchemyWorkerDirectory,
)
from flux.serving.routing import RegistryRouter, RoundRobinSelector, StaticRouter


def get_model_catalog(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ModelCatalog:
    return SqlAlchemyModelCatalog(session)


def get_idempotency_store(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IdempotencyStore:
    return SqlAlchemyIdempotencyStore(session)


def get_usage_recorder(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UsageRecorder:
    return SqlAlchemyUsageRecorder(session)


def get_inference_service(
    engine: Annotated[InferenceEngine, Depends(get_inference_engine)],
    scheduler: Annotated[Scheduler, Depends(get_scheduler)],
    rate_limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    catalog: Annotated[ModelCatalog, Depends(get_model_catalog)],
    session: Annotated[AsyncSession, Depends(get_session)],
    selector: Annotated[RoundRobinSelector, Depends(get_worker_selector)],
    usage_recorder: Annotated[UsageRecorder, Depends(get_usage_recorder)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> InferenceService:
    router: Router
    if settings.serving_backend == "remote":
        directory = SqlAlchemyWorkerDirectory(session, settings.worker_heartbeat_ttl_seconds)
        router = RegistryRouter(directory, selector)
    else:
        router = StaticRouter()
    return InferenceService(
        engine=engine,
        router=router,
        scheduler=scheduler,
        rate_limiter=rate_limiter,
        catalog=catalog,
        usage_recorder=usage_recorder,
        rate_limit_enabled=settings.rate_limit_enabled,
        metering_enabled=settings.metering_enabled,
    )
