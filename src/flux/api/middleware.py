from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from flux.logging import get_logger
from flux.observability import get_correlation_id, new_correlation_id, set_correlation_id

logger = get_logger(__name__)

CORRELATION_HEADER = "X-Request-ID"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Assign a correlation id to every request and echo it back."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        cid = request.headers.get(CORRELATION_HEADER) or new_correlation_id()
        set_correlation_id(cid)
        response = await call_next(request)
        response.headers[CORRELATION_HEADER] = cid
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Emit a structured access log line for every request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
            correlation_id=get_correlation_id(),
        )
        return response
