from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from flux.errors import UpstreamError
from flux.serving.domain import (
    ChatMessage,
    ChatRole,
    InferenceRequest,
    RouteTarget,
    SamplingParams,
)
from flux.serving.remote import RemoteInferenceEngine
from flux.worker.app import create_worker_app
from flux.worker.backend import EchoBackend
from flux.worker.config import WorkerSettings, get_worker_settings

WORKER_ENDPOINT = "http://worker.internal"


def _worker_app() -> FastAPI:
    settings = WorkerSettings(backend="echo", served_models="gpt-stub")
    app = create_worker_app(settings)
    app.state.backend = EchoBackend()
    app.dependency_overrides[get_worker_settings] = lambda: settings
    return app


def _engine(worker_app: FastAPI) -> RemoteInferenceEngine:
    def factory(endpoint: str) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=worker_app), base_url=WORKER_ENDPOINT)

    return RemoteInferenceEngine(factory)


def _request(model_name: str = "gpt-stub") -> InferenceRequest:
    return InferenceRequest(
        tenant_id="t-1",
        model_id="m-1",
        model_name=model_name,
        messages=(ChatMessage(role=ChatRole.USER, content="hello worker"),),
        sampling=SamplingParams(max_tokens=32),
    )


def _target() -> RouteTarget:
    return RouteTarget(pool_id="w-1", endpoint=WORKER_ENDPOINT, worker_id="w-1")


async def test_generate_calls_worker_and_parses_result() -> None:
    engine = _engine(_worker_app())
    result = await engine.generate(_request(), _target())

    assert "worker echo" in result.content
    assert result.finish_reason.value in {"stop", "length"}
    assert result.usage.total_tokens > 0


async def test_stream_yields_role_content_and_finish() -> None:
    engine = _engine(_worker_app())
    chunks = [chunk async for chunk in engine.stream(_request(), _target())]

    assert any(chunk.role is ChatRole.ASSISTANT for chunk in chunks)
    assert any(chunk.delta for chunk in chunks)
    assert chunks[-1].finish_reason is not None


async def test_unserved_model_maps_to_upstream_error() -> None:
    engine = _engine(_worker_app())
    with pytest.raises(UpstreamError):
        await engine.generate(_request(model_name="not-served"), _target())


async def test_missing_endpoint_maps_to_upstream_error() -> None:
    engine = _engine(_worker_app())
    with pytest.raises(UpstreamError):
        await engine.generate(_request(), RouteTarget(pool_id="w-1"))
