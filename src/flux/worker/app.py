from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from flux.logging import get_logger
from flux.worker.backend import EchoBackend, InferenceBackend
from flux.worker.config import WorkerSettings, get_worker_settings
from flux.worker.registration import (
    RegistrationClient,
    heartbeat_loop,
    register_with_retry,
)
from flux.worker.router import router as worker_router

logger = get_logger(__name__)


def _build_backend(settings: WorkerSettings) -> InferenceBackend:
    # settings.backend is Literal["echo"] today; this is the seam for real engines.
    return EchoBackend()


def create_worker_app(settings: WorkerSettings | None = None) -> FastAPI:
    settings = settings or get_worker_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.backend = _build_backend(settings)
        logger.info(
            "worker_startup",
            worker=settings.worker_name,
            backend=settings.backend,
            models=sorted(settings.served_model_set),
        )
        registration: RegistrationClient | None = None
        heartbeat_task: asyncio.Task[None] | None = None
        if settings.registration_enabled:
            registration = RegistrationClient(
                control_plane_url=settings.control_plane_url,
                api_key=settings.api_key,
                worker_id=settings.effective_worker_id,
                name=settings.worker_name,
                advertise_url=settings.advertise_url,
                served_models=sorted(settings.served_model_set),
                max_concurrency=settings.max_concurrency,
            )
            registered = await register_with_retry(
                registration,
                retries=settings.register_retries,
                delay=settings.register_retry_delay_seconds,
            )
            if registered:
                logger.info("worker_registered", worker=settings.effective_worker_id)
                heartbeat_task = asyncio.create_task(
                    heartbeat_loop(registration, settings.heartbeat_interval_seconds)
                )
        try:
            yield
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat_task
            if registration is not None:
                await registration.deregister()
                await registration.aclose()
            logger.info("worker_shutdown")

    app = FastAPI(title="Flux Worker", version="0.4.0", lifespan=lifespan)
    app.include_router(worker_router)
    return app


app = create_worker_app()
