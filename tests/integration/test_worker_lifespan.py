from __future__ import annotations

import asyncio
import os
from typing import ClassVar

import pytest

from flux.worker.app import create_worker_app
from flux.worker.config import WorkerSettings
from flux.worker.registration import RegistrationClient


@pytest.fixture(autouse=True)
def _clean_worker_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("FLUX_WORKER_"):
            monkeypatch.delenv(key, raising=False)


class _FakeRegistration:
    calls: ClassVar[list[str]] = []

    def __init__(self, **kwargs: object) -> None:
        type(self).calls = []

    async def register(self) -> None:
        type(self).calls.append("register")

    async def heartbeat(self) -> None:
        type(self).calls.append("heartbeat")

    async def deregister(self) -> None:
        type(self).calls.append("deregister")

    async def aclose(self) -> None:
        type(self).calls.append("aclose")


async def test_worker_selfregisters_on_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("flux.worker.app.RegistrationClient", _FakeRegistration)

    async def _fake_retry(client: RegistrationClient, *, retries: int, delay: float) -> bool:
        await client.register()
        return True

    monkeypatch.setattr("flux.worker.app.register_with_retry", _fake_retry)

    settings = WorkerSettings(
        worker_name="w1",
        control_plane_url="http://control-plane",
        advertise_url="http://w1:8090",
        api_key="worker-key",
        heartbeat_interval_seconds=0.01,
    )
    app = create_worker_app(settings)

    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.03)

    assert "register" in _FakeRegistration.calls
    assert "deregister" in _FakeRegistration.calls
    assert "aclose" in _FakeRegistration.calls


async def test_worker_skips_registration_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = {"n": 0}

    class _ShouldNotBeUsed:
        def __init__(self, **kwargs: object) -> None:
            created["n"] += 1

    monkeypatch.setattr("flux.worker.app.RegistrationClient", _ShouldNotBeUsed)

    settings = WorkerSettings(_env_file=None, worker_name="w1")
    app = create_worker_app(settings)
    async with app.router.lifespan_context(app):
        pass
    assert created["n"] == 0
