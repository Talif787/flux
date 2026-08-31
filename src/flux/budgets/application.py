from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from flux.budgets.domain import Budget, BudgetRepository, BudgetStatus
from flux.errors import BudgetExceededError, NotFoundError
from flux.logging import get_logger
from flux.metering.application import CostReporter

logger = get_logger(__name__)


def month_start(now: datetime) -> datetime:
    """First instant of the current calendar month, in UTC."""
    return datetime(now.year, now.month, 1, tzinfo=UTC)


async def _current_spend(reporter: CostReporter, tenant_id: str) -> Decimal:
    start = month_start(datetime.now(UTC))
    report = await reporter.report(tenant_id=tenant_id, model_name=None, start=start, end=None)
    return report.total_cost


class BudgetService:
    """Manages per-tenant budgets and reports spend against them."""

    def __init__(self, repo: BudgetRepository, reporter: CostReporter, currency: str) -> None:
        self._repo = repo
        self._reporter = reporter
        self._currency = currency

    async def set_budget(self, tenant_id: str, monthly_limit: Decimal) -> Budget:
        budget = Budget(tenant_id=tenant_id, monthly_limit=monthly_limit)
        await self._repo.upsert(budget)
        return budget

    async def get_budget(self, tenant_id: str) -> Budget:
        budget = await self._repo.get(tenant_id)
        if budget is None:
            raise NotFoundError("budget", tenant_id)
        return budget

    async def list_budgets(self) -> list[Budget]:
        return await self._repo.list()

    async def delete_budget(self, tenant_id: str) -> bool:
        return await self._repo.delete(tenant_id)

    async def status(self, tenant_id: str) -> BudgetStatus:
        budget = await self.get_budget(tenant_id)
        spent = await _current_spend(self._reporter, tenant_id)
        return BudgetStatus(
            tenant_id=tenant_id,
            monthly_limit=budget.monthly_limit,
            currency=self._currency,
            period_start=month_start(datetime.now(UTC)),
            spent=spent,
        )


class EnforcingBudgetGuard:
    """Serving-path guard that blocks a tenant over its monthly budget.

    Fails open: if spend cannot be determined, the request is allowed and the
    failure is logged, so a metering hiccup never blocks all traffic. A tenant
    with no budget row is unconstrained.
    """

    def __init__(self, repo: BudgetRepository, reporter: CostReporter) -> None:
        self._repo = repo
        self._reporter = reporter

    async def check(self, tenant_id: str) -> None:
        try:
            budget = await self._repo.get(tenant_id)
            if budget is None:
                return
            spent = await _current_spend(self._reporter, tenant_id)
        except Exception:
            logger.warning("budget_check_failed", tenant=tenant_id)
            return
        if spent >= budget.monthly_limit:
            raise BudgetExceededError(tenant_id, budget.monthly_limit, spent)
