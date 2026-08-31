from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from flux.errors import DomainError

MAX_MESSAGES = 512


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class FinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"


class IdempotencyStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass(frozen=True)
class ChatMessage:
    role: ChatRole
    content: str


@dataclass(frozen=True)
class SamplingParams:
    """Validated generation parameters (a value object)."""

    temperature: float = 1.0
    top_p: float = 1.0
    max_tokens: int | None = None
    stop: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.temperature <= 2.0:
            raise DomainError("temperature must be between 0 and 2")
        if not 0.0 < self.top_p <= 1.0:
            raise DomainError("top_p must be in (0, 1]")
        if self.max_tokens is not None and self.max_tokens < 1:
            raise DomainError("max_tokens must be >= 1")


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class ResolvedModel:
    id: str
    name: str


@dataclass(frozen=True)
class InferenceRequest:
    tenant_id: str
    model_id: str
    model_name: str
    messages: tuple[ChatMessage, ...]
    sampling: SamplingParams


@dataclass(frozen=True)
class RouteTarget:
    """Where a request should be served.

    In stub mode this is a single logical pool. In remote mode ``endpoint`` and
    ``worker_id`` identify the selected worker."""

    pool_id: str
    endpoint: str | None = None
    worker_id: str | None = None


@dataclass(frozen=True)
class WorkerEndpoint:
    worker_id: str
    base_url: str


@dataclass(frozen=True)
class CompletionResult:
    content: str
    finish_reason: FinishReason
    usage: Usage


@dataclass(frozen=True)
class CompletionChunk:
    delta: str = ""
    role: ChatRole | None = None
    finish_reason: FinishReason | None = None


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: float = 0.0


@dataclass(frozen=True)
class BeginOutcome:
    """Result of claiming an idempotency key."""

    is_new: bool
    replay_code: int | None = None
    replay_body: str | None = None


# --- Ports (implemented by infrastructure adapters) ---


class ModelCatalog(Protocol):
    async def resolve(self, tenant_id: str, name: str) -> ResolvedModel | None: ...


class Router(Protocol):
    async def route(self, request: InferenceRequest) -> RouteTarget: ...


class WorkerDirectory(Protocol):
    async def candidates(self, model_name: str) -> list[WorkerEndpoint]: ...


class Scheduler(Protocol):
    async def acquire(self) -> None: ...
    def release(self) -> None: ...


class RateLimiter(Protocol):
    def check(self, key: str) -> RateLimitDecision: ...


class InferenceEngine(Protocol):
    async def generate(
        self, request: InferenceRequest, target: RouteTarget
    ) -> CompletionResult: ...

    def stream(
        self, request: InferenceRequest, target: RouteTarget
    ) -> AsyncIterator[CompletionChunk]: ...


class UsageRecorder(Protocol):
    async def record(
        self,
        *,
        tenant_id: str,
        model_id: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None: ...


class BudgetGuard(Protocol):
    async def check(self, tenant_id: str) -> None: ...


class IdempotencyStore(Protocol):
    async def begin(self, tenant_id: str, key: str, fingerprint: str) -> BeginOutcome: ...
    async def complete(self, tenant_id: str, key: str, code: int, body: str) -> None: ...
    async def discard(self, tenant_id: str, key: str) -> None: ...


def count_tokens(text: str) -> int:
    """A deterministic, whitespace-based token estimate for the stub engine."""
    return len(text.split())
