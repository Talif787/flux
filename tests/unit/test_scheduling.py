from __future__ import annotations

import pytest

from flux.errors import OverloadedError
from flux.serving.scheduling import SemaphoreScheduler


async def test_scheduler_admits_then_sheds_load() -> None:
    scheduler = SemaphoreScheduler(max_concurrency=1, max_queue=0)

    await scheduler.acquire()
    with pytest.raises(OverloadedError):
        await scheduler.acquire()

    scheduler.release()
    await scheduler.acquire()  # capacity freed
    scheduler.release()


async def test_scheduler_allows_queue_depth() -> None:
    scheduler = SemaphoreScheduler(max_concurrency=1, max_queue=1)

    await scheduler.acquire()  # running
    scheduler.release()
    await scheduler.acquire()  # reuse
    scheduler.release()
