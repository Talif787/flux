from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Twelve-factor configuration sourced from the environment.

    All settings are prefixed with ``FLUX_`` and may be supplied via a local
    ``.env`` file during development. Production supplies them as real env vars.
    """

    model_config = SettingsConfigDict(
        env_prefix="FLUX_", env_file=".env", extra="ignore", frozen=True
    )

    env: Literal["local", "dev", "staging", "prod"] = "local"
    service_name: str = "flux-control-plane"

    log_level: str = "INFO"
    log_json: bool = True

    database_url: str = "postgresql+asyncpg://flux:flux@localhost:5432/flux"
    db_echo: bool = False
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=20, ge=0)
    db_pool_recycle: int = Field(default=1800, ge=0)

    api_key_pepper: str = Field(default="change-me", min_length=1)

    # Request plane (serving) controls.
    serving_backend: Literal["stub", "remote"] = "stub"
    rate_limit_enabled: bool = True
    rate_limit_rps: float = Field(default=10.0, ge=0.0)
    rate_limit_burst: int = Field(default=20, ge=1)
    max_concurrency: int = Field(default=32, ge=1)
    max_queue: int = Field(default=64, ge=0)
    idempotency_enabled: bool = True
    worker_heartbeat_ttl_seconds: int = Field(default=60, ge=1)
    remote_request_timeout_seconds: float = Field(default=30.0, gt=0.0)
    metering_enabled: bool = True
    default_prompt_per_1k: Decimal = Field(default=Decimal("0.0005"), ge=0)
    default_completion_per_1k: Decimal = Field(default=Decimal("0.0015"), ge=0)
    billing_currency: str = "USD"

    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton (cached)."""
    return Settings()
