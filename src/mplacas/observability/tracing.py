from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI
from opentelemetry import propagate, trace
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor, RequestInfo
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Span
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from sqlalchemy.ext.asyncio import AsyncEngine

from mplacas import __version__
from mplacas.core.config import Settings
from mplacas.observability.logging import configure_logging
from mplacas.observability.metrics import MetricsRuntime, configure_metrics
from mplacas.observability.propagation import CloudTraceContextPropagator

_TELEGRAM_TOKEN = re.compile(r"/bot[^/]+")
_TRACER_NAME = "mplacas"
_runtime: ObservabilityRuntime | None = None


@dataclass(slots=True)
class ObservabilityRuntime:
    provider: TracerProvider | None = None
    metrics: MetricsRuntime | None = None

    def shutdown(self) -> None:
        if self.provider is not None:
            self.provider.force_flush(timeout_millis=5000)
            self.provider.shutdown()
        if self.metrics is not None:
            self.metrics.shutdown()


def configure_observability(
    *,
    settings: Settings,
    service_name: str,
    app: FastAPI | None = None,
    engine: AsyncEngine | None = None,
) -> ObservabilityRuntime:
    global _runtime
    configure_logging(
        level=settings.log_level,
        service_name=service_name,
        project_id=settings.gcp_project_id,
        structured=settings.env == "production",
    )
    metrics_runtime = configure_metrics(settings=settings, service_name=service_name)
    if not settings.cloud_trace_enabled:
        return ObservabilityRuntime(metrics=metrics_runtime)
    if _runtime is not None:
        return _runtime

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": __version__,
            "deployment.environment.name": settings.env,
        }
    )
    provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(settings.trace_sample_rate)),
    )
    provider.add_span_processor(
        BatchSpanProcessor(CloudTraceSpanExporter(project_id=settings.gcp_project_id))
    )
    trace.set_tracer_provider(provider)
    propagate.set_global_textmap(
        CompositePropagator(
            [
                TraceContextTextMapPropagator(),
                W3CBaggagePropagator(),
                CloudTraceContextPropagator(),
            ]
        )
    )
    if app is not None:
        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=provider,
            server_request_hook=_sanitize_server_span,
            exclude_spans=["receive", "send"],
        )
    if engine is not None:
        SQLAlchemyInstrumentor().instrument(
            engine=engine.sync_engine,
            tracer_provider=provider,
        )
    HTTPXClientInstrumentor().instrument(
        tracer_provider=provider,
        request_hook=_sanitize_http_span,
        async_request_hook=_sanitize_async_http_span,
    )
    _runtime = ObservabilityRuntime(provider=provider, metrics=metrics_runtime)
    return _runtime


def sanitized_http_url(request: RequestInfo) -> str:
    parsed = urlsplit(str(request.url))
    path = parsed.path
    if (parsed.hostname or "").lower() == "api.telegram.org":
        path = _TELEGRAM_TOKEN.sub("/bot<redacted>", path, count=1)
    hostname = parsed.hostname or ""
    netloc = f"[{hostname}]" if ":" in hostname else hostname
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, path, "", ""))


def _sanitize_http_span(span: Span, request: RequestInfo) -> None:
    if not span.is_recording():
        return
    safe_url = sanitized_http_url(request)
    span.set_attribute("http.url", safe_url)
    span.set_attribute("url.full", safe_url)
    span.set_attribute("url.query", "")
    span.set_attribute("http.target", urlsplit(safe_url).path)


async def _sanitize_async_http_span(span: Span, request: RequestInfo) -> None:
    _sanitize_http_span(span, request)


def _sanitize_server_span(span: Span, scope: dict[str, object]) -> None:
    if not span.is_recording():
        return
    path = str(scope.get("path") or "/")
    span.set_attribute("url.query", "")
    span.set_attribute("http.target", path)


@contextmanager
def traced_operation(name: str, **attributes: object) -> Iterator[Span]:
    tracer = trace.get_tracer(_TRACER_NAME)
    safe_attributes = {
        key: value
        for key, value in attributes.items()
        if isinstance(value, (bool, int, float, str))
    }
    with tracer.start_as_current_span(name, attributes=safe_attributes) as span:
        yield span
