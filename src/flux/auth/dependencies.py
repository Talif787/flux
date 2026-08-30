from __future__ import annotations

import hashlib
import hmac
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from flux.api.deps import get_session
from flux.auth.domain import Principal
from flux.auth.persistence import AuthRepository, SqlAlchemyAuthRepository
from flux.config import Settings, get_settings
from flux.errors import ForbiddenError, UnauthorizedError


def hash_api_key(raw_key: str, pepper: str) -> str:
    """Keyed (HMAC-SHA256) hash of a high-entropy API key.

    API keys carry sufficient entropy that a fast keyed hash is appropriate;
    slow password hashes (argon2) are unnecessary and would tax the hot path.
    """
    return hmac.new(pepper.encode(), raw_key.encode(), hashlib.sha256).hexdigest()


def _extract_key(authorization: str | None, x_api_key: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if x_api_key:
        return x_api_key.strip()
    return None


async def get_current_principal(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> Principal:
    raw = _extract_key(authorization, x_api_key)
    if not raw:
        raise UnauthorizedError("missing API key")
    repo: AuthRepository = SqlAlchemyAuthRepository(session)
    principal = await repo.find_principal_by_key_hash(
        hash_api_key(raw, settings.api_key_pepper)
    )
    if principal is None:
        raise UnauthorizedError("invalid API key")
    return principal


def require_roles(
    *required: str,
) -> Callable[[Principal], Awaitable[Principal]]:
    """Dependency factory enforcing that the caller holds one of the roles."""

    async def _dependency(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if required and not any(principal.has_role(r) for r in required):
            raise ForbiddenError("insufficient role")
        return principal

    return _dependency
