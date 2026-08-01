from __future__ import annotations

import json
import logging
from io import StringIO

import httpx
from opentelemetry import trace
from opentelemetry.instrumentation.httpx import RequestInfo

from mplacas.observability.context import (
    CorrelationContext,
    bind_correlation_context,
    current_correlation_context,
    parse_cloud_trace_context,
    parse_traceparent,
)
from mplacas.observability.logging import CloudJsonFormatter, SecretRedactionFilter
from mplacas.observability.operations import observe_operation
from mplacas.observability.propagation import CloudTraceContextPropagator
from mplacas.observability.sanitize import redact_secrets
from mplacas.observability.tracing import sanitized_http_url

TRACE_ID = "0123456789abcdef0123456789abcdef"
SPAN_ID = "0123456789abcdef"


def test_cloud_and_w3c_trace_headers_are_parsed_strictly() -> None:
    cloud = parse_cloud_trace_context(f"{TRACE_ID}/74;o=1")
    w3c = parse_traceparent(f"00-{TRACE_ID}-{SPAN_ID}-01")

    assert cloud == CorrelationContext(
        trace_id=TRACE_ID,
        span_id="000000000000004a",
        trace_sampled=True,
    )
    assert w3c == CorrelationContext(
        trace_id=TRACE_ID,
        span_id=SPAN_ID,
        trace_sampled=True,
    )
    assert parse_cloud_trace_context(f"{'0' * 32}/1;o=1") is None
    assert parse_cloud_trace_context(f"{TRACE_ID}/0;o=1") is None
    assert parse_traceparent(f"00-{TRACE_ID}-{'0' * 16}-01") is None
    assert parse_traceparent(f"ff-{TRACE_ID}-{SPAN_ID}-01") is None


def test_cloud_trace_propagator_extracts_and_injects_remote_parent() -> None:
    propagator = CloudTraceContextPropagator()
    extracted = propagator.extract(
        {"x-cloud-trace-context": f"{TRACE_ID}/81985529216486895;o=1"}
    )
    extracted_span = trace.get_current_span(extracted).get_span_context()

    assert f"{extracted_span.trace_id:032x}" == TRACE_ID
    assert f"{extracted_span.span_id:016x}" == SPAN_ID
    assert extracted_span.is_remote is True
    assert extracted_span.trace_flags.sampled is True

    carrier: dict[str, str] = {}
    propagator.inject(carrier, context=extracted)
    assert carrier["x-cloud-trace-context"] == (
        f"{TRACE_ID}/{int(SPAN_ID, 16)};o=1"
    )


def test_json_formatter_emits_cloud_trace_special_fields_without_secrets() -> None:
    formatter = CloudJsonFormatter(
        service_name="mplacas-api",
        project_id="synthetic-project",
    )
    record = logging.LogRecord(
        name="mplacas.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request_completed",
        args=(),
        exc_info=None,
    )
    record.plant_count = 2
    correlation = CorrelationContext(
        trace_id=TRACE_ID,
        span_id=SPAN_ID,
        trace_sampled=True,
        request_id="request-1",
    )

    with bind_correlation_context(correlation):
        payload = json.loads(formatter.format(record))

    assert payload["severity"] == "INFO"
    assert payload["request_id"] == "request-1"
    assert payload["logging.googleapis.com/trace"] == (
        f"projects/synthetic-project/traces/{TRACE_ID}"
    )
    assert payload["logging.googleapis.com/spanId"] == SPAN_ID
    assert payload["logging.googleapis.com/trace_sampled"] is True
    assert payload["plant_count"] == 2


def test_observed_operation_logs_duration_and_result(caplog) -> None:
    logger = logging.getLogger("mplacas.observability.test")
    caplog.set_level("INFO", logger=logger.name)

    with observe_operation(logger, "synthetic_stage", plant_id="plant-1") as operation:
        operation.add_result(received=3)

    completed = [record for record in caplog.records if record.message == "operation_completed"]
    assert completed[-1].operation == "synthetic_stage"
    assert completed[-1].received == 3
    assert completed[-1].duration_ms >= 0


def test_http_trace_url_drops_query_and_redacts_telegram_token() -> None:
    request = httpx.Request(
        "POST",
        "https://user:password@api.telegram.org/botsecret-value/sendMessage?chat_id=private",
    )
    request_info = RequestInfo(
        method=b"POST",
        url=request.url,
        headers=None,
        stream=None,
        extensions=None,
    )

    safe = sanitized_http_url(request_info)

    assert safe == "https://api.telegram.org/bot<redacted>/sendMessage"
    assert "secret-value" not in safe
    assert "chat_id" not in safe


def _capture_with_filter(record: logging.LogRecord) -> str:
    buffer = StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(SecretRedactionFilter())
    handler.handle(record)
    return buffer.getvalue()


def test_secret_redaction_filter_scrubs_token_embedded_directly_in_message() -> None:
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="HTTP Request: POST https://api.telegram.org/botsecret-value/sendMessage",
        args=(),
        exc_info=None,
    )

    output = _capture_with_filter(record)

    assert "secret-value" not in output
    assert "/bot<redacted>" in output


def test_secret_redaction_filter_scrubs_token_passed_via_lazy_args() -> None:
    # Mirrors httpx's own logging call:
    # logger.info('HTTP Request: %s %s "%s %d %s"', method, url, http_version, status, reason)
    request = httpx.Request(
        "POST", "https://api.telegram.org/botsecret-value/sendMessage"
    )
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='HTTP Request: %s %s "%s %d %s"',
        args=("POST", request.url, "HTTP/1.1", 200, "OK"),
        exc_info=None,
    )

    output = _capture_with_filter(record)

    assert "secret-value" not in output
    assert "/bot<redacted>" in output
    assert "200" in output
    assert "OK" in output


def test_secret_redaction_filter_leaves_normal_log_messages_intact() -> None:
    record = logging.LogRecord(
        name="mplacas.nepviewer",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="fetched %s readings for station %s",
        args=(42, "station-1"),
        exc_info=None,
    )

    output = _capture_with_filter(record)

    assert output.strip() == "fetched 42 readings for station station-1"


def test_secret_redaction_filter_keeps_cloud_json_formatter_valid() -> None:
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='HTTP Request: %s %s "%s %d %s"',
        args=(
            "POST",
            "https://api.telegram.org/botsecret-value/sendMessage",
            "HTTP/1.1",
            200,
            "OK",
        ),
        exc_info=None,
    )
    SecretRedactionFilter().filter(record)
    formatter = CloudJsonFormatter(service_name="mplacas-api", project_id=None)

    payload = json.loads(formatter.format(record))

    assert "secret-value" not in json.dumps(payload)
    assert "/bot<redacted>" in payload["message"]


def test_redact_secrets_only_touches_known_patterns() -> None:
    assert redact_secrets("plain text with no secrets") == "plain text with no secrets"
    assert (
        redact_secrets("https://api.telegram.org/bot123:ABC-token/sendMessage")
        == "https://api.telegram.org/bot<redacted>/sendMessage"
    )


def test_redact_secrets_does_not_mangle_lookalike_unrelated_paths() -> None:
    assert redact_secrets("POST /bots/create 201") == "POST /bots/create 201"
    assert redact_secrets("checking /bot-status page") == "checking /bot-status page"


def _make_chained_telegram_http_error() -> Exception:
    token = "8916381999:AAF-X7zOBPpmq1adI40E99AKxqzHST0wstM"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    request = httpx.Request("POST", url)
    response = httpx.Response(400, request=request, json={"ok": False})
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as status_error:
        try:
            # Mirror the "wrap and re-raise" pattern used elsewhere in the
            # codebase (e.g. TelegramClientError(...) from exc): the outer
            # exception's message is generic, but the original, token-
            # bearing exception is preserved as __cause__ and still gets
            # rendered by traceback formatting.
            raise RuntimeError("telegram delivery request failed") from status_error
        except RuntimeError as wrapped:
            return wrapped
    raise AssertionError("expected raise_for_status to raise")


def test_secret_redaction_filter_scrubs_token_from_exception_and_chained_cause() -> None:
    error = _make_chained_telegram_http_error()
    try:
        raise error
    except RuntimeError:
        record = logging.LogRecord(
            name="mplacas.alerts",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="operation_failed",
            args=(),
            exc_info=(type(error), error, error.__traceback__),
        )

    text_output = _capture_with_filter(record)
    assert "8916381999" not in text_output
    assert "wstM" not in text_output
    assert "/bot<redacted>" in text_output
    # The chained cause (httpx.HTTPStatusError, whose str() embeds the URL)
    # must be redacted too, not just the top-level RuntimeError.
    assert "api.telegram.org" in text_output


def test_secret_redaction_filter_scrubs_token_from_exception_in_json_formatter() -> None:
    error = _make_chained_telegram_http_error()
    try:
        raise error
    except RuntimeError:
        record = logging.LogRecord(
            name="mplacas.alerts",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="operation_failed",
            args=(),
            exc_info=(type(error), error, error.__traceback__),
        )

    SecretRedactionFilter().filter(record)
    formatter = CloudJsonFormatter(service_name="mplacas-api", project_id=None)
    payload = json.loads(formatter.format(record))
    serialized = json.dumps(payload)

    assert "8916381999" not in serialized
    assert "wstM" not in serialized
    assert "/bot<redacted>" in payload["exception"]


def test_bound_context_is_reset() -> None:
    correlation = CorrelationContext(
        trace_id=TRACE_ID,
        span_id=None,
        trace_sampled=False,
    )
    with bind_correlation_context(correlation):
        assert current_correlation_context() == correlation
    assert current_correlation_context() is None
