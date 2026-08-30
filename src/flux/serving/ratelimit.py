from __future__ import annotations

import time
from collections.abc import Callable

from flux.serving.domain import RateLimitDecision


class TokenBucketRateLimiter:
    """Per-key token-bucket rate limiter (in-process).

    A shared instance holds one bucket per key (per tenant). The clock is
    injectable so the behaviour is deterministically testable. A distributed
    limiter (Redis) can later replace this behind the RateLimiter port.
    """

    def __init__(
        self,
        rps: float,
        burst: int,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._rps = float(rps)
        self._burst = float(burst)
        self._now = now
        self._buckets: dict[str, tuple[float, float]] = {}

    def check(self, key: str) -> RateLimitDecision:
        now = self._now()
        tokens, last = self._buckets.get(key, (self._burst, now))
        tokens = min(self._burst, tokens + (now - last) * self._rps)
        if tokens >= 1.0:
            self._buckets[key] = (tokens - 1.0, now)
            return RateLimitDecision(allowed=True)
        self._buckets[key] = (tokens, now)
        deficit = 1.0 - tokens
        retry_after = deficit / self._rps if self._rps > 0 else 60.0
        return RateLimitDecision(allowed=False, retry_after=retry_after)
