from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from flux.budgets.application import month_start
from flux.budgets.domain import BudgetStatus


def _status(limit: str, spent: str) -> BudgetStatus:
    return BudgetStatus(
        tenant_id="t-1",
        monthly_limit=Decimal(limit),
        currency="USD",
        period_start=month_start(datetime.now(UTC)),
        spent=Decimal(spent),
    )


def test_remaining_is_limit_minus_spent() -> None:
    assert _status("10", "3").remaining == Decimal("7")


def test_remaining_clamps_at_zero_when_over() -> None:
    assert _status("10", "12").remaining == Decimal("0")


def test_not_exceeded_below_limit() -> None:
    assert _status("10", "9.999999").exceeded is False


def test_exceeded_at_and_above_limit() -> None:
    assert _status("10", "10").exceeded is True
    assert _status("10", "10.000001").exceeded is True


def test_month_start_is_first_of_month_utc() -> None:
    start = month_start(datetime(2026, 3, 17, 14, 30, tzinfo=UTC))
    assert start == datetime(2026, 3, 1, 0, 0, tzinfo=UTC)
    assert start.tzinfo is UTC
