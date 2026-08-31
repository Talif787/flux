from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class Budget:
    """A tenant's monthly spend limit in the configured billing currency."""

    tenant_id: str
    monthly_limit: Decimal


@dataclass(frozen=True)
class BudgetStatus:
    """A budget alongside the current period's spend against it."""

    tenant_id: str
    monthly_limit: Decimal
    currency: str
    period_start: datetime
    spent: Decimal

    @property
    def remaining(self) -> Decimal:
        remaining = self.monthly_limit - self.spent
        return remaining if remaining > 0 else Decimal(0)

    @property
    def exceeded(self) -> bool:
        return self.spent >= self.monthly_limit


class BudgetRepository(Protocol):
    async def get(self, tenant_id: str) -> Budget | None: ...
    async def list(self) -> list[Budget]: ...
    async def upsert(self, budget: Budget) -> None: ...
    async def delete(self, tenant_id: str) -> bool: ...
