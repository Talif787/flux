from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from flux.db import Base
from flux.ids import new_id
from flux.metering.domain import ModelPrice, UsageAggregate


class UsageRecordRow(Base):
    __tablename__ = "usage_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class ModelPriceRow(Base):
    __tablename__ = "model_prices"

    # Rates stored as strings so Decimal precision survives on SQLite (which has
    # no exact numeric type); parsed back to Decimal on read.
    model_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    prompt_per_1k: Mapped[str] = mapped_column(String(32), nullable=False)
    completion_per_1k: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _price_to_domain(row: ModelPriceRow) -> ModelPrice:
    return ModelPrice(
        model_name=row.model_name,
        prompt_per_1k=Decimal(row.prompt_per_1k),
        completion_per_1k=Decimal(row.completion_per_1k),
    )


class SqlAlchemyUsageRecorder:
    """Writer for usage records on the request session.

    The store commits eagerly per operation (as the repositories and the
    idempotency store do), which persists the usage row on the non-idempotent
    path where the request session is otherwise never committed.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        tenant_id: str,
        model_id: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        self._session.add(
            UsageRecordRow(
                id=new_id(),
                tenant_id=tenant_id,
                model_id=model_id,
                model_name=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                recorded_at=datetime.now(UTC),
            )
        )
        await self._session.commit()


class SqlAlchemyUsageRepository:
    """Read adapter that aggregates usage records for reporting."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def aggregate(
        self,
        *,
        tenant_id: str | None,
        model_name: str | None,
        start: datetime | None,
        end: datetime | None,
    ) -> list[UsageAggregate]:
        stmt = select(
            UsageRecordRow.model_name,
            func.sum(UsageRecordRow.prompt_tokens),
            func.sum(UsageRecordRow.completion_tokens),
            func.count(),
        ).group_by(UsageRecordRow.model_name)
        if tenant_id is not None:
            stmt = stmt.where(UsageRecordRow.tenant_id == tenant_id)
        if model_name is not None:
            stmt = stmt.where(UsageRecordRow.model_name == model_name)
        if start is not None:
            stmt = stmt.where(UsageRecordRow.recorded_at >= start)
        if end is not None:
            stmt = stmt.where(UsageRecordRow.recorded_at < end)
        rows = (await self._session.execute(stmt)).all()
        return [
            UsageAggregate(
                model_name=row[0],
                prompt_tokens=int(row[1] or 0),
                completion_tokens=int(row[2] or 0),
                request_count=int(row[3] or 0),
            )
            for row in rows
        ]


class SqlAlchemyPriceRepository:
    """CRUD adapter for per-model prices."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, model_name: str) -> ModelPrice | None:
        row = await self._session.get(ModelPriceRow, model_name)
        return _price_to_domain(row) if row is not None else None

    async def list(self) -> list[ModelPrice]:
        rows = (
            (await self._session.execute(select(ModelPriceRow).order_by(ModelPriceRow.model_name)))
            .scalars()
            .all()
        )
        return [_price_to_domain(row) for row in rows]

    async def upsert(self, price: ModelPrice) -> None:
        row = await self._session.get(ModelPriceRow, price.model_name)
        if row is None:
            self._session.add(
                ModelPriceRow(
                    model_name=price.model_name,
                    prompt_per_1k=str(price.prompt_per_1k),
                    completion_per_1k=str(price.completion_per_1k),
                    updated_at=datetime.now(UTC),
                )
            )
        else:
            row.prompt_per_1k = str(price.prompt_per_1k)
            row.completion_per_1k = str(price.completion_per_1k)
            row.updated_at = datetime.now(UTC)
        await self._session.commit()

    async def delete(self, model_name: str) -> bool:
        row = await self._session.get(ModelPriceRow, model_name)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.commit()
        return True
