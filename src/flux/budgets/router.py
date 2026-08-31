from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from flux.api.deps import get_session
from flux.auth.dependencies import require_roles
from flux.auth.domain import Principal, Role
from flux.budgets.application import BudgetService
from flux.budgets.persistence import SqlAlchemyBudgetRepository
from flux.budgets.schemas import (
    BudgetListResponse,
    BudgetResponse,
    BudgetStatusResponse,
    BudgetUpsertRequest,
)
from flux.config import Settings, get_settings
from flux.errors import ForbiddenError
from flux.metering.application import CostReporter
from flux.metering.persistence import (
    SqlAlchemyPriceRepository,
    SqlAlchemyUsageRepository,
)

router = APIRouter(prefix="/v1/budgets", tags=["budgets"])

BudgetManager = Annotated[Principal, Depends(require_roles(Role.PLATFORM_ADMIN))]
BudgetViewer = Annotated[Principal, Depends(require_roles(Role.TENANT_ADMIN))]


def get_budget_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BudgetService:
    reporter = CostReporter(
        usage_repo=SqlAlchemyUsageRepository(session),
        price_repo=SqlAlchemyPriceRepository(session),
        default_prompt_per_1k=settings.default_prompt_per_1k,
        default_completion_per_1k=settings.default_completion_per_1k,
        currency=settings.billing_currency,
    )
    return BudgetService(SqlAlchemyBudgetRepository(session), reporter, settings.billing_currency)


BudgetSvc = Annotated[BudgetService, Depends(get_budget_service)]


@router.put("/{tenant_id}", response_model=BudgetResponse)
async def set_budget(
    tenant_id: str,
    payload: BudgetUpsertRequest,
    _: BudgetManager,
    service: BudgetSvc,
) -> BudgetResponse:
    budget = await service.set_budget(tenant_id, payload.monthly_limit)
    return BudgetResponse.from_domain(budget)


@router.get("", response_model=BudgetListResponse)
async def list_budgets(_: BudgetManager, service: BudgetSvc) -> BudgetListResponse:
    budgets = await service.list_budgets()
    return BudgetListResponse(items=[BudgetResponse.from_domain(b) for b in budgets])


@router.get("/{tenant_id}", response_model=BudgetStatusResponse)
async def get_budget_status(
    tenant_id: str, principal: BudgetViewer, service: BudgetSvc
) -> BudgetStatusResponse:
    if not principal.is_platform_admin and tenant_id != principal.tenant_id:
        raise ForbiddenError("cannot view another tenant's budget")
    return BudgetStatusResponse.from_domain(await service.status(tenant_id))


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(tenant_id: str, _: BudgetManager, service: BudgetSvc) -> Response:
    await service.delete_budget(tenant_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
