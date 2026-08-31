from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from flux.budgets.domain import Budget, BudgetStatus


class BudgetUpsertRequest(BaseModel):
    monthly_limit: Decimal = Field(ge=0)


class BudgetResponse(BaseModel):
    tenant_id: str
    monthly_limit: str

    @classmethod
    def from_domain(cls, budget: Budget) -> BudgetResponse:
        return cls(tenant_id=budget.tenant_id, monthly_limit=str(budget.monthly_limit))


class BudgetListResponse(BaseModel):
    items: list[BudgetResponse]


class BudgetStatusResponse(BaseModel):
    tenant_id: str
    currency: str
    period_start: datetime
    monthly_limit: str
    spent: str
    remaining: str
    exceeded: bool

    @classmethod
    def from_domain(cls, status: BudgetStatus) -> BudgetStatusResponse:
        return cls(
            tenant_id=status.tenant_id,
            currency=status.currency,
            period_start=status.period_start,
            monthly_limit=str(status.monthly_limit),
            spent=str(status.spent),
            remaining=str(status.remaining),
            exceeded=status.exceeded,
        )
