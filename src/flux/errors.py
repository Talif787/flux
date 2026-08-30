from __future__ import annotations

from dataclasses import dataclass


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
