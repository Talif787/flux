from __future__ import annotations

import pytest

from flux.errors import DomainError
from flux.serving.domain import SamplingParams, Usage, count_tokens
from flux.serving.idempotency import fingerprint


def test_sampling_params_defaults() -> None:
    params = SamplingParams()
    assert params.temperature == 1.0
    assert params.top_p == 1.0
    assert params.max_tokens is None
    assert params.stop == ()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"temperature": -0.1},
        {"temperature": 2.1},
        {"top_p": 0.0},
        {"top_p": 1.5},
        {"max_tokens": 0},
    ],
)
def test_sampling_params_validation(kwargs: dict[str, float]) -> None:
    with pytest.raises(DomainError):
        SamplingParams(**kwargs)


def test_count_tokens() -> None:
    assert count_tokens("") == 0
    assert count_tokens("one two three") == 3


def test_usage_total() -> None:
    usage = Usage(prompt_tokens=4, completion_tokens=6)
    assert usage.total_tokens == 10


def test_fingerprint_is_stable_and_body_sensitive() -> None:
    a = fingerprint("t1", "POST", "/v1/chat/completions", b'{"x":1}')
    b = fingerprint("t1", "POST", "/v1/chat/completions", b'{"x":1}')
    c = fingerprint("t1", "POST", "/v1/chat/completions", b'{"x":2}')
    d = fingerprint("t2", "POST", "/v1/chat/completions", b'{"x":1}')
    assert a == b
    assert a != c
    assert a != d
