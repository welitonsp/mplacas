from __future__ import annotations

import re
import secrets
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Iterator

from opentelemetry import trace

_CLOUD_TRACE_PATTERN = re.compile(
    r"^(?P<trace>[0-9a-fA-F]{32})/(?P<span>[0-9]{1,20})(?:;o=(?P<sampled>[01]))?$"
)
_TRACEPARENT_PATTERN = re.compile(
    r"^00-(?P<trace>[0-9a-fA-F]{32})-"
    r"(?P<span>[0-9a-fA-F]{16})-(?P<flags>[0-9a-fA-F]{2})$"
)
_MAX_SPAN_ID = (1 << 64) - 1


@dataclass(frozen=True, slots=True)
class CorrelationContext:
    trace_id: str
    span_id: str | None
    trace_sampled: bool
    request_id: str | None = None


_CORRELATION: ContextVar[CorrelationContext | None] = ContextVar(
    "mplacas_correlation",
    default=None,
)


def parse_cloud_trace_context(value: str | None) -> CorrelationContext | None:
    if value is None:
        return None
    match = _CLOUD_TRACE_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    trace_id = match.group("trace").lower()
    span_number = int(match.group("span"))
    if int(trace_id, 16) == 0 or not 0 < span_number <= _MAX_SPAN_ID:
        return None
    return CorrelationContext(
        trace_id=trace_id,
        span_id=f"{span_number:016x}",
        trace_sampled=match.group("sampled") == "1",
    )


def parse_traceparent(value: str | None) -> CorrelationContext | None:
    if value is None:
        return None
    match = _TRACEPARENT_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    trace_id = match.group("trace").lower()
    span_id = match.group("span").lower()
    if int(trace_id, 16) == 0 or int(span_id, 16) == 0:
        return None
    return CorrelationContext(
        trace_id=trace_id,
        span_id=span_id,
        trace_sampled=bool(int(match.group("flags"), 16) & 1),
    )


def new_correlation_context(*, request_id: str | None = None) -> CorrelationContext:
    trace_id = secrets.token_hex(16)
    while int(trace_id, 16) == 0:
        trace_id = secrets.token_hex(16)
    return CorrelationContext(
        trace_id=trace_id,
        span_id=None,
        trace_sampled=False,
        request_id=request_id,
    )


def resolve_correlation_context(
    *,
    cloud_trace_header: str | None,
    traceparent_header: str | None,
    request_id: str | None,
) -> CorrelationContext:
    active = active_span_context()
    resolved = (
        active
        or parse_cloud_trace_context(cloud_trace_header)
        or parse_traceparent(traceparent_header)
        or new_correlation_context()
    )
    return CorrelationContext(
        trace_id=resolved.trace_id,
        span_id=resolved.span_id,
        trace_sampled=resolved.trace_sampled,
        request_id=request_id,
    )


def active_span_context() -> CorrelationContext | None:
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None
    return CorrelationContext(
        trace_id=f"{span_context.trace_id:032x}",
        span_id=f"{span_context.span_id:016x}",
        trace_sampled=span_context.trace_flags.sampled,
    )


def current_correlation_context() -> CorrelationContext | None:
    active = active_span_context()
    bound = _CORRELATION.get()
    if active is None:
        return bound
    return CorrelationContext(
        trace_id=active.trace_id,
        span_id=active.span_id,
        trace_sampled=active.trace_sampled,
        request_id=bound.request_id if bound is not None else None,
    )


@contextmanager
def bind_correlation_context(context: CorrelationContext) -> Iterator[None]:
    token: Token[CorrelationContext | None] = _CORRELATION.set(context)
    try:
        yield
    finally:
        _CORRELATION.reset(token)
