from __future__ import annotations

from flux.serving.ratelimit import TokenBucketRateLimiter


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_token_bucket_allows_burst_then_denies() -> None:
    clock = _Clock()
    limiter = TokenBucketRateLimiter(rps=1.0, burst=2, now=clock)

    assert limiter.check("tenant").allowed
    assert limiter.check("tenant").allowed
    denied = limiter.check("tenant")
    assert not denied.allowed
    assert denied.retry_after > 0.0


def test_token_bucket_refills_over_time() -> None:
    clock = _Clock()
    limiter = TokenBucketRateLimiter(rps=1.0, burst=1, now=clock)

    assert limiter.check("tenant").allowed
    assert not limiter.check("tenant").allowed
    clock.t = 1.0
    assert limiter.check("tenant").allowed


def test_token_bucket_isolates_keys() -> None:
    clock = _Clock()
    limiter = TokenBucketRateLimiter(rps=1.0, burst=1, now=clock)

    assert limiter.check("a").allowed
    assert limiter.check("b").allowed
    assert not limiter.check("a").allowed
