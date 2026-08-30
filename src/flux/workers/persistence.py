from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from flux.db import Base
from flux.pagination import Page, PageParams
from flux.workers.domain import Worker, WorkerStatus


class WorkerRow(Base):
    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    served_models: Mapped[str] = mapped_column(Text, nullable=False, default="")
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _encode_models(models: frozenset[str]) -> str:
    return ",".join(sorted(models))


def _decode_models(raw: str) -> frozenset[str]:
    return frozenset(m for m in raw.split(",") if m)


def _aware(value: datetime) -> datetime:
    # SQLite drops tzinfo on DateTime(timezone=True); normalize to UTC-aware
    # so comparisons against timezone-aware values never raise.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _to_domain(row: WorkerRow) -> Worker:
    return Worker(
        id=row.id,
        name=row.name,
        base_url=row.base_url,
        served_models=_decode_models(row.served_models),
        max_concurrency=row.max_concurrency,
        status=WorkerStatus(row.status),
        registered_at=_aware(row.registered_at),
        last_heartbeat_at=_aware(row.last_heartbeat_at),
    )


class SqlAlchemyWorkerRepository:
    """SQLAlchemy adapter for the WorkerRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, worker_id: str) -> Worker | None:
        row = await self._session.get(WorkerRow, worker_id)
        return _to_domain(row) if row is not None else None

    async def upsert(self, worker: Worker) -> None:
        row = await self._session.get(WorkerRow, worker.id)
        if row is None:
            self._session.add(
                WorkerRow(
                    id=worker.id,
                    name=worker.name,
                    base_url=worker.base_url,
                    served_models=_encode_models(worker.served_models),
                    max_concurrency=worker.max_concurrency,
                    status=worker.status.value,
                    registered_at=worker.registered_at,
                    last_heartbeat_at=worker.last_heartbeat_at,
                )
            )
        else:
            row.name = worker.name
            row.base_url = worker.base_url
            row.served_models = _encode_models(worker.served_models)
            row.max_concurrency = worker.max_concurrency
            row.status = worker.status.value
            row.last_heartbeat_at = worker.last_heartbeat_at
        await self._session.commit()

    async def delete(self, worker_id: str) -> bool:
        row = await self._session.get(WorkerRow, worker_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.commit()
        return True

    async def list(self, page: PageParams) -> Page[Worker]:
        total = int(
            (await self._session.execute(select(func.count()).select_from(WorkerRow))).scalar_one()
        )
        rows = (
            (
                await self._session.execute(
                    select(WorkerRow)
                    .order_by(WorkerRow.registered_at.desc())
                    .limit(page.limit)
                    .offset(page.offset)
                )
            )
            .scalars()
            .all()
        )
        return Page(
            items=[_to_domain(r) for r in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )
