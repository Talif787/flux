from __future__ import annotations

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

    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton (cached)."""
    return Settings()
