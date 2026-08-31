from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from flux.budgets.application import BudgetService, EnforcingBudgetGuard
from flux.budgets.domain import Budget
from flux.budgets.persistence import SqlAlchemyBudgetRepository
from flux.errors import BudgetExceededError, NotFoundError
from flux.metering.application import CostReporter
from flux.metering.persistence import (
    SqlAlchemyPriceRepository,
    SqlAlchemyUsageRecorder,
    SqlAlchemyUsageRepository,
)

_DEFAULT_PROMPT = Decimal("0.0005")
_DEFAULT_COMPLETION = Decimal("0.0015")


def _reporter(session: AsyncSession) -> CostReporter:
    return CostReporter(
        usage_repo=SqlAlchemyUsageRepository(session),
        price_repo=SqlAlchemyPriceRepository(session),
        default_prompt_per_1k=_DEFAULT_PROMPT,
        default_completion_per_1k=_DEFAULT_COMPLETION,
        currency="USD",
    )


async def _record(
    sessionmaker: async_sessionmaker[AsyncSession],
    tenant_id: str,
    prompt: int,
    completion: int,
) -> None:
    async with sessionmaker() as session:
        await SqlAlchemyUsageRecorder(session).record(
            tenant_id=tenant_id,
            model_id="m-gpt-stub",
            model_name="gpt-stub",
            prompt_tokens=prompt,
            completion_tokens=completion,
        )


async def test_budget_repository_crud(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        repo = SqlAlchemyBudgetRepository(session)
        assert await repo.get("t-1") is None
        await repo.upsert(Budget("t-1", Decimal("50")))
        assert (await repo.get("t-1")).monthly_limit == Decimal("50")
        await repo.upsert(Budget("t-1", Decimal("75")))  # update
        assert (await repo.get("t-1")).monthly_limit == Decimal("75")
        assert [b.tenant_id for b in await repo.list()] == ["t-1"]
        assert await repo.delete("t-1") is True
        assert await repo.get("t-1") is None
        assert await repo.delete("t-1") is False


async def test_status_reflects_recorded_spend(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # 1000 prompt + 1000 completion at defaults = 0.0005 + 0.0015 = 0.002000
    await _record(sessionmaker, "t-1", 1000, 1000)
    async with sessionmaker() as session:
        repo = SqlAlchemyBudgetRepository(session)
        await repo.upsert(Budget("t-1", Decimal("10")))
        service = BudgetService(repo, _reporter(session), "USD")
        status = await service.status("t-1")
    assert status.spent == Decimal("0.002000")
    assert status.remaining == Decimal("9.998000")
    assert status.exceeded is False


async def test_status_missing_budget_raises(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        service = BudgetService(SqlAlchemyBudgetRepository(session), _reporter(session), "USD")
        with pytest.raises(NotFoundError):
            await service.status("nobody")


async def test_guard_blocks_over_budget(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await _record(sessionmaker, "t-1", 1000, 1000)  # spend 0.002
    async with sessionmaker() as session:
        repo = SqlAlchemyBudgetRepository(session)
        await repo.upsert(Budget("t-1", Decimal("0.001")))  # limit below spend
        guard = EnforcingBudgetGuard(repo, _reporter(session))
        with pytest.raises(BudgetExceededError):
            await guard.check("t-1")


async def test_guard_allows_under_budget(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await _record(sessionmaker, "t-1", 1000, 1000)  # spend 0.002
    async with sessionmaker() as session:
        repo = SqlAlchemyBudgetRepository(session)
        await repo.upsert(Budget("t-1", Decimal("1.00")))  # generous limit
        guard = EnforcingBudgetGuard(repo, _reporter(session))
        await guard.check("t-1")  # must not raise


async def test_guard_no_budget_is_unconstrained(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await _record(sessionmaker, "t-1", 999999, 999999)
    async with sessionmaker() as session:
        guard = EnforcingBudgetGuard(SqlAlchemyBudgetRepository(session), _reporter(session))
        await guard.check("t-1")  # no budget row -> no enforcement, no raise
