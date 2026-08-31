from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


class FluxError(Exception):
    """Base class for all application errors."""


class DomainError(FluxError):
    """Raised when a domain invariant is violated."""


class NotFoundError(FluxError):
    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(f"{resource} not found: {identifier}")
        self.resource = resource
        self.identifier = identifier


class ConflictError(FluxError):
    """Raised when an operation conflicts with existing state."""


class UnauthorizedError(FluxError):
    """Raised when authentication fails or is missing."""


class ForbiddenError(FluxError):
    """Raised when an authenticated principal lacks permission."""


class RateLimitError(FluxError):
    """Raised when a caller exceeds its rate limit."""

    def __init__(self, retry_after: float) -> None:
        super().__init__("rate limit exceeded")
        self.retry_after = retry_after


class OverloadedError(FluxError):
    """Raised when the serving queue is saturated and cannot admit work."""


class IdempotencyMismatchError(FluxError):
    """Raised when an idempotency key is reused with a different request."""


class NoWorkerAvailableError(FluxError):
    """Raised when no healthy worker serves the requested model."""


class UpstreamError(FluxError):
    """Raised when a worker returns an error or cannot be reached."""


class BudgetExceededError(FluxError):
    """Raised when a tenant has spent past its monthly budget."""

    def __init__(self, tenant_id: str, limit: Decimal, spent: Decimal) -> None:
        super().__init__(f"monthly budget exceeded for tenant {tenant_id}")
        self.tenant_id = tenant_id
        self.limit = limit
        self.spent = spent


@dataclass(frozen=True)
class ProblemDetail:
    """RFC 9457 problem details representation."""

    type: str
    title: str
    status: int
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
        }
