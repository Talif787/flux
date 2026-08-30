import logging
import sys

import structlog
from structlog.types import EventDict, WrappedLogger

from flux.config import Settings
from flux.observability import get_correlation_id


def _add_correlation_id(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    cid = get_correlation_id()
    if cid is not None:
        event_dict["correlation_id"] = cid
    return event_dict


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _add_correlation_id,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
