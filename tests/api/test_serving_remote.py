from __future__ import annotations

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from flux.config import Settings, get_settings
from flux.serving.remote import RemoteInferenceEngine
from flux.worker.app import create_worker_app
from flux.worker.backend import EchoBackend
from flux.worker.config import WorkerSettings, get_worker_settings
from tests.conftest import TEST_PEPPER, KeyFactory

WORKER_ENDPOINT = "http://worker.internal"


def _auth(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _remote_settings() -> Settings:
    return Settings(
        env="local",
        database_url="sqlite+aiosqlite:///:memory:",
        api_key_pepper=TEST_PEPPER,
        log_json=False,
        otel_enabled=False,
        serving_backend="remote",
        worker_heartbeat_ttl_seconds=300,
    )


def _worker_app() -> FastAPI:
    settings = WorkerSettings(backend="echo", served_models="gpt-stub")
    app = create_worker_app(settings)
    app.state.backend = EchoBackend()
    app.dependency_overrides[get_worker_settings] = lambda: settings
    return app


def _wire_remote(app: FastAPI, worker_app: FastAPI) -> None:
    """Flip the shared control-plane app into remote mode for one test.

    Lifespan does not run under ASGITransport, so we set the remote engine on
    app.state directly and point its client factory at the in-process worker.
    """
    app.dependency_overrides[get_settings] = lambda: _remote_settings()

    def factory(endpoint: str) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=worker_app), base_url=WORKER_ENDPOINT)

    app.state.inference_engine = RemoteInferenceEngine(factory)


async def _register_worker(client: AsyncClient, api_key: str, worker_id: str = "w-1") -> None:
    resp = await client.put(
        f"/v1/workers/{worker_id}",
        json={
            "name": worker_id,
            "base_url": WORKER_ENDPOINT,
            "served_models": ["gpt-stub"],
        },
        headers=_auth(api_key),
    )
    assert resp.status_code == 200


async def _register_model(client: AsyncClient, api_key: str) -> None:
    resp = await client.post(
        "/v1/models",
        json={"name": "gpt-stub", "family": "stub"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201


async def test_gateway_routes_completion_to_registered_worker(
    app: FastAPI, client: AsyncClient, key_factory: KeyFactory
) -> None:
    _wire_remote(app, _worker_app())
    raw, _ = await key_factory("model.write,inference.invoke,worker.register")
    await _register_worker(client, raw)
    await _register_model(client, raw)

    resp = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-stub",
            "messages": [{"role": "user", "content": "hello remote"}],
        },
        headers=_auth(raw),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "gpt-stub"
    # The worker (not the in-process stub) produced this content.
    assert "worker echo" in body["choices"][0]["message"]["content"]


async def test_gateway_streams_from_registered_worker(
    app: FastAPI, client: AsyncClient, key_factory: KeyFactory
) -> None:
    _wire_remote(app, _worker_app())
    raw, _ = await key_factory("model.write,inference.invoke,worker.register")
    await _register_worker(client, raw)
    await _register_model(client, raw)

    resp = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-stub",
            "messages": [{"role": "user", "content": "stream remote"}],
            "stream": True,
        },
        headers=_auth(raw),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert "chat.completion.chunk" in resp.text
    assert "[DONE]" in resp.text


async def test_gateway_returns_503_when_no_worker_registered(
    app: FastAPI, client: AsyncClient, key_factory: KeyFactory
) -> None:
    _wire_remote(app, _worker_app())
    raw, _ = await key_factory("model.write,inference.invoke")
    await _register_model(client, raw)

    resp = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-stub",
            "messages": [{"role": "user", "content": "anyone home"}],
        },
        headers=_auth(raw),
    )
    assert resp.status_code == 503
    assert resp.json()["title"] == "Service Unavailable"


async def test_gateway_returns_404_when_model_not_registered(
    app: FastAPI, client: AsyncClient, key_factory: KeyFactory
) -> None:
    _wire_remote(app, _worker_app())
    raw, _ = await key_factory("model.write,inference.invoke,worker.register")
    await _register_worker(client, raw)

    resp = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-stub",
            "messages": [{"role": "user", "content": "unregistered model"}],
        },
        headers=_auth(raw),
    )
    assert resp.status_code == 404
