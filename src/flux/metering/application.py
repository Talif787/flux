from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flux.errors import NotFoundError
from flux.metering.domain import (
    ModelPrice,
    PriceBook,
    PriceRepository,
    ReportLine,
    UsageReport,
    UsageRepository,
)


class CostReporter:
    """Builds a priced usage report from aggregated records."""

    def __init__(
        self,
        *,
        usage_repo: UsageRepository,
        price_repo: PriceRepository,
        default_prompt_per_1k: Decimal,
        default_completion_per_1k: Decimal,
        currency: str,
    ) -> None:
        self._usage_repo = usage_repo
        self._price_repo = price_repo
        self._default_prompt_per_1k = default_prompt_per_1k
        self._default_completion_per_1k = default_completion_per_1k
        self._currency = currency

    async def report(
        self,
        *,
        tenant_id: str | None,
        model_name: str | None,
        start: datetime | None,
        end: datetime | None,
    ) -> UsageReport:
        aggregates = await self._usage_repo.aggregate(
            tenant_id=tenant_id, model_name=model_name, start=start, end=end
        )
        prices = {price.model_name: price for price in await self._price_repo.list()}
        book = PriceBook(
            prices=prices,
            default_prompt_per_1k=self._default_prompt_per_1k,
            default_completion_per_1k=self._default_completion_per_1k,
        )
        lines = [
            ReportLine(
                model_name=agg.model_name,
                prompt_tokens=agg.prompt_tokens,
                completion_tokens=agg.completion_tokens,
                request_count=agg.request_count,
                cost=book.cost(agg.model_name, agg.prompt_tokens, agg.completion_tokens),
            )
            for agg in sorted(aggregates, key=lambda a: a.model_name)
        ]
        return UsageReport(tenant=tenant_id or "all", currency=self._currency, lines=lines)


class PriceService:
    """Manages per-model prices."""

    def __init__(self, repo: PriceRepository) -> None:
        self._repo = repo

    async def set_price(
        self,
        model_name: str,
        *,
        prompt_per_1k: Decimal,
        completion_per_1k: Decimal,
    ) -> ModelPrice:
        price = ModelPrice(
            model_name=model_name,
            prompt_per_1k=prompt_per_1k,
            completion_per_1k=completion_per_1k,
        )
        await self._repo.upsert(price)
        return price

    async def get_price(self, model_name: str) -> ModelPrice:
        price = await self._repo.get(model_name)
        if price is None:
            raise NotFoundError("price", model_name)
        return price

    async def list_prices(self) -> list[ModelPrice]:
        return await self._repo.list()

    async def delete_price(self, model_name: str) -> bool:
        return await self._repo.delete(model_name)
