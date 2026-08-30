from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from flux.events import EventBus
from flux.serving.domain import InferenceEngine, RateLimiter, Scheduler


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session (session-per-request)."""
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        yield session


def get_event_bus(request: Request) -> EventBus:
    bus: EventBus = request.app.state.event_bus
    return bus


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


def get_scheduler(request: Request) -> Scheduler:
    scheduler: Scheduler = request.app.state.scheduler
    return scheduler


def get_inference_engine(request: Request) -> InferenceEngine:
    engine: InferenceEngine = request.app.state.inference_engine
    return engine
