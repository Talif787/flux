from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from flux.api.deps import get_session

router = APIRouter(tags=["health"])


@router.get("/livez")
async def livez() -> dict[str, str]:
    """Liveness: the process is running and can serve requests."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(
    session: Annotated[AsyncSession, Depends(get_session)], response: Response
) -> dict[str, str]:
    """Readiness: dependencies (database) are reachable."""
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}
    return {"status": "ready"}


@router.get("/healthz")
async def healthz(
    session: Annotated[AsyncSession, Depends(get_session)], response: Response
) -> dict[str, str]:
    """Aggregate health check."""
    return await readyz(session, response)
