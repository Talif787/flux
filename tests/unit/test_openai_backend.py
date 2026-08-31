from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from flux.worker.backend import BackendError, EchoBackend, OpenAIBackend
from flux.worker.config import WorkerSettings
from flux.worker.domain import ChatRole, ChatTurn, FinishReason, InferenceJob, Sampling

Handler = Callable[[httpx.Request], httpx.Response]

_JOB = InferenceJob(
    model="gpt-x",
    turns=(ChatTurn(role=ChatRole.USER, content="hello there"),),
    sampling=Sampling(temperature=0.5, top_p=0.9, max_tokens=32),
)


def _backend(handler: Handler, **kwargs: object) -> OpenAIBackend:
    http = httpx.AsyncClient(base_url="http://upstream/v1", transport=httpx.MockTransport(handler))
    return OpenAIBackend(base_url="http://upstream/v1", client=http, **kwargs)


def _completion(content: str, finish: str = "stop", usage: dict | None = None) -> dict:
    body: dict[str, object] = {
        "id": "cmpl-1",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish,
            }
        ],
    }
    if usage is not None:
        body["usage"] = usage
    return body


async def test_generate_builds_openai_request_and_maps_result() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=_completion("hi back", usage={"prompt_tokens": 3, "completion_tokens": 2}),
        )

    result = await _backend(handler).generate(_JOB)

    assert seen["url"] == "http://upstream/v1/chat/completions"
    assert seen["body"] == {
        "model": "gpt-x",
        "messages": [{"role": "user", "content": "hello there"}],
        "temperature": 0.5,
        "top_p": 0.9,
        "stream": False,
        "max_tokens": 32,
    }
    assert result.content == "hi back"
    assert result.finish_reason is FinishReason.STOP
    assert result.usage.prompt_tokens == 3
    assert result.usage.completion_tokens == 2


async def test_generate_maps_length_finish_reason() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion("truncated", finish="length"))

    result = await _backend(handler).generate(_JOB)
    assert result.finish_reason is FinishReason.LENGTH


async def test_generate_falls_back_to_token_estimate_without_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion("one two three"))

    result = await _backend(handler).generate(_JOB)
    # prompt "hello there" -> 2, completion "one two three" -> 3
    assert result.usage.prompt_tokens == 2
    assert result.usage.completion_tokens == 3


async def test_model_override_is_sent_upstream() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion("ok"))

    await _backend(handler, model="llama3.2:1b").generate(_JOB)
    assert seen["body"]["model"] == "llama3.2:1b"


async def test_api_key_sets_authorization_header() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=_completion("ok"))

    # Inject a transport (not a client) so the backend builds its own client with
    # the Authorization header, exercising the real api_key path.
    backend = OpenAIBackend(
        base_url="http://upstream/v1",
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
    )
    await backend.generate(_JOB)
    assert seen["auth"] == "Bearer sk-test"


async def test_generate_raises_backend_error_on_upstream_5xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    with pytest.raises(BackendError):
        await _backend(handler).generate(_JOB)


async def test_stream_yields_role_deltas_and_finish() -> None:
    sse = (
        'data: {"choices":[{"index":0,"delta":{"role":"assistant"}}]}\n\n'
        'data: {"choices":[{"index":0,"delta":{"content":"Hel"}}]}\n\n'
        'data: {"choices":[{"index":0,"delta":{"content":"lo"}}]}\n\n'
        'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=sse.encode(), headers={"content-type": "text/event-stream"}
        )

    chunks = [c async for c in _backend(handler).stream(_JOB)]
    assert chunks[0].role is ChatRole.ASSISTANT
    deltas = "".join(c.delta for c in chunks if c.delta)
    assert deltas == "Hello"
    assert chunks[-1].finish_reason is FinishReason.STOP


async def test_stream_survives_upstream_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    chunks = [c async for c in _backend(handler).stream(_JOB)]
    # role first, then a terminal finish chunk; no crash
    assert chunks[0].role is ChatRole.ASSISTANT
    assert chunks[-1].finish_reason is FinishReason.STOP


# --- config dispatch / validation ---


def test_openai_backend_requires_upstream_url() -> None:
    with pytest.raises(ValueError):
        WorkerSettings(_env_file=None, backend="openai")  # no upstream_base_url


def test_openai_settings_accept_upstream_url() -> None:
    settings = WorkerSettings(_env_file=None, backend="openai", upstream_base_url="http://u/v1")
    assert settings.backend == "openai"
    assert settings.upstream_base_url == "http://u/v1"


def test_echo_is_the_default_backend() -> None:
    assert WorkerSettings(_env_file=None).backend == "echo"
    assert EchoBackend().name == "echo"
