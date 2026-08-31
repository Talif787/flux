from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from flux.budgets.domain import Budget
from flux.db import Base


class BudgetRow(Base):
    __tablename__ = "budgets"

    # One budget per tenant. Limit stored as a string so Decimal precision
    # survives on SQLite, which has no exact numeric type.
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    monthly_limit: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _to_domain(row: BudgetRow) -> Budget:
    return Budget(tenant_id=row.tenant_id, monthly_limit=Decimal(row.monthly_limit))


class SqlAlchemyBudgetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: str) -> Budget | None:
        row = await self._session.get(BudgetRow, tenant_id)
        return _to_domain(row) if row is not None else None

    async def list(self) -> list[Budget]:
        rows = (
            (await self._session.execute(select(BudgetRow).order_by(BudgetRow.tenant_id)))
            .scalars()
            .all()
        )
        return [_to_domain(row) for row in rows]

    async def upsert(self, budget: Budget) -> None:
        row = await self._session.get(BudgetRow, budget.tenant_id)
        if row is None:
            self._session.add(
                BudgetRow(
                    tenant_id=budget.tenant_id,
                    monthly_limit=str(budget.monthly_limit),
                    updated_at=datetime.now(UTC),
                )
            )
        else:
            row.monthly_limit = str(budget.monthly_limit)
            row.updated_at = datetime.now(UTC)
        await self._session.commit()

    async def delete(self, tenant_id: str) -> bool:
        row = await self._session.get(BudgetRow, tenant_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.commit()
        return True
