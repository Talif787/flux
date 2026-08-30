from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from flux.workers.domain import Worker


class WorkerRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=1, max_length=512)
    served_models: list[str] = Field(default_factory=list)
    max_concurrency: int = Field(default=8, ge=1)


class WorkerResponse(BaseModel):
    id: str
    name: str
    base_url: str
    served_models: list[str]
    max_concurrency: int
    status: str
    registered_at: datetime
    last_heartbeat_at: datetime

    @classmethod
    def from_domain(cls, worker: Worker) -> WorkerResponse:
        return cls(
            id=worker.id,
            name=worker.name,
            base_url=worker.base_url,
            served_models=sorted(worker.served_models),
            max_concurrency=worker.max_concurrency,
            status=worker.status.value,
            registered_at=worker.registered_at,
            last_heartbeat_at=worker.last_heartbeat_at,
        )


class PageMeta(BaseModel):
    total: int
    limit: int
    offset: int


class WorkerListResponse(BaseModel):
    items: list[WorkerResponse]
    meta: PageMeta
