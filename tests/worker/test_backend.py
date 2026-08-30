from __future__ import annotations

from flux.worker.backend import EchoBackend
from flux.worker.domain import ChatRole, ChatTurn, FinishReason, InferenceJob, Sampling


def _job(text: str, *, max_tokens: int | None = None) -> InferenceJob:
    return InferenceJob(
        model="gpt-stub",
        turns=(ChatTurn(role=ChatRole.USER, content=text),),
        sampling=Sampling(max_tokens=max_tokens),
    )


async def test_generate_is_deterministic_and_counts_tokens() -> None:
    backend = EchoBackend()
    result = await backend.generate(_job("hello there friend"))
    assert "gpt-stub" in result.content
    assert result.finish_reason is FinishReason.STOP
    assert result.usage.prompt_tokens == 3
    assert result.usage.total_tokens == (
        result.usage.prompt_tokens + result.usage.completion_tokens
    )


async def test_generate_truncates_on_max_tokens() -> None:
    backend = EchoBackend()
    result = await backend.generate(_job("one two three four five", max_tokens=2))
    assert result.finish_reason is FinishReason.LENGTH
    assert result.usage.completion_tokens == 2


async def test_stream_yields_role_then_words_then_finish() -> None:
    backend = EchoBackend()
    chunks = [chunk async for chunk in backend.stream(_job("stream this"))]
    assert chunks[0].role is ChatRole.ASSISTANT
    assert any(c.delta for c in chunks)
    assert chunks[-1].finish_reason is FinishReason.STOP
