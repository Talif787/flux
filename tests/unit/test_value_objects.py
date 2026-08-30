from __future__ import annotations

import pytest

from flux.errors import DomainError
from flux.models.domain import MAX_CONTEXT_LENGTH, ContextLength, Precision


def test_context_length_accepts_valid_value() -> None:
    assert ContextLength(4096).value == 4096


@pytest.mark.parametrize("bad", [0, -1, MAX_CONTEXT_LENGTH + 1])
def test_context_length_rejects_out_of_range(bad: int) -> None:
    with pytest.raises(DomainError):
        ContextLength(bad)


def test_precision_enum_membership() -> None:
    assert Precision("fp16") is Precision.FP16
    assert "int8" in {p.value for p in Precision}
