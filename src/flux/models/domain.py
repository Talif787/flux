from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from flux.errors import DomainError
from flux.events import DomainEvent
from flux.ids import new_id
from flux.pagination import Page, PageParams

MAX_CONTEXT_LENGTH = 1_048_576
MAX_NAME_LENGTH = 255


class Precision(StrEnum):
    FP32 = "fp32"
    FP16 = "fp16"
    BF16 = "bf16"
    FP8 = "fp8"
    INT8 = "int8"


class VersionStatus(StrEnum):
    REGISTERED = "registered"
    BUILDING = "building"
    BUILT = "built"
    DEPLOYED = "deployed"
    FAILED = "failed"


@dataclass(frozen=True)
class ContextLength:
    """Value object: a validated maximum context window in tokens."""

    value: int

    def __post_init__(self) -> None:
        if not 1 <= self.value <= MAX_CONTEXT_LENGTH:
            raise DomainError(f"context_length must be between 1 and {MAX_CONTEXT_LENGTH}")


@dataclass(frozen=True, kw_only=True)
class ModelRegistered(DomainEvent):
    model_id: str
    tenant_id: str
    name: str


@dataclass(frozen=True, kw_only=True)
class ModelVersionRegistered(DomainEvent):
    model_id: str
    version_id: str
    tenant_id: str
    version: str


@dataclass
class Model:
    """Aggregate root: a named model owned by a tenant."""

    id: str
    tenant_id: str
    name: str
    family: str
    created_at: datetime

    @staticmethod
    def register(*, tenant_id: str, name: str, family: str) -> tuple[Model, ModelRegistered]:
        clean_name = name.strip()
        if not clean_name:
            raise DomainError("model name must not be empty")
        if len(clean_name) > MAX_NAME_LENGTH:
            raise DomainError("model name too long")
        clean_family = family.strip()
        if not clean_family:
            raise DomainError("model family must not be empty")
        model = Model(
            id=new_id(),
            tenant_id=tenant_id,
            name=clean_name,
            family=clean_family,
            created_at=datetime.now(UTC),
        )
        event = ModelRegistered(model_id=model.id, tenant_id=tenant_id, name=clean_name)
        return model, event


@dataclass
class ModelVersion:
    """Aggregate root: a concrete, servable version of a model."""

    id: str
    model_id: str
    tenant_id: str
    version: str
    precision: Precision
    context_length: ContextLength
    status: VersionStatus
    created_at: datetime

    @staticmethod
    def register(
        *,
        model_id: str,
        tenant_id: str,
        version: str,
        precision: Precision,
        context_length: ContextLength,
    ) -> tuple[ModelVersion, ModelVersionRegistered]:
        clean_version = version.strip()
        if not clean_version:
            raise DomainError("version must not be empty")
        model_version = ModelVersion(
            id=new_id(),
            model_id=model_id,
            tenant_id=tenant_id,
            version=clean_version,
            precision=precision,
            context_length=context_length,
            status=VersionStatus.REGISTERED,
            created_at=datetime.now(UTC),
        )
        event = ModelVersionRegistered(
            model_id=model_id,
            version_id=model_version.id,
            tenant_id=tenant_id,
            version=clean_version,
        )
        return model_version, event


class ModelRepository(Protocol):
    """Persistence port for the model lifecycle context."""

    async def add_model(self, model: Model) -> None: ...
    async def get_model(self, tenant_id: str, model_id: str) -> Model | None: ...
    async def model_name_exists(self, tenant_id: str, name: str) -> bool: ...
    async def list_models(
        self, tenant_id: str, *, family: str | None, page: PageParams
    ) -> Page[Model]: ...
    async def add_version(self, version: ModelVersion) -> None: ...
    async def list_versions(
        self, tenant_id: str, model_id: str, *, page: PageParams
    ) -> Page[ModelVersion]: ...
