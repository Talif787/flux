from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from flux.errors import NotFoundError
from flux.pagination import PageParams
from flux.workers.application import WorkerRegistry
from flux.workers.domain import WorkerStatus
from flux.workers.persistence import SqlAlchemyWorkerRepository


def _registry(session: AsyncSession) -> WorkerRegistry:
    return WorkerRegistry(SqlAlchemyWorkerRepository(session))


async def test_register_creates_active_worker(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        registry = _registry(session)
        worker = await registry.register(
            "w-1",
            name="node-1",
            base_url="http://w1:8090",
            served_models=["gpt-stub", "llama-3-8b"],
            max_concurrency=4,
        )

    assert worker.status is WorkerStatus.ACTIVE
    assert worker.served_models == frozenset({"gpt-stub", "llama-3-8b"})
    assert worker.max_concurrency == 4
    assert worker.last_heartbeat_at == worker.registered_at


async def test_register_is_idempotent_upsert(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        registry = _registry(session)
        first = await registry.register(
            "w-1",
            name="node-1",
            base_url="http://old:8090",
            served_models=["gpt-stub"],
            max_concurrency=2,
        )
        second = await registry.register(
            "w-1",
            name="node-1-renamed",
            base_url="http://new:8090",
            served_models=["gpt-stub", "mixtral"],
            max_concurrency=8,
        )

    assert second.base_url == "http://new:8090"
    assert second.name == "node-1-renamed"
    assert second.served_models == frozenset({"gpt-stub", "mixtral"})
    # registered_at is preserved across re-registration
    assert second.registered_at == first.registered_at

    async with sessionmaker() as session:
        stored = await SqlAlchemyWorkerRepository(session).get("w-1")
    assert stored is not None
    assert stored.base_url == "http://new:8090"


async def test_heartbeat_refreshes_liveness(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        registry = _registry(session)
        registered = await registry.register(
            "w-1",
            name="node-1",
            base_url="http://w1:8090",
            served_models=[],
            max_concurrency=1,
        )
        beaten = await registry.heartbeat("w-1")

    assert beaten.last_heartbeat_at >= registered.last_heartbeat_at
    assert beaten.registered_at == registered.registered_at


async def test_heartbeat_unknown_worker_raises(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        with pytest.raises(NotFoundError):
            await _registry(session).heartbeat("ghost")


async def test_deregister_removes_worker(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        registry = _registry(session)
        await registry.register(
            "w-1",
            name="node-1",
            base_url="http://w1:8090",
            served_models=[],
            max_concurrency=1,
        )
        removed = await registry.deregister("w-1")
        again = await registry.deregister("w-1")

    assert removed is True
    assert again is False


async def test_list_workers_paginates(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        registry = _registry(session)
        for i in range(3):
            await registry.register(
                f"w-{i}",
                name=f"node-{i}",
                base_url=f"http://w{i}:8090",
                served_models=[],
                max_concurrency=1,
            )
        page = await registry.list_workers(PageParams(limit=2, offset=0))

    assert page.total == 3
    assert len(page.items) == 2
