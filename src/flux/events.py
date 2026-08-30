from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from flux.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


EventHandler = Callable[[DomainEvent], Awaitable[None]]


class EventBus(Protocol):
    async def publish(self, event: DomainEvent) -> None: ...


class InProcessEventBus:
    """In-process event bus.

    Phase 1 uses in-process dispatch; the same port is later backed by a
    durable broker (NATS/Redis Streams) without changing callers.
    """

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[EventHandler]] = {}

    def subscribe(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def publish(self, event: DomainEvent) -> None:
        logger.info(
            "domain_event",
            event_type=type(event).__name__,
            event_id=event.event_id,
        )
        for handler in self._handlers.get(type(event), []):
            await handler(event)
