from __future__ import annotations

import asyncio

from flux.errors import OverloadedError


class SemaphoreScheduler:
    """Bounded admission control.

    Admits up to ``max_concurrency`` requests to run at once and lets up to
    ``max_queue`` more wait for a slot. Beyond that the scheduler sheds load by
    raising OverloadedError, which the API surfaces as HTTP 503. This is the
    seam for the continuous-batching scheduler that arrives with real workers.
    """

    def __init__(self, max_concurrency: int, max_queue: int) -> None:
        self._sem = asyncio.Semaphore(max_concurrency)
        self._capacity = max_concurrency + max_queue
        self._inflight = 0

    async def acquire(self) -> None:
        if self._inflight >= self._capacity:
            raise OverloadedError("inference queue is full")
        self._inflight += 1
        try:
            await self._sem.acquire()
        except BaseException:
            self._inflight -= 1
            raise

    def release(self) -> None:
        self._sem.release()
        self._inflight -= 1
