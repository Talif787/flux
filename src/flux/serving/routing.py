from __future__ import annotations

from flux.serving.domain import InferenceRequest, RouteTarget

DEFAULT_POOL = "default"


class StaticRouter:
    """Routes every request to a single logical pool.

    This is the seam for KV-aware, load-aware routing introduced with real
    worker pools in a later phase. The port stays the same; only this adapter
    grows smarter.
    """

    def __init__(self, pool_id: str = DEFAULT_POOL) -> None:
        self._pool_id = pool_id

    async def route(self, request: InferenceRequest) -> RouteTarget:
        return RouteTarget(pool_id=self._pool_id)
