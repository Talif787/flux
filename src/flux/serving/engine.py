from __future__ import annotations

from collections.abc import AsyncIterator

from flux.serving.domain import (
    ChatRole,
    CompletionChunk,
    CompletionResult,
    FinishReason,
    InferenceRequest,
    RouteTarget,
    Usage,
    count_tokens,
)


class StubInferenceEngine:
    """A deterministic placeholder engine.

    Phase 3 establishes the serving path and its abstractions without GPUs.
    This engine returns a reproducible response so the API, streaming, usage
    accounting, idempotency, and admission control are all exercisable end to
    end. Phase 4 replaces it with real serving backends behind the same port.
    """

    async def generate(self, request: InferenceRequest, target: RouteTarget) -> CompletionResult:
        content = self._reply(request)
        prompt_tokens = self._prompt_tokens(request)
        completion_tokens = count_tokens(content)
        finish = FinishReason.STOP
        max_tokens = request.sampling.max_tokens
        if max_tokens is not None and completion_tokens > max_tokens:
            words = content.split()[:max_tokens]
            content = " ".join(words)
            completion_tokens = len(words)
            finish = FinishReason.LENGTH
        return CompletionResult(
            content=content,
            finish_reason=finish,
            usage=Usage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
        )

    async def stream(
        self, request: InferenceRequest, target: RouteTarget
    ) -> AsyncIterator[CompletionChunk]:
        result = await self.generate(request, target)
        yield CompletionChunk(role=ChatRole.ASSISTANT)
        for word in result.content.split():
            yield CompletionChunk(delta=f"{word} ")
        yield CompletionChunk(finish_reason=result.finish_reason)

    @staticmethod
    def _reply(request: InferenceRequest) -> str:
        last_user = next(
            (m.content for m in reversed(request.messages) if m.role == ChatRole.USER),
            "",
        )
        return f"Flux stub response for {request.model_name}. You said: {last_user}"

    @staticmethod
    def _prompt_tokens(request: InferenceRequest) -> int:
        return sum(count_tokens(m.content) for m in request.messages)
