from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    """Configuration for a Flux worker (compute-plane node).

    Prefixed with ``FLUX_WORKER_`` and read from an optional ``.env.worker`` file,
    kept separate from the control plane's ``.env`` so a worker and the control
    plane can run side by side.
    """

    model_config = SettingsConfigDict(
        env_prefix="FLUX_WORKER_",
        env_file=".env.worker",
        extra="ignore",
        frozen=True,
    )

    worker_name: str = "flux-worker"
    backend: Literal["echo"] = "echo"
    served_models: str = ""  # comma-separated; empty means serve any model
    max_tokens_cap: int = Field(default=4096, ge=1)

    @property
    def served_model_set(self) -> frozenset[str]:
        return frozenset(m.strip() for m in self.served_models.split(",") if m.strip())


@lru_cache
def get_worker_settings() -> WorkerSettings:
    return WorkerSettings()
