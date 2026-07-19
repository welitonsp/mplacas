from __future__ import annotations

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.propagators.textmap import (
    CarrierT,
    Getter,
    Setter,
    TextMapPropagator,
    default_getter,
    default_setter,
)
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags, TraceState

from mplacas.observability.context import parse_cloud_trace_context

_HEADER = "x-cloud-trace-context"


class CloudTraceContextPropagator(TextMapPropagator):
    """Propagate the header injected by Google Cloud's frontend."""

    def extract(
        self,
        carrier: CarrierT,
        context: Context | None = None,
        getter: Getter[CarrierT] = default_getter,
    ) -> Context:
        base = context or Context()
        values = getter.get(carrier, _HEADER)
        parsed = parse_cloud_trace_context(values[0] if values else None)
        if parsed is None or parsed.span_id is None:
            return base
        span_context = SpanContext(
            trace_id=int(parsed.trace_id, 16),
            span_id=int(parsed.span_id, 16),
            is_remote=True,
            trace_flags=TraceFlags(TraceFlags.SAMPLED if parsed.trace_sampled else 0),
            trace_state=TraceState(),
        )
        return trace.set_span_in_context(NonRecordingSpan(span_context), base)

    def inject(
        self,
        carrier: CarrierT,
        context: Context | None = None,
        setter: Setter[CarrierT] = default_setter,
    ) -> None:
        span_context = trace.get_current_span(context).get_span_context()
        if not span_context.is_valid:
            return
        sampled = "1" if span_context.trace_flags.sampled else "0"
        setter.set(
            carrier,
            _HEADER,
            f"{span_context.trace_id:032x}/{span_context.span_id};o={sampled}",
        )

    @property
    def fields(self) -> set[str]:
        return {_HEADER}
