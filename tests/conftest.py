from __future__ import annotations

import secrets
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from flux.api import deps
from flux.api.app import create_app
from flux.auth.dependencies import hash_api_key
from flux.auth.persistence import ApiKeyRow, TenantRow
from flux.config import Settings, get_settings
from flux.db import Base, create_engine, create_sessionmaker
from flux.events import InProcessEventBus
from flux.ids import new_id

TEST_PEPPER = "test-pepper"


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
async def api_key(sessionmaker: async_sessionmaker[AsyncSession]) -> str:
    raw = "flux_" + secrets.token_urlsafe(16)
    async with sessionmaker() as session:
        tenant = TenantRow(id=new_id(), name="test", status="active")
        session.add(tenant)
        session.add(
            ApiKeyRow(
                id=new_id(),
                tenant_id=tenant.id,
                key_hash=hash_api_key(raw, TEST_PEPPER),
                roles="model.read,model.write",
                status="active",
            )
        )
        await session.commit()
    return raw


@pytest_asyncio.fixture
async def client(
    settings: Settings, sessionmaker: async_sessionmaker[AsyncSession]
) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    app.state.sessionmaker = sessionmaker
    app.state.event_bus = InProcessEventBus()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[deps.get_session] = _session_override
    app.dependency_overrides[deps.get_event_bus] = lambda: app.state.event_bus
    app.dependency_overrides[get_settings] = lambda: settings

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
