from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from flux.errors import NotFoundError, RateLimitError
from flux.logging import get_logger
from flux.serving.domain import (
    BudgetGuard,
    ChatMessage,
    CompletionChunk,
    CompletionResult,
    InferenceEngine,
    InferenceRequest,
    ModelCatalog,
    RateLimiter,
    Router,
    RouteTarget,
    SamplingParams,
    Scheduler,
    UsageRecorder,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class Prepared:
    """A request that has cleared rate limiting, resolution, routing, and
    admission. It holds an admission slot that the caller must release by
    running it to completion (or streaming it) exactly once."""

    request: InferenceRequest
    target: RouteTarget


class InferenceService:
    """Orchestrates the request plane: rate limit, resolve, route, admit, run.

    Admission is acquired in ``prepare`` (so overload and rate limiting surface
    as synchronous HTTP status codes) and released when ``complete`` or
    ``stream`` finishes.
    """

    def __init__(
        self,
        *,
        engine: InferenceEngine,
        router: Router,
        scheduler: Scheduler,
        rate_limiter: RateLimiter,
        catalog: ModelCatalog,
        usage_recorder: UsageRecorder | None = None,
        budget_guard: BudgetGuard | None = None,
        rate_limit_enabled: bool = True,
        metering_enabled: bool = True,
        budget_enforcement_enabled: bool = False,
    ) -> None:
        self._engine = engine
        self._router = router
        self._scheduler = scheduler
        self._rate_limiter = rate_limiter
        self._catalog = catalog
        self._usage_recorder = usage_recorder
        self._budget_guard = budget_guard
        self._rate_limit_enabled = rate_limit_enabled
        self._metering_enabled = metering_enabled
        self._budget_enforcement_enabled = budget_enforcement_enabled

    def _check_rate(self, tenant_id: str) -> None:
        if not self._rate_limit_enabled:
            return
        decision = self._rate_limiter.check(tenant_id)
        if not decision.allowed:
            raise RateLimitError(retry_after=decision.retry_after)

    async def _resolve(self, tenant_id: str, name: str) -> InferenceRequest:
        resolved = await self._catalog.resolve(tenant_id, name)
        if resolved is None:
            raise NotFoundError("model", name)
        return InferenceRequest(
            tenant_id=tenant_id,
            model_id=resolved.id,
            model_name=resolved.name,
            messages=(),
            sampling=SamplingParams(),
        )

    async def _record_usage(
        self,
        request: InferenceRequest,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        if not self._metering_enabled or self._usage_recorder is None:
            return
        try:
            await self._usage_recorder.record(
                tenant_id=request.tenant_id,
                model_id=request.model_id,
                model_name=request.model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        except Exception:
            logger.warning("metering_failed", model=request.model_name)

    async def _check_budget(self, tenant_id: str) -> None:
        if not self._budget_enforcement_enabled or self._budget_guard is None:
            return
        await self._budget_guard.check(tenant_id)

    async def prepare(
        self,
        *,
        tenant_id: str,
        model: str,
        messages: tuple[ChatMessage, ...],
        sampling: SamplingParams,
    ) -> Prepared:
        self._check_rate(tenant_id)
        await self._check_budget(tenant_id)
        base = await self._resolve(tenant_id, model)
        request = InferenceRequest(
            tenant_id=tenant_id,
            model_id=base.model_id,
            model_name=base.model_name,
            messages=messages,
            sampling=sampling,
        )
        target = await self._router.route(request)
        await self._scheduler.acquire()
        return Prepared(request=request, target=target)

    async def complete(self, prepared: Prepared) -> CompletionResult:
        try:
            result = await self._engine.generate(prepared.request, prepared.target)
            await self._record_usage(
                prepared.request,
                result.usage.prompt_tokens,
                result.usage.completion_tokens,
            )
            return result
        finally:
            self._scheduler.release()

    async def stream(self, prepared: Prepared) -> AsyncIterator[CompletionChunk]:
        # Streaming usage metering is deferred to a follow-on; the streaming
        # response carries no authoritative usage and metering inside the
        # generator's teardown is fragile against the session lifecycle.
        try:
            async for chunk in self._engine.stream(prepared.request, prepared.target):
                yield chunk
        finally:
            self._scheduler.release()
