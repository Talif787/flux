from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from flux.db import Base
from flux.errors import ConflictError, IdempotencyMismatchError
from flux.models.persistence import ModelRow
from flux.serving.domain import BeginOutcome, IdempotencyStatus, ResolvedModel


class IdempotencyRow(Base):
    __tablename__ = "idempotency_records"

    tenant_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SqlAlchemyModelCatalog:
    """Read adapter resolving a model name to a registered model for a tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(self, tenant_id: str, name: str) -> ResolvedModel | None:
        stmt = select(ModelRow).where(ModelRow.tenant_id == tenant_id, ModelRow.name == name)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return ResolvedModel(id=row.id, name=row.name)


class SqlAlchemyIdempotencyStore:
    """Postgres-backed idempotency store.

    The primary-key insert acts as a distributed lock: the first request for a
    key inserts an in-progress row; concurrent or repeat requests read that row
    and either replay the stored response, reject a mismatched payload, or wait
    out an in-flight request.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def begin(self, tenant_id: str, key: str, fingerprint: str) -> BeginOutcome:
        self._session.add(
            IdempotencyRow(
                tenant_id=tenant_id,
                idempotency_key=key,
                fingerprint=fingerprint,
                status=IdempotencyStatus.IN_PROGRESS.value,
                created_at=datetime.now(UTC),
            )
        )
        try:
            await self._session.commit()
            return BeginOutcome(is_new=True)
        except IntegrityError:
            await self._session.rollback()

        existing = await self._session.get(IdempotencyRow, (tenant_id, key))
        if existing is None:
            raise ConflictError("idempotency record vanished during a race")
        if existing.fingerprint != fingerprint:
            raise IdempotencyMismatchError("idempotency key reused with a different request")
        if existing.status == IdempotencyStatus.IN_PROGRESS.value:
            raise ConflictError("a request with this idempotency key is still in progress")
        return BeginOutcome(
            is_new=False,
            replay_code=existing.response_code,
            replay_body=existing.response_body,
        )

    async def complete(self, tenant_id: str, key: str, code: int, body: str) -> None:
        row = await self._session.get(IdempotencyRow, (tenant_id, key))
        if row is None:
            return
        row.status = IdempotencyStatus.COMPLETED.value
        row.response_code = code
        row.response_body = body
        row.completed_at = datetime.now(UTC)
        await self._session.commit()

    async def discard(self, tenant_id: str, key: str) -> None:
        row = await self._session.get(IdempotencyRow, (tenant_id, key))
        if row is not None:
            await self._session.delete(row)
            await self._session.commit()
