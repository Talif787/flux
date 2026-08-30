from __future__ import annotations

from httpx import AsyncClient

from flux.worker.config import WorkerSettings
from tests.worker.conftest import build_worker_client


async def test_health(worker_client: AsyncClient) -> None:
    assert (await worker_client.get("/livez")).json() == {"status": "ok"}
    ready = await worker_client.get("/readyz")
    assert ready.status_code == 200
    body = ready.json()
    assert body["status"] == "ready"
    assert body["backend"] == "echo"
    assert body["models"] == ["gpt-stub", "llama-3-8b"]


async def test_list_models(worker_client: AsyncClient) -> None:
    resp = await worker_client.get("/v1/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "list"
    assert {m["id"] for m in body["data"]} == {"gpt-stub", "llama-3-8b"}


async def test_chat_completion_happy_path(worker_client: AsyncClient) -> None:
    resp = await worker_client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-stub",
            "messages": [{"role": "user", "content": "hello worker"}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "gpt-stub"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"]
    assert body["choices"][0]["finish_reason"] == "stop"
    usage = body["usage"]
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


async def test_chat_completion_streaming(worker_client: AsyncClient) -> None:
    resp = await worker_client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-stub",
            "messages": [{"role": "user", "content": "stream please"}],
            "stream": True,
        },
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert "chat.completion.chunk" in resp.text
    assert "[DONE]" in resp.text


async def test_chat_completion_max_tokens(worker_client: AsyncClient) -> None:
    resp = await worker_client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-stub",
            "messages": [{"role": "user", "content": "one two three four five"}],
            "max_tokens": 2,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["usage"]["completion_tokens"] == 2
    assert body["choices"][0]["finish_reason"] == "length"


async def test_model_not_served_returns_404(worker_client: AsyncClient) -> None:
    resp = await worker_client.post(
        "/v1/chat/completions",
        json={
            "model": "not-loaded",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert resp.status_code == 404


async def test_empty_served_set_serves_any_model() -> None:
    settings = WorkerSettings(backend="echo", served_models="")
    app, client = build_worker_client(settings)
    async with client as ac:
        resp = await ac.post(
            "/v1/chat/completions",
            json={
                "model": "anything-goes",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["model"] == "anything-goes"
