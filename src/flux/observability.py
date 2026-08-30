from __future__ import annotations

import contextvars
import uuid

from flux.config import Settings

_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def configure_tracing(settings: Settings) -> None:
    """Initialise OpenTelemetry tracing when enabled.

    Imports are performed lazily so the OTel SDK is only required when tracing
    is switched on, keeping local and test runs lightweight.
    """
    if not settings.otel_enabled:
        return

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": settings.service_name}))
    if settings.otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
        )
    trace.set_tracer_provider(provider)
