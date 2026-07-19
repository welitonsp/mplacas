from __future__ import annotations

import logging
from contextlib import contextmanager
from time import monotonic
from typing import Iterator

from opentelemetry.trace import Span

from mplacas.observability.tracing import traced_operation


class ObservedOperation:
    def __init__(self, span: Span) -> None:
        self._span = span
        self._result: dict[str, bool | int | float | str] = {}

    def add_result(self, **fields: bool | int | float | str) -> None:
        self._result.update(fields)
        for key, value in fields.items():
            self._span.set_attribute(f"result.{key}", value)

    @property
    def result(self) -> dict[str, bool | int | float | str]:
        return dict(self._result)


@contextmanager
def observe_operation(
    logger: logging.Logger,
    operation: str,
    **fields: bool | int | float | str,
) -> Iterator[ObservedOperation]:
    started = monotonic()
    logger.info(
        "operation_started",
        extra={"operation": operation, **fields},
    )
    with traced_operation(operation, **fields) as span:
        observed = ObservedOperation(span)
        try:
            yield observed
        except Exception as exc:
            duration_ms = max(0, round((monotonic() - started) * 1000))
            span.set_attribute("operation.duration_ms", duration_ms)
            span.set_attribute("error.code", type(exc).__name__)
            logger.exception(
                "operation_failed",
                extra={
                    "operation": operation,
                    "duration_ms": duration_ms,
                    "error_code": type(exc).__name__,
                    **fields,
                },
            )
            raise
        duration_ms = max(0, round((monotonic() - started) * 1000))
        span.set_attribute("operation.duration_ms", duration_ms)
        logger.info(
            "operation_completed",
            extra={
                "operation": operation,
                "duration_ms": duration_ms,
                **fields,
                **observed.result,
            },
        )
