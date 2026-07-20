from __future__ import annotations

import logging
from typing import Iterator

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from mplacas.core.config import Settings
from mplacas.observability.metrics import (
    OUTCOME_FAILURE,
    OUTCOME_SUCCESS,
    configure_metrics,
    record_operation,
    reset_metrics_state_for_tests,
)
from mplacas.observability.operations import observe_operation

logger = logging.getLogger("test_metrics")


@pytest.fixture
def metric_reader() -> Iterator[InMemoryMetricReader]:
    reader = InMemoryMetricReader()
    settings = Settings(_env_file=None)
    configure_metrics(settings=settings, service_name="mplacas-test", reader=reader)
    yield reader
    reset_metrics_state_for_tests()


def _collect_points(reader: InMemoryMetricReader) -> dict[str, list[object]]:
    data = reader.get_metrics_data()
    points: dict[str, list[object]] = {}
    if data is None:
        return points
    for resource_metric in data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                points.setdefault(metric.name, []).extend(metric.data.data_points)
    return points


def test_record_operation_emits_histogram_and_counter(
    metric_reader: InMemoryMetricReader,
) -> None:
    record_operation(operation="unit.test", outcome=OUTCOME_SUCCESS, duration_ms=42)

    points = _collect_points(metric_reader)
    assert "mplacas.operation.duration" in points
    assert "mplacas.operation.runs" in points
    histogram_point = points["mplacas.operation.duration"][0]
    counter_point = points["mplacas.operation.runs"][0]
    assert dict(histogram_point.attributes) == {
        "operation": "unit.test",
        "outcome": OUTCOME_SUCCESS,
    }
    assert histogram_point.sum == 42
    assert counter_point.value == 1


def test_record_operation_clamps_negative_duration(
    metric_reader: InMemoryMetricReader,
) -> None:
    record_operation(operation="unit.clamp", outcome=OUTCOME_SUCCESS, duration_ms=-5)

    points = _collect_points(metric_reader)
    histogram_point = points["mplacas.operation.duration"][0]
    assert histogram_point.sum == 0


def test_observe_operation_records_success_metric(
    metric_reader: InMemoryMetricReader,
) -> None:
    with observe_operation(logger, "metrics.success_case") as operation:
        operation.add_result(items=3)

    points = _collect_points(metric_reader)
    counter_point = points["mplacas.operation.runs"][0]
    assert dict(counter_point.attributes) == {
        "operation": "metrics.success_case",
        "outcome": OUTCOME_SUCCESS,
    }


def test_observe_operation_records_failure_metric(
    metric_reader: InMemoryMetricReader,
) -> None:
    with pytest.raises(RuntimeError):
        with observe_operation(logger, "metrics.failure_case"):
            raise RuntimeError("boom")

    points = _collect_points(metric_reader)
    counter_point = points["mplacas.operation.runs"][0]
    assert dict(counter_point.attributes) == {
        "operation": "metrics.failure_case",
        "outcome": OUTCOME_FAILURE,
    }


def test_metric_attributes_stay_low_cardinality(
    metric_reader: InMemoryMetricReader,
) -> None:
    with observe_operation(
        logger,
        "metrics.cardinality_case",
        plant_id="00000000-0000-0000-0000-000000000001",
        target_date="2026-07-19",
    ):
        pass

    points = _collect_points(metric_reader)
    for point in points["mplacas.operation.runs"]:
        assert set(point.attributes) == {"operation", "outcome"}


def test_metrics_disabled_keeps_recording_a_noop() -> None:
    reset_metrics_state_for_tests()
    settings = Settings(_env_file=None)
    runtime = configure_metrics(settings=settings, service_name="mplacas-test")
    assert runtime.provider is None
    record_operation(operation="noop.case", outcome=OUTCOME_SUCCESS, duration_ms=1)
    with observe_operation(logger, "noop.observed"):
        pass
