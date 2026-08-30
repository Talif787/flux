from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from flux.models.domain import MAX_CONTEXT_LENGTH, Model, ModelVersion, Precision


class ModelCreateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    name: str = Field(min_length=1, max_length=255)
    family: str = Field(min_length=1, max_length=128)


class ModelResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    name: str
    family: str
    created_at: datetime

    @classmethod
    def from_domain(cls, model: Model) -> ModelResponse:
        return cls(
            id=model.id,
            name=model.name,
            family=model.family,
            created_at=model.created_at,
        )


class ModelVersionCreateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    version: str = Field(min_length=1, max_length=64)
    precision: Precision
    context_length: int = Field(ge=1, le=MAX_CONTEXT_LENGTH)


class ModelVersionResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    model_id: str
    version: str
    precision: Precision
    context_length: int
    status: str
    created_at: datetime

    @classmethod
    def from_domain(cls, version: ModelVersion) -> ModelVersionResponse:
        return cls(
            id=version.id,
            model_id=version.model_id,
            version=version.version,
            precision=version.precision,
            context_length=version.context_length.value,
            status=version.status.value,
            created_at=version.created_at,
        )


class PageMeta(BaseModel):
    total: int
    limit: int
    offset: int


class ModelListResponse(BaseModel):
    items: list[ModelResponse]
    meta: PageMeta


class ModelVersionListResponse(BaseModel):
    items: list[ModelVersionResponse]
    meta: PageMeta
