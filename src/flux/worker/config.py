from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
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
    backend: Literal["echo", "openai"] = "echo"
    # Upstream OpenAI-compatible server (vLLM, Ollama, TGI, or OpenAI) for the
    # openai backend. base_url should include the /v1 path.
    upstream_base_url: str = ""
    upstream_api_key: str = ""
    upstream_model: str = ""  # override the model name sent upstream; empty uses the request model
    request_timeout_seconds: float = Field(default=60.0, gt=0.0)
    served_models: str = ""  # comma-separated; empty means serve any model
    max_tokens_cap: int = Field(default=4096, ge=1)

    # Self-registration with the control plane (all three required to enable).
    control_plane_url: str = ""
    advertise_url: str = ""
    api_key: str = ""
    worker_id: str = ""  # stable id for idempotent re-registration; defaults to name
    max_concurrency: int = Field(default=8, ge=1)
    heartbeat_interval_seconds: float = Field(default=10.0, gt=0.0)
    register_retries: int = Field(default=5, ge=0)
    register_retry_delay_seconds: float = Field(default=2.0, gt=0.0)

    @model_validator(mode="after")
    def _require_upstream_for_openai(self) -> WorkerSettings:
        if self.backend == "openai" and not self.upstream_base_url:
            raise ValueError("backend=openai requires FLUX_WORKER_UPSTREAM_BASE_URL")
        return self

    @property
    def served_model_set(self) -> frozenset[str]:
        return frozenset(m.strip() for m in self.served_models.split(",") if m.strip())

    @property
    def effective_worker_id(self) -> str:
        return self.worker_id or self.worker_name

    @property
    def registration_enabled(self) -> bool:
        return bool(self.control_plane_url and self.advertise_url and self.api_key)


@lru_cache
def get_worker_settings() -> WorkerSettings:
    return WorkerSettings()
