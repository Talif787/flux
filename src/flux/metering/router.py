from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from flux.api.deps import get_session
from flux.auth.dependencies import require_roles
from flux.auth.domain import Principal, Role
from flux.config import Settings, get_settings
from flux.errors import ForbiddenError
from flux.metering.application import CostReporter, PriceService
from flux.metering.persistence import (
    SqlAlchemyPriceRepository,
    SqlAlchemyUsageRepository,
)
from flux.metering.schemas import (
    PriceListResponse,
    PriceResponse,
    PriceUpsertRequest,
    UsageReportResponse,
)

router = APIRouter(prefix="/v1", tags=["metering"])

UsageViewer = Annotated[Principal, Depends(require_roles(Role.TENANT_ADMIN))]
PriceManager = Annotated[Principal, Depends(require_roles(Role.PLATFORM_ADMIN))]


def get_cost_reporter(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CostReporter:
    return CostReporter(
        usage_repo=SqlAlchemyUsageRepository(session),
        price_repo=SqlAlchemyPriceRepository(session),
        default_prompt_per_1k=settings.default_prompt_per_1k,
        default_completion_per_1k=settings.default_completion_per_1k,
        currency=settings.billing_currency,
    )


def get_price_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PriceService:
    return PriceService(SqlAlchemyPriceRepository(session))


ReporterDep = Annotated[CostReporter, Depends(get_cost_reporter)]
PriceSvc = Annotated[PriceService, Depends(get_price_service)]

FromQuery = Annotated[datetime | None, Query(alias="from")]
ToQuery = Annotated[datetime | None, Query(alias="to")]
ModelQuery = Annotated[str | None, Query()]
TenantQuery = Annotated[str | None, Query()]


@router.get("/usage", response_model=UsageReportResponse)
async def usage_report(
    principal: UsageViewer,
    reporter: ReporterDep,
    start: FromQuery = None,
    end: ToQuery = None,
    model: ModelQuery = None,
    tenant: TenantQuery = None,
) -> UsageReportResponse:
    if principal.is_platform_admin:
        tenant_id = None if tenant in (None, "all") else tenant
    else:
        if tenant is not None and tenant != principal.tenant_id:
            raise ForbiddenError("cannot view usage for another tenant")
        tenant_id = principal.tenant_id
    report = await reporter.report(tenant_id=tenant_id, model_name=model, start=start, end=end)
    return UsageReportResponse.from_domain(report, start=start, end=end)


@router.put("/pricing/{model_name}", response_model=PriceResponse)
async def set_price(
    model_name: str,
    payload: PriceUpsertRequest,
    _: PriceManager,
    service: PriceSvc,
) -> PriceResponse:
    price = await service.set_price(
        model_name,
        prompt_per_1k=payload.prompt_per_1k,
        completion_per_1k=payload.completion_per_1k,
    )
    return PriceResponse.from_domain(price)


@router.get("/pricing", response_model=PriceListResponse)
async def list_prices(_: UsageViewer, service: PriceSvc) -> PriceListResponse:
    prices = await service.list_prices()
    return PriceListResponse(items=[PriceResponse.from_domain(p) for p in prices])


@router.get("/pricing/{model_name}", response_model=PriceResponse)
async def get_price(model_name: str, _: UsageViewer, service: PriceSvc) -> PriceResponse:
    return PriceResponse.from_domain(await service.get_price(model_name))


@router.delete("/pricing/{model_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_price(model_name: str, _: PriceManager, service: PriceSvc) -> Response:
    await service.delete_price(model_name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
