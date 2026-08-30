from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from flux.db import Base
from flux.errors import ConflictError
from flux.models.domain import (
    ContextLength,
    Model,
    ModelVersion,
    Precision,
    VersionStatus,
)
from flux.pagination import Page, PageParams


class ModelRow(Base):
    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_models_tenant_name"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    family: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ModelVersionRow(Base):
    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("model_id", "version", name="uq_versions_model_version"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    precision: Mapped[str] = mapped_column(String(16), nullable=False)
    context_length: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


def _to_model(row: ModelRow) -> Model:
    return Model(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        family=row.family,
        created_at=row.created_at,
    )


def _to_version(row: ModelVersionRow) -> ModelVersion:
    return ModelVersion(
        id=row.id,
        model_id=row.model_id,
        tenant_id=row.tenant_id,
        version=row.version,
        precision=Precision(row.precision),
        context_length=ContextLength(row.context_length),
        status=VersionStatus(row.status),
        created_at=row.created_at,
    )


class SqlAlchemyModelRepository:
    """SQLAlchemy adapter implementing the ModelRepository port.

    Each write is committed as its own transaction; unique-constraint races
    are translated into ConflictError so callers never leak driver errors.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_model(self, model: Model) -> None:
        self._session.add(
            ModelRow(
                id=model.id,
                tenant_id=model.tenant_id,
                name=model.name,
                family=model.family,
                created_at=model.created_at,
            )
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(f"model already exists: {model.name}") from exc

    async def get_model(self, tenant_id: str, model_id: str) -> Model | None:
        row = await self._session.get(ModelRow, model_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _to_model(row)

    async def model_name_exists(self, tenant_id: str, name: str) -> bool:
        stmt = (
            select(func.count())
            .select_from(ModelRow)
            .where(ModelRow.tenant_id == tenant_id, ModelRow.name == name)
        )
        return bool((await self._session.execute(stmt)).scalar_one())

    async def list_models(
        self, tenant_id: str, *, family: str | None, page: PageParams
    ) -> Page[Model]:
        base = select(ModelRow).where(ModelRow.tenant_id == tenant_id)
        counter = (
            select(func.count())
            .select_from(ModelRow)
            .where(ModelRow.tenant_id == tenant_id)
        )
        if family:
            base = base.where(ModelRow.family == family)
            counter = counter.where(ModelRow.family == family)
        total = int((await self._session.execute(counter)).scalar_one())
        rows = (
            (
                await self._session.execute(
                    base.order_by(ModelRow.created_at.desc())
                    .limit(page.limit)
                    .offset(page.offset)
                )
            )
            .scalars()
            .all()
        )
        return Page(
            items=[_to_model(r) for r in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )

    async def add_version(self, version: ModelVersion) -> None:
        self._session.add(
            ModelVersionRow(
                id=version.id,
                model_id=version.model_id,
                tenant_id=version.tenant_id,
                version=version.version,
                precision=version.precision.value,
                context_length=version.context_length.value,
                status=version.status.value,
                created_at=version.created_at,
            )
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(
                f"version already exists: {version.version}"
            ) from exc

    async def list_versions(
        self, tenant_id: str, model_id: str, *, page: PageParams
    ) -> Page[ModelVersion]:
        predicate = (
            ModelVersionRow.tenant_id == tenant_id,
            ModelVersionRow.model_id == model_id,
        )
        total = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(ModelVersionRow)
                    .where(*predicate)
                )
            ).scalar_one()
        )
        rows = (
            (
                await self._session.execute(
                    select(ModelVersionRow)
                    .where(*predicate)
                    .order_by(ModelVersionRow.created_at.desc())
                    .limit(page.limit)
                    .offset(page.offset)
                )
            )
            .scalars()
            .all()
        )
        return Page(
            items=[_to_version(r) for r in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )
