from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from mplacas.observability.context import current_correlation_context
from mplacas.observability.sanitize import redact_secrets

_STANDARD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
}

# Used only to render tracebacks (``formatException``) ahead of the record
# reaching a handler's own formatter, so we can redact the text before it is
# ever cached on ``record.exc_text``. Stateless besides the default format
# string, which is irrelevant here since only ``formatException`` is used.
_EXCEPTION_TEXT_FORMATTER = logging.Formatter()


class SecretRedactionFilter(logging.Filter):
    """Redact known secrets (e.g. Telegram bot tokens) from log records.

    Third-party libraries such as httpx log the full request URL at INFO
    level (``HTTP Request: %s %s "%s %d %s"``), and the Telegram Bot API
    embeds the bot token in the URL path. This filter scrubs
    ``record.msg``, ``record.args`` and the rendered exception/traceback
    (``record.exc_info``/``record.exc_text``) so the secret never reaches a
    handler/formatter, regardless of which logger emitted it, whether the
    message uses lazy ``%``-style formatting, or whether it surfaces via a
    raised (and possibly chained, ``raise ... from exc``) exception whose
    ``str()`` embeds the offending URL — e.g. ``httpx.HTTPStatusError``.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    key: self._redact_arg(value) for key, value in record.args.items()
                }
            else:
                record.args = tuple(self._redact_arg(arg) for arg in record.args)
        if record.exc_info:
            # Render the traceback ourselves (traceback.print_exception,
            # via logging.Formatter.formatException, walks the full
            # __cause__/__context__ chain) *before* any handler formatter
            # gets a chance to compute and cache the unsanitized text on
            # record.exc_text. Clearing exc_info afterwards prevents
            # downstream formatters from re-rendering the raw traceback.
            record.exc_text = redact_secrets(
                _EXCEPTION_TEXT_FORMATTER.formatException(record.exc_info)
            )
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact_secrets(record.exc_text)
        return True

    @staticmethod
    def _redact_arg(value: object) -> object:
        if isinstance(value, str):
            return redact_secrets(value)
        text = str(value)
        redacted = redact_secrets(text)
        return redacted if redacted != text else value


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

        if record.exc_text:
            payload["exception"] = record.exc_text
        elif record.exc_info is not None:
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
    handler.addFilter(SecretRedactionFilter())
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
