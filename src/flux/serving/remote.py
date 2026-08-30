from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx

from flux.errors import UpstreamError
from flux.serving.domain import (
    ChatRole,
    CompletionChunk,
    CompletionResult,
    FinishReason,
    InferenceRequest,
    RouteTarget,
    Usage,
)

ClientFactory = Callable[[str], httpx.AsyncClient]

_PATH = "/v1/chat/completions"


def default_client_factory(timeout_seconds: float) -> ClientFactory:
    def factory(endpoint: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=endpoint, timeout=timeout_seconds)

    return factory


class RemoteInferenceEngine:
    """Calls a worker over HTTP using its OpenAI-compatible surface.

    The client factory maps a worker endpoint to an httpx client, which keeps
    the transport injectable (a real client in production, an in-process ASGI
    client in tests).
    """

    def __init__(self, client_factory: ClientFactory) -> None:
        self._client_factory = client_factory

    def _payload(self, request: InferenceRequest, *, stream: bool) -> dict[str, object]:
        sampling = request.sampling
        return {
            "model": request.model_name,
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
            "temperature": sampling.temperature,
            "top_p": sampling.top_p,
            "max_tokens": sampling.max_tokens,
            "stream": stream,
            "stop": list(sampling.stop) if sampling.stop else None,
        }

    async def generate(self, request: InferenceRequest, target: RouteTarget) -> CompletionResult:
        if target.endpoint is None:
            raise UpstreamError("route target has no worker endpoint")
        client = self._client_factory(target.endpoint)
        async with client:
            try:
                resp = await client.post(_PATH, json=self._payload(request, stream=False))
            except httpx.HTTPError as exc:
                raise UpstreamError("worker request failed") from exc
            if resp.status_code >= 400:
                raise UpstreamError(f"worker returned status {resp.status_code}")
            try:
                return self._parse_completion(resp.json())
            except (KeyError, ValueError) as exc:
                raise UpstreamError("invalid worker response") from exc

    async def stream(
        self, request: InferenceRequest, target: RouteTarget
    ) -> AsyncIterator[CompletionChunk]:
        if target.endpoint is None:
            raise UpstreamError("route target has no worker endpoint")
        client = self._client_factory(target.endpoint)
        async with client:
            try:
                async with client.stream(
                    "POST", _PATH, json=self._payload(request, stream=True)
                ) as resp:
                    if resp.status_code >= 400:
                        raise UpstreamError(f"worker returned status {resp.status_code}")
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[len("data:") :].strip()
                        if payload == "[DONE]":
                            return
                        try:
                            data = json.loads(payload)
                        except ValueError as exc:
                            raise UpstreamError("invalid worker chunk") from exc
                        yield self._parse_chunk(data)
            except httpx.HTTPError as exc:
                raise UpstreamError("worker stream failed") from exc

    @staticmethod
    def _parse_completion(data: dict[str, Any]) -> CompletionResult:
        choice = data["choices"][0]
        message = choice["message"]
        usage = data["usage"]
        return CompletionResult(
            content=str(message["content"]),
            finish_reason=FinishReason(str(choice["finish_reason"])),
            usage=Usage(
                prompt_tokens=int(usage["prompt_tokens"]),
                completion_tokens=int(usage["completion_tokens"]),
            ),
        )

    @staticmethod
    def _parse_chunk(data: dict[str, Any]) -> CompletionChunk:
        choice = data["choices"][0]
        delta = choice.get("delta", {})
        role = ChatRole(delta["role"]) if "role" in delta else None
        finish_raw = choice.get("finish_reason")
        finish = FinishReason(str(finish_raw)) if finish_raw else None
        return CompletionChunk(
            delta=str(delta.get("content", "")),
            role=role,
            finish_reason=finish,
        )
