from __future__ import annotations

from dataclasses import dataclass

from flux.errors import ConflictError, NotFoundError
from flux.events import EventBus
from flux.models.domain import (
    ContextLength,
    Model,
    ModelRepository,
    ModelVersion,
    Precision,
)
from flux.pagination import Page, PageParams


@dataclass(frozen=True)
class RegisterModelCommand:
    tenant_id: str
    name: str
    family: str


@dataclass(frozen=True)
class RegisterModelVersionCommand:
    tenant_id: str
    model_id: str
    version: str
    precision: Precision
    context_length: int


class ModelService:
    """Application service orchestrating the model lifecycle use cases."""

    def __init__(self, repository: ModelRepository, event_bus: EventBus) -> None:
        self._repo = repository
        self._events = event_bus

    async def register_model(self, cmd: RegisterModelCommand) -> Model:
        if await self._repo.model_name_exists(cmd.tenant_id, cmd.name.strip()):
            raise ConflictError(f"model already exists: {cmd.name}")
        model, event = Model.register(
            tenant_id=cmd.tenant_id, name=cmd.name, family=cmd.family
        )
        await self._repo.add_model(model)
        await self._events.publish(event)
        return model

    async def get_model(self, tenant_id: str, model_id: str) -> Model:
        model = await self._repo.get_model(tenant_id, model_id)
        if model is None:
            raise NotFoundError("model", model_id)
        return model

    async def list_models(
        self, tenant_id: str, *, family: str | None, page: PageParams
    ) -> Page[Model]:
        return await self._repo.list_models(tenant_id, family=family, page=page)

    async def register_version(
        self, cmd: RegisterModelVersionCommand
    ) -> ModelVersion:
        model = await self._repo.get_model(cmd.tenant_id, cmd.model_id)
        if model is None:
            raise NotFoundError("model", cmd.model_id)
        version, event = ModelVersion.register(
            model_id=model.id,
            tenant_id=cmd.tenant_id,
            version=cmd.version,
            precision=cmd.precision,
            context_length=ContextLength(cmd.context_length),
        )
        await self._repo.add_version(version)
        await self._events.publish(event)
        return version

    async def list_versions(
        self, tenant_id: str, model_id: str, *, page: PageParams
    ) -> Page[ModelVersion]:
        if await self._repo.get_model(tenant_id, model_id) is None:
            raise NotFoundError("model", model_id)
        return await self._repo.list_versions(tenant_id, model_id, page=page)
