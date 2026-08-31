from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Protocol

import httpx

from flux.logging import get_logger
from flux.worker.domain import (
    ChatRole,
    Chunk,
    Completion,
    FinishReason,
    InferenceJob,
    Usage,
    count_tokens,
)

logger = get_logger(__name__)


class BackendError(Exception):
    """Raised when the upstream serving engine cannot fulfil a request."""


class InferenceBackend(Protocol):
    """The port a real serving engine implements.

    Phase 4 ships EchoBackend (CPU, deterministic). A GPU engine (vLLM, TGI, or
    a custom runtime) plugs in here without changing the worker's HTTP surface.
    """

    async def generate(self, job: InferenceJob) -> Completion: ...
    def stream(self, job: InferenceJob) -> AsyncIterator[Chunk]: ...


class EchoBackend:
    """A deterministic backend that echoes the last user turn.

    It exists so the whole serving node (HTTP surface, streaming, usage
    accounting, model gating) is exercisable without a GPU.
    """

    name = "echo"

    async def generate(self, job: InferenceJob) -> Completion:
        content = self._reply(job)
        prompt_tokens = sum(count_tokens(turn.content) for turn in job.turns)
        completion_tokens = count_tokens(content)
        finish = FinishReason.STOP
        max_tokens = job.sampling.max_tokens
        if max_tokens is not None and completion_tokens > max_tokens:
            words = content.split()[:max_tokens]
            content = " ".join(words)
            completion_tokens = len(words)
            finish = FinishReason.LENGTH
        return Completion(
            content=content,
            finish_reason=finish,
            usage=Usage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
        )

    async def stream(self, job: InferenceJob) -> AsyncIterator[Chunk]:
        result = await self.generate(job)
        yield Chunk(role=ChatRole.ASSISTANT)
        for word in result.content.split():
            yield Chunk(delta=f"{word} ")
        yield Chunk(finish_reason=result.finish_reason)

    @staticmethod
    def _reply(job: InferenceJob) -> str:
        last_user = next(
            (t.content for t in reversed(job.turns) if t.role == ChatRole.USER),
            "",
        )
        return f"Flux worker echo for {job.model}. You said: {last_user}"


def _finish_reason(value: object) -> FinishReason:
    return FinishReason.LENGTH if value == "length" else FinishReason.STOP


def _usage(raw: object, job: InferenceJob, content: str) -> Usage:
    if isinstance(raw, dict) and "prompt_tokens" in raw and "completion_tokens" in raw:
        return Usage(
            prompt_tokens=int(raw["prompt_tokens"]),
            completion_tokens=int(raw["completion_tokens"]),
        )
    prompt = sum(count_tokens(turn.content) for turn in job.turns)
    return Usage(prompt_tokens=prompt, completion_tokens=count_tokens(content))


class OpenAIBackend:
    """Backend that proxies to an upstream OpenAI-compatible server.

    Works with vLLM, Ollama, TGI, or OpenAI itself. The worker's HTTP surface,
    streaming, and usage accounting are unchanged; only the engine differs.
    """

    name = "openai"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        model: str | None = None,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model_override = model
        self._owns_client = client is None
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    def _body(self, job: InferenceJob, *, stream: bool) -> dict[str, object]:
        body: dict[str, object] = {
            "model": self._model_override or job.model,
            "messages": [{"role": turn.role.value, "content": turn.content} for turn in job.turns],
            "temperature": job.sampling.temperature,
            "top_p": job.sampling.top_p,
            "stream": stream,
        }
        if job.sampling.max_tokens is not None:
            body["max_tokens"] = job.sampling.max_tokens
        if job.sampling.stop:
            body["stop"] = list(job.sampling.stop)
        return body

    async def generate(self, job: InferenceJob) -> Completion:
        try:
            response = await self._client.post(
                "/chat/completions", json=self._body(job, stream=False)
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise BackendError(f"upstream request failed: {exc}") from exc
        choice = data["choices"][0]
        content = choice["message"].get("content") or ""
        return Completion(
            content=content,
            finish_reason=_finish_reason(choice.get("finish_reason")),
            usage=_usage(data.get("usage"), job, content),
        )

    async def stream(self, job: InferenceJob) -> AsyncIterator[Chunk]:
        yield Chunk(role=ChatRole.ASSISTANT)
        finish = FinishReason.STOP
        try:
            async with self._client.stream(
                "POST", "/chat/completions", json=self._body(job, stream=True)
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[len("data:") :].strip()
                    if payload == "[DONE]":
                        break
                    event = json.loads(payload)
                    choice = event["choices"][0]
                    text = choice.get("delta", {}).get("content")
                    if text:
                        yield Chunk(delta=text)
                    if choice.get("finish_reason"):
                        finish = _finish_reason(choice["finish_reason"])
        except (httpx.HTTPError, json.JSONDecodeError, KeyError):
            logger.warning("upstream_stream_failed")
        yield Chunk(finish_reason=finish)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
