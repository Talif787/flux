from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from flux.errors import NotFoundError
from flux.pagination import Page, PageParams
from flux.workers.domain import Worker, WorkerRepository, WorkerStatus


class WorkerRegistry:
    """Registration and liveness for compute-plane workers.

    ``register`` is an idempotent upsert so a worker that restarts re-registers
    cleanly. ``heartbeat`` refreshes liveness; discovery treats a worker as a
    routing candidate only while its heartbeat is fresh.
    """

    def __init__(self, repo: WorkerRepository) -> None:
        self._repo = repo

    async def register(
        self,
        worker_id: str,
        *,
        name: str,
        base_url: str,
        served_models: Iterable[str],
        max_concurrency: int,
    ) -> Worker:
        now = datetime.now(UTC)
        existing = await self._repo.get(worker_id)
        registered_at = existing.registered_at if existing is not None else now
        worker = Worker(
            id=worker_id,
            name=name,
            base_url=base_url,
            served_models=frozenset(served_models),
            max_concurrency=max_concurrency,
            status=WorkerStatus.ACTIVE,
            registered_at=registered_at,
            last_heartbeat_at=now,
        )
        await self._repo.upsert(worker)
        return worker

    async def heartbeat(self, worker_id: str) -> Worker:
        existing = await self._repo.get(worker_id)
        if existing is None:
            raise NotFoundError("worker", worker_id)
        worker = Worker(
            id=existing.id,
            name=existing.name,
            base_url=existing.base_url,
            served_models=existing.served_models,
            max_concurrency=existing.max_concurrency,
            status=existing.status,
            registered_at=existing.registered_at,
            last_heartbeat_at=datetime.now(UTC),
        )
        await self._repo.upsert(worker)
        return worker

    async def deregister(self, worker_id: str) -> bool:
        return await self._repo.delete(worker_id)

    async def list_workers(self, page: PageParams) -> Page[Worker]:
        return await self._repo.list(page)
