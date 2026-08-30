from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from flux.api.health import router as health_router
from flux.api.middleware import CorrelationIdMiddleware, RequestLoggingMiddleware
from flux.config import Settings, get_settings
from flux.db import create_engine, create_sessionmaker
from flux.errors import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    ProblemDetail,
    UnauthorizedError,
)
from flux.events import InProcessEventBus
from flux.logging import configure_logging, get_logger
from flux.models.router import router as models_router
from flux.observability import configure_tracing
from flux.tenancy.router import router as tenancy_router

logger = get_logger(__name__)

_PROBLEM_BASE = "https://flux.dev/problems"


def _problem(status_code: int, title: str, detail: str, slug: str) -> JSONResponse:
    problem = ProblemDetail(
        type=f"{_PROBLEM_BASE}/{slug}",
        title=title,
        status=status_code,
        detail=detail,
    )
    return JSONResponse(
        status_code=status_code,
        content=problem.to_dict(),
        media_type="application/problem+json",
    )


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return _problem(404, "Not Found", str(exc), "not-found")

    @app.exception_handler(ConflictError)
    async def _conflict(_: Request, exc: ConflictError) -> JSONResponse:
        return _problem(409, "Conflict", str(exc), "conflict")

    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        return _problem(422, "Unprocessable Entity", str(exc), "domain-error")

    @app.exception_handler(UnauthorizedError)
    async def _unauthorized(_: Request, exc: UnauthorizedError) -> JSONResponse:
        return _problem(401, "Unauthorized", str(exc), "unauthorized")

    @app.exception_handler(ForbiddenError)
    async def _forbidden(_: Request, exc: ForbiddenError) -> JSONResponse:
        return _problem(403, "Forbidden", str(exc), "forbidden")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    configure_tracing(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        app.state.engine = engine
        app.state.sessionmaker = create_sessionmaker(engine)
        app.state.event_bus = InProcessEventBus()
        logger.info("startup", env=settings.env, service=settings.service_name)
        try:
            yield
        finally:
            await engine.dispose()
            logger.info("shutdown")

    app = FastAPI(title="Flux Control Plane", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    _register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(models_router)
    app.include_router(tenancy_router)
    return app


app = create_app()
