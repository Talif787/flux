from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from flux.logging import get_logger
from flux.worker.backend import EchoBackend, InferenceBackend
from flux.worker.config import WorkerSettings, get_worker_settings
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
        try:
            yield
        finally:
            logger.info("worker_shutdown")

    app = FastAPI(title="Flux Worker", version="0.4.0", lifespan=lifespan)
    app.include_router(worker_router)
    return app


app = create_worker_app()
