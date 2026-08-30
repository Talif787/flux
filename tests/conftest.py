from __future__ import annotations

import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from flux.api import deps
from flux.api.app import create_app
from flux.auth.hashing import hash_api_key, key_prefix
from flux.auth.persistence import ApiKeyRow, TenantRow
from flux.config import Settings, get_settings
from flux.db import Base, create_engine, create_sessionmaker
from flux.events import InProcessEventBus
from flux.ids import new_id
from flux.serving.engine import StubInferenceEngine
from flux.serving.ratelimit import TokenBucketRateLimiter
from flux.serving.scheduling import SemaphoreScheduler

TEST_PEPPER = "test-pepper"

# A factory that provisions a tenant + key with given roles and returns
# (plaintext_key, tenant_id).
KeyFactory = Callable[..., Awaitable[tuple[str, str]]]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env="local",
        database_url="sqlite+aiosqlite:///:memory:",
        api_key_pepper=TEST_PEPPER,
        log_json=False,
        otel_enabled=False,
    )


@pytest_asyncio.fixture
async def sessionmaker(
    settings: Settings,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield create_sessionmaker(engine)
    await engine.dispose()


@pytest_asyncio.fixture
async def key_factory(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> KeyFactory:
    async def _make(
        roles: str,
        *,
        tenant_id: str | None = None,
        tenant_status: str = "active",
        key_status: str = "active",
    ) -> tuple[str, str]:
        raw = "flux_" + secrets.token_urlsafe(16)
        now = datetime.now(UTC)
        tid = tenant_id or new_id()
        async with sessionmaker() as session:
            if tenant_id is None:
                session.add(
                    TenantRow(
                        id=tid,
                        name=f"t-{tid[:8]}",
                        status=tenant_status,
                        created_at=now,
                    )
                )
            session.add(
                ApiKeyRow(
                    id=new_id(),
                    tenant_id=tid,
                    key_hash=hash_api_key(raw, TEST_PEPPER),
                    name="test-key",
                    prefix=key_prefix(raw),
                    roles=roles,
                    status=key_status,
                    created_at=now,
                )
            )
            await session.commit()
        return raw, tid

    return _make


@pytest_asyncio.fixture
async def api_key(key_factory: KeyFactory) -> str:
    raw, _ = await key_factory("model.read,model.write")
    return raw


@pytest_asyncio.fixture
async def admin_key(key_factory: KeyFactory) -> str:
    raw, _ = await key_factory("platform.admin")
    return raw


@pytest_asyncio.fixture
async def app(
    settings: Settings, sessionmaker: async_sessionmaker[AsyncSession]
) -> AsyncIterator[FastAPI]:
    """A wired application whose request-plane singletons live on app.state.

    Tests that need to constrain the request plane (a tight rate limiter or a
    saturated scheduler) can override the serving dependencies on this object
    before issuing a request.
    """
    application = create_app(settings)
    application.state.sessionmaker = sessionmaker
    application.state.event_bus = InProcessEventBus()
    application.state.rate_limiter = TokenBucketRateLimiter(rps=1000, burst=1000)
    application.state.scheduler = SemaphoreScheduler(max_concurrency=64, max_queue=128)
    application.state.inference_engine = StubInferenceEngine()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    application.dependency_overrides[deps.get_session] = _session_override
    application.dependency_overrides[deps.get_event_bus] = lambda: application.state.event_bus
    application.dependency_overrides[get_settings] = lambda: settings
    yield application
    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
