from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

_MONEY_QUANTUM = Decimal("0.000001")


def quantize_money(amount: Decimal) -> Decimal:
    """Round a monetary amount to six decimal places (half-up)."""
    return amount.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class UsageRecord:
    """One metered inference, priced later from token counts."""

    id: str
    tenant_id: str
    model_id: str
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    recorded_at: datetime


@dataclass(frozen=True)
class UsageAggregate:
    """Summed usage for one model over a query window."""

    model_name: str
    prompt_tokens: int
    completion_tokens: int
    request_count: int


@dataclass(frozen=True)
class ModelPrice:
    """Per-1000-token rates for a model, in the configured billing currency."""

    model_name: str
    prompt_per_1k: Decimal
    completion_per_1k: Decimal


@dataclass(frozen=True)
class PriceBook:
    """Resolves rates for a model, falling back to configured defaults."""

    prices: dict[str, ModelPrice]
    default_prompt_per_1k: Decimal
    default_completion_per_1k: Decimal

    def rates_for(self, model_name: str) -> tuple[Decimal, Decimal]:
        price = self.prices.get(model_name)
        if price is not None:
            return price.prompt_per_1k, price.completion_per_1k
        return self.default_prompt_per_1k, self.default_completion_per_1k

    def cost(self, model_name: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
        prompt_rate, completion_rate = self.rates_for(model_name)
        amount = (
            Decimal(prompt_tokens) / Decimal(1000) * prompt_rate
            + Decimal(completion_tokens) / Decimal(1000) * completion_rate
        )
        return quantize_money(amount)


@dataclass(frozen=True)
class ReportLine:
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    request_count: int
    cost: Decimal


@dataclass(frozen=True)
class UsageReport:
    tenant: str
    currency: str
    lines: list[ReportLine]

    @property
    def total_prompt_tokens(self) -> int:
        return sum(line.prompt_tokens for line in self.lines)

    @property
    def total_completion_tokens(self) -> int:
        return sum(line.completion_tokens for line in self.lines)

    @property
    def total_request_count(self) -> int:
        return sum(line.request_count for line in self.lines)

    @property
    def total_cost(self) -> Decimal:
        return quantize_money(sum((line.cost for line in self.lines), Decimal(0)))


class UsageRepository(Protocol):
    async def aggregate(
        self,
        *,
        tenant_id: str | None,
        model_name: str | None,
        start: datetime | None,
        end: datetime | None,
    ) -> list[UsageAggregate]: ...


class PriceRepository(Protocol):
    async def get(self, model_name: str) -> ModelPrice | None: ...
    async def list(self) -> list[ModelPrice]: ...
    async def upsert(self, price: ModelPrice) -> None: ...
    async def delete(self, model_name: str) -> bool: ...
