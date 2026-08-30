from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from flux.worker.app import create_worker_app
from flux.worker.backend import EchoBackend
from flux.worker.config import WorkerSettings, get_worker_settings


def build_worker_client(settings: WorkerSettings) -> tuple[FastAPI, AsyncClient]:
    """Build a worker app with its backend wired and settings overridden.

    Lifespan does not run under ASGITransport, so the backend is placed on
    app.state directly, mirroring how the control-plane tests are wired.
    """
    app = create_worker_app(settings)
    app.state.backend = EchoBackend()
    app.dependency_overrides[get_worker_settings] = lambda: settings
    transport = ASGITransport(app=app)
    return app, AsyncClient(transport=transport, base_url="http://worker")


@pytest.fixture
def worker_settings() -> WorkerSettings:
    return WorkerSettings(backend="echo", served_models="gpt-stub,llama-3-8b")


@pytest_asyncio.fixture
async def worker_client(
    worker_settings: WorkerSettings,
) -> AsyncIterator[AsyncClient]:
    app, client = build_worker_client(worker_settings)
    async with client as ac:
        yield ac
    app.dependency_overrides.clear()
