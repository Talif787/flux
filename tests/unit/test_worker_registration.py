from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable

import httpx
import pytest

from flux.worker.config import WorkerSettings
from flux.worker.registration import (
    RegistrationClient,
    heartbeat_loop,
    register_with_retry,
)

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def _clean_worker_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("FLUX_WORKER_"):
            monkeypatch.delenv(key, raising=False)


_WORKER_RESPONSE = {
    "id": "w1",
    "name": "w1",
    "base_url": "http://w1:8090",
    "served_models": ["gpt-stub"],
    "max_concurrency": 8,
    "status": "active",
    "registered_at": "2026-01-01T00:00:00Z",
    "last_heartbeat_at": "2026-01-01T00:00:00Z",
}


def _client(handler: Handler) -> RegistrationClient:
    http = httpx.AsyncClient(
        base_url="http://control-plane",
        headers={"Authorization": "Bearer worker-key"},
        transport=httpx.MockTransport(handler),
    )
    return RegistrationClient(
        control_plane_url="http://control-plane",
        api_key="worker-key",
        worker_id="w1",
        name="w1",
        advertise_url="http://w1:8090",
        served_models=["gpt-stub"],
        max_concurrency=8,
        client=http,
    )


async def test_register_puts_correct_payload() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_WORKER_RESPONSE)

    await _client(handler).register()

    assert seen["method"] == "PUT"
    assert seen["url"] == "http://control-plane/v1/workers/w1"
    assert seen["auth"] == "Bearer worker-key"
    assert seen["body"] == {
        "name": "w1",
        "base_url": "http://w1:8090",
        "served_models": ["gpt-stub"],
        "max_concurrency": 8,
    }


async def test_heartbeat_posts_to_worker() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        return httpx.Response(200, json=_WORKER_RESPONSE)

    await _client(handler).heartbeat()
    assert seen["method"] == "POST"
    assert seen["url"] == "http://control-plane/v1/workers/w1/heartbeat"


async def test_deregister_swallows_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    await _client(handler).deregister()  # must not raise on 500


async def test_register_with_retry_succeeds_after_failures() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=_WORKER_RESPONSE)

    ok = await register_with_retry(_client(handler), retries=5, delay=0.0)
    assert ok is True
    assert attempts["n"] == 3


async def test_register_with_retry_gives_up() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    ok = await register_with_retry(_client(handler), retries=2, delay=0.0)
    assert ok is False


async def test_heartbeat_loop_reregisters_on_404() -> None:
    events: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/heartbeat"):
            events.append("heartbeat")
            return httpx.Response(404)
        events.append("register")
        return httpx.Response(200, json=_WORKER_RESPONSE)

    task = asyncio.create_task(heartbeat_loop(_client(handler), interval=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert "heartbeat" in events
    assert "register" in events  # a 404 heartbeat triggered a re-register


def test_registration_enabled_requires_all_three() -> None:
    assert WorkerSettings(_env_file=None).registration_enabled is False
    assert (
        WorkerSettings(
            control_plane_url="http://cp",
            advertise_url="http://w:8090",
            api_key="k",
        ).registration_enabled
        is True
    )
    assert (
        WorkerSettings(
            control_plane_url="http://cp", advertise_url="http://w:8090"
        ).registration_enabled
        is False
    )


def test_effective_worker_id_defaults_to_name() -> None:
    assert WorkerSettings(worker_name="alpha").effective_worker_id == "alpha"
    assert WorkerSettings(worker_name="alpha", worker_id="alpha-1").effective_worker_id == "alpha-1"
