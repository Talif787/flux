from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class FinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"


@dataclass(frozen=True)
class ChatTurn:
    role: ChatRole
    content: str


@dataclass(frozen=True)
class Sampling:
    temperature: float = 1.0
    top_p: float = 1.0
    max_tokens: int | None = None
    stop: tuple[str, ...] = ()


@dataclass(frozen=True)
class InferenceJob:
    model: str
    turns: tuple[ChatTurn, ...]
    sampling: Sampling


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class Completion:
    content: str
    finish_reason: FinishReason
    usage: Usage


@dataclass(frozen=True)
class Chunk:
    delta: str = ""
    role: ChatRole | None = None
    finish_reason: FinishReason | None = None


def count_tokens(text: str) -> int:
    """Deterministic, whitespace-based token estimate for the echo backend."""
    return len(text.split())
