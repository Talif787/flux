from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from flux.api.deps import (
    get_inference_engine,
    get_rate_limiter,
    get_scheduler,
    get_session,
)
from flux.config import Settings, get_settings
from flux.serving.application import InferenceService
from flux.serving.domain import (
    IdempotencyStore,
    InferenceEngine,
    ModelCatalog,
    RateLimiter,
    Scheduler,
)
from flux.serving.persistence import (
    SqlAlchemyIdempotencyStore,
    SqlAlchemyModelCatalog,
)
from flux.serving.routing import StaticRouter


def get_model_catalog(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ModelCatalog:
    return SqlAlchemyModelCatalog(session)


def get_idempotency_store(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IdempotencyStore:
    return SqlAlchemyIdempotencyStore(session)


def get_inference_service(
    engine: Annotated[InferenceEngine, Depends(get_inference_engine)],
    scheduler: Annotated[Scheduler, Depends(get_scheduler)],
    rate_limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    catalog: Annotated[ModelCatalog, Depends(get_model_catalog)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> InferenceService:
    return InferenceService(
        engine=engine,
        router=StaticRouter(),
        scheduler=scheduler,
        rate_limiter=rate_limiter,
        catalog=catalog,
        rate_limit_enabled=settings.rate_limit_enabled,
    )
