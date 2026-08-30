from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from flux.metering.domain import ModelPrice, UsageReport


class PriceUpsertRequest(BaseModel):
    prompt_per_1k: Decimal = Field(ge=0)
    completion_per_1k: Decimal = Field(ge=0)


class PriceResponse(BaseModel):
    model_name: str
    prompt_per_1k: str
    completion_per_1k: str

    @classmethod
    def from_domain(cls, price: ModelPrice) -> PriceResponse:
        return cls(
            model_name=price.model_name,
            prompt_per_1k=str(price.prompt_per_1k),
            completion_per_1k=str(price.completion_per_1k),
        )


class PriceListResponse(BaseModel):
    items: list[PriceResponse]


class ReportLineResponse(BaseModel):
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    request_count: int
    cost: str


class ReportTotals(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    request_count: int
    cost: str


class UsageReportResponse(BaseModel):
    tenant: str
    currency: str
    start: datetime | None
    end: datetime | None
    lines: list[ReportLineResponse]
    totals: ReportTotals

    @classmethod
    def from_domain(
        cls,
        report: UsageReport,
        *,
        start: datetime | None,
        end: datetime | None,
    ) -> UsageReportResponse:
        return cls(
            tenant=report.tenant,
            currency=report.currency,
            start=start,
            end=end,
            lines=[
                ReportLineResponse(
                    model_name=line.model_name,
                    prompt_tokens=line.prompt_tokens,
                    completion_tokens=line.completion_tokens,
                    request_count=line.request_count,
                    cost=str(line.cost),
                )
                for line in report.lines
            ],
            totals=ReportTotals(
                prompt_tokens=report.total_prompt_tokens,
                completion_tokens=report.total_completion_tokens,
                request_count=report.total_request_count,
                cost=str(report.total_cost),
            ),
        )
