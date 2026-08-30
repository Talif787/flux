from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from flux.pagination import Page, PageParams


class WorkerStatus(StrEnum):
    ACTIVE = "active"
    DRAINING = "draining"


@dataclass(frozen=True)
class Worker:
    """A registered compute-plane node.

    Workers are platform-global (not tenant-scoped). ``served_models`` is the set
    of model names the worker can serve; an empty set means it serves any model.
    """

    id: str
    name: str
    base_url: str
    served_models: frozenset[str]
    max_concurrency: int
    status: WorkerStatus
    registered_at: datetime
    last_heartbeat_at: datetime


class WorkerRepository(Protocol):
    async def get(self, worker_id: str) -> Worker | None: ...
    async def upsert(self, worker: Worker) -> None: ...
    async def delete(self, worker_id: str) -> bool: ...
    async def list(self, page: PageParams) -> Page[Worker]: ...
