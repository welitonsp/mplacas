from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from mplacas.observability.context import current_correlation_context

_STANDARD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
}


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID, Enum)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)


class CloudJsonFormatter(logging.Formatter):
    """Render one Cloud Logging-compatible JSON object per line."""

    def __init__(self, *, service_name: str, project_id: str | None) -> None:
        super().__init__()
        self._service_name = service_name
        self._project_id = project_id

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "service": self._service_name,
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_FIELDS and not key.startswith("_"):
                payload[key] = _json_safe(value)

        correlation = current_correlation_context()
        if correlation is not None:
            payload["trace_id"] = correlation.trace_id
            payload["trace_sampled"] = correlation.trace_sampled
            if correlation.request_id is not None:
                payload["request_id"] = correlation.request_id
            if correlation.span_id is not None:
                payload["span_id"] = correlation.span_id
                payload["logging.googleapis.com/spanId"] = correlation.span_id
            if self._project_id is not None:
                payload["logging.googleapis.com/trace"] = (
                    f"projects/{self._project_id}/traces/{correlation.trace_id}"
                )
                payload["logging.googleapis.com/trace_sampled"] = correlation.trace_sampled

        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(
    *,
    level: str,
    service_name: str,
    project_id: str | None,
    structured: bool,
) -> None:
    handler = logging.StreamHandler(sys.stdout)
    if structured:
        handler.setFormatter(
            CloudJsonFormatter(service_name=service_name, project_id=project_id)
        )
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    logging.basicConfig(
        level=level.upper(),
        handlers=[handler],
    )
