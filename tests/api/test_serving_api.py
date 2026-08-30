from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import KeyFactory


def _auth(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


async def _register(client: AsyncClient, api_key: str, name: str) -> None:
    resp = await client.post(
        "/v1/models",
        json={"name": name, "family": "stub"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201


async def test_chat_completion_happy_path(client: AsyncClient, key_factory: KeyFactory) -> None:
    raw, _ = await key_factory("model.write,inference.invoke")
    await _register(client, raw, "gpt-stub")

    resp = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-stub",
            "messages": [{"role": "user", "content": "hello there"}],
        },
        headers=_auth(raw),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "gpt-stub"
    choice = body["choices"][0]
    assert choice["message"]["role"] == "assistant"
    assert choice["message"]["content"]
    assert choice["finish_reason"] == "stop"
    usage = body["usage"]
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


async def test_chat_completion_streaming(client: AsyncClient, key_factory: KeyFactory) -> None:
    raw, _ = await key_factory("model.write,inference.invoke")
    await _register(client, raw, "gpt-stub")

    resp = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-stub",
            "messages": [{"role": "user", "content": "stream please"}],
            "stream": True,
        },
        headers=_auth(raw),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert "chat.completion.chunk" in resp.text
    assert "[DONE]" in resp.text


async def test_chat_requires_auth(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/chat/completions",
        json={"model": "x", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 401


async def test_chat_requires_inference_role(client: AsyncClient, key_factory: KeyFactory) -> None:
    raw, _ = await key_factory("model.read")
    resp = await client.post(
        "/v1/chat/completions",
        json={"model": "x", "messages": [{"role": "user", "content": "hi"}]},
        headers=_auth(raw),
    )
    assert resp.status_code == 403


async def test_chat_unknown_model_returns_404(client: AsyncClient, key_factory: KeyFactory) -> None:
    raw, _ = await key_factory("inference.invoke")
    resp = await client.post(
        "/v1/chat/completions",
        json={"model": "nope", "messages": [{"role": "user", "content": "hi"}]},
        headers=_auth(raw),
    )
    assert resp.status_code == 404


async def test_chat_max_tokens_truncates(client: AsyncClient, key_factory: KeyFactory) -> None:
    raw, _ = await key_factory("model.write,inference.invoke")
    await _register(client, raw, "gpt-stub")

    resp = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-stub",
            "messages": [{"role": "user", "content": "one two three four five"}],
            "max_tokens": 2,
        },
        headers=_auth(raw),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["usage"]["completion_tokens"] == 2
    assert body["choices"][0]["finish_reason"] == "length"


async def test_idempotent_replay(client: AsyncClient, key_factory: KeyFactory) -> None:
    raw, _ = await key_factory("model.write,inference.invoke")
    await _register(client, raw, "gpt-stub")
    payload = {
        "model": "gpt-stub",
        "messages": [{"role": "user", "content": "hi"}],
    }
    headers = {**_auth(raw), "Idempotency-Key": "key-1"}

    first = await client.post("/v1/chat/completions", json=payload, headers=headers)
    assert first.status_code == 200
    second = await client.post("/v1/chat/completions", json=payload, headers=headers)
    assert second.status_code == 200
    assert second.headers.get("Idempotent-Replay") == "true"
    assert first.json()["id"] == second.json()["id"]


async def test_idempotency_key_reuse_with_different_body_is_rejected(
    client: AsyncClient, key_factory: KeyFactory
) -> None:
    raw, _ = await key_factory("model.write,inference.invoke")
    await _register(client, raw, "gpt-stub")
    headers = {**_auth(raw), "Idempotency-Key": "key-2"}

    first = await client.post(
        "/v1/chat/completions",
        json={"model": "gpt-stub", "messages": [{"role": "user", "content": "a"}]},
        headers=headers,
    )
    assert first.status_code == 200
    second = await client.post(
        "/v1/chat/completions",
        json={"model": "gpt-stub", "messages": [{"role": "user", "content": "b"}]},
        headers=headers,
    )
    assert second.status_code == 422


async def test_idempotency_record_discarded_on_error(
    client: AsyncClient, key_factory: KeyFactory
) -> None:
    raw, _ = await key_factory("inference.invoke")
    headers = {**_auth(raw), "Idempotency-Key": "key-404"}
    payload = {
        "model": "missing",
        "messages": [{"role": "user", "content": "hi"}],
    }

    first = await client.post("/v1/chat/completions", json=payload, headers=headers)
    assert first.status_code == 404
    # A failed request must not leave the key stuck in progress (would be 409).
    second = await client.post("/v1/chat/completions", json=payload, headers=headers)
    assert second.status_code == 404
