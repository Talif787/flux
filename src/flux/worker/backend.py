from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from flux.worker.domain import (
    ChatRole,
    Chunk,
    Completion,
    FinishReason,
    InferenceJob,
    Usage,
    count_tokens,
)


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
