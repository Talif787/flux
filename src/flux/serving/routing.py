from __future__ import annotations

from flux.errors import NoWorkerAvailableError
from flux.serving.domain import (
    InferenceRequest,
    RouteTarget,
    WorkerDirectory,
    WorkerEndpoint,
)

DEFAULT_POOL = "default"


class StaticRouter:
    """Routes every request to a single logical pool (stub serving mode)."""

    def __init__(self, pool_id: str = DEFAULT_POOL) -> None:
        self._pool_id = pool_id

    async def route(self, request: InferenceRequest) -> RouteTarget:
        return RouteTarget(pool_id=self._pool_id)


class RoundRobinSelector:
    """Process-wide round-robin over a stable, ordered candidate list.

    A single shared instance lives on app state so the index advances across
    requests. Load-aware selection (least in-flight) is a later refinement.
    """

    def __init__(self) -> None:
        self._index = 0

    def pick(self, items: list[WorkerEndpoint]) -> WorkerEndpoint | None:
        if not items:
            return None
        chosen = items[self._index % len(items)]
        self._index += 1
        return chosen


class RegistryRouter:
    """Discovery-based router (remote serving mode).

    Asks the worker directory for healthy workers serving the model and picks
    one round-robin. If none are available it raises, which the API surfaces as
    HTTP 503.
    """

    def __init__(self, directory: WorkerDirectory, selector: RoundRobinSelector) -> None:
        self._directory = directory
        self._selector = selector

    async def route(self, request: InferenceRequest) -> RouteTarget:
        candidates = await self._directory.candidates(request.model_name)
        chosen = self._selector.pick(candidates)
        if chosen is None:
            raise NoWorkerAvailableError(f"no worker available for model: {request.model_name}")
        return RouteTarget(
            pool_id=chosen.worker_id,
            endpoint=chosen.base_url,
            worker_id=chosen.worker_id,
        )
