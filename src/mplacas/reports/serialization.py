from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from typing import Protocol

from mplacas.reports.contract import MonthlyEnergyReport, ReportMetric
from mplacas.reports.report_projection import ENGINE_SOURCE


class CsvRowWriter(Protocol):
    def writerow(self, row: Iterable[object]) -> object: ...


def serialize_monthly_report(report: MonthlyEnergyReport) -> dict[str, object]:
    trend: dict[str, object] | None = None
    if report.trend is not None:
        trend = {
            "current_reference_month": report.trend.current_reference_month,
            "previous_reference_month": report.trend.previous_reference_month,
            "metrics": [
                {
                    "key": item.key,
                    "label": item.label,
                    "absolute_delta": item.absolute_delta,
                    "unit": item.unit,
                    "percent_delta": item.percent_delta,
                    "direction": item.direction,
                }
                for item in report.trend.metrics
            ],
            "diagnostics": [
                {
                    "code": item.code,
                    "severity": item.severity,
                    "message": item.message,
                    "recommended_action": item.recommended_action,
                }
                for item in report.trend.diagnostics
            ],
        }

    return {
        "schema_version": report.schema_version,
        "calculation_version": report.calculation_version,
        "plant_id": str(report.plant_id),
        "bill_id": str(report.bill_id),
        "reference_month": report.reference_month,
        "status": report.status,
        "headline": report.headline,
        "metrics": [
            {
                "key": item.key,
                "label": item.label,
                "value": item.value,
                "unit": item.unit,
                "nature": item.nature,
                "source": item.source,
            }
            for item in report.metrics
        ],
        "quality": [
            {
                "key": item.key,
                "label": item.label,
                "value": item.value,
                "unit": item.unit,
                "nature": item.nature,
                "source": item.source,
            }
            for item in report.quality
        ],
        "diagnostics": [
            {
                "code": item.code,
                "severity": item.severity,
                "message": item.message,
                "recommended_action": item.recommended_action,
            }
            for item in report.diagnostics
        ],
        "priority_actions": list(report.priority_actions),
        "trend": trend,
    }


def _write_metric_row(
    writer: CsvRowWriter,
    *,
    section: str,
    metric: ReportMetric,
    reference_month: str,
) -> None:
    writer.writerow(
        [
            section,
            metric.key,
            metric.label,
            metric.value,
            metric.unit or "",
            metric.nature,
            metric.source,
            reference_month,
            "",
        ]
    )


def monthly_report_to_csv(report: MonthlyEnergyReport) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "section",
            "key",
            "label",
            "value",
            "unit",
            "nature",
            "source",
            "reference_month",
            "detail",
        ]
    )
    metadata = (
        ("schema_version", report.schema_version),
        ("calculation_version", report.calculation_version),
        ("plant_id", str(report.plant_id)),
        ("bill_id", str(report.bill_id)),
        ("status", report.status),
        ("headline", report.headline),
    )
    for key, value in metadata:
        writer.writerow(
            [
                "metadata",
                key,
                key,
                value,
                "",
                "METADATA",
                "MPLACAS_REPORT",
                report.reference_month,
                "",
            ]
        )
    for metric in report.metrics:
        _write_metric_row(
            writer,
            section="metric",
            metric=metric,
            reference_month=report.reference_month,
        )
    for quality_metric in report.quality:
        _write_metric_row(
            writer,
            section="quality",
            metric=quality_metric,
            reference_month=report.reference_month,
        )
    for diagnostic in report.diagnostics:
        writer.writerow(
            [
                "diagnostic",
                diagnostic.code,
                diagnostic.message,
                diagnostic.severity,
                "",
                "DETERMINISTIC_DIAGNOSTIC",
                ENGINE_SOURCE,
                report.reference_month,
                diagnostic.recommended_action,
            ]
        )
    for index, action in enumerate(report.priority_actions, start=1):
        writer.writerow(
            [
                "priority_action",
                f"action_{index}",
                "Ação prioritária",
                action,
                "",
                "DETERMINISTIC_RECOMMENDATION",
                ENGINE_SOURCE,
                report.reference_month,
                "",
            ]
        )
    if report.trend is not None:
        trend_reference = (
            f"{report.trend.previous_reference_month}->{report.trend.current_reference_month}"
        )
        for trend_metric in report.trend.metrics:
            percent_detail = (
                f"percent_delta={trend_metric.percent_delta};direction={trend_metric.direction}"
                if trend_metric.percent_delta is not None
                else f"direction={trend_metric.direction}"
            )
            writer.writerow(
                [
                    "trend",
                    trend_metric.key,
                    trend_metric.label,
                    trend_metric.absolute_delta,
                    trend_metric.unit,
                    "CALCULATED_DELTA",
                    ENGINE_SOURCE,
                    trend_reference,
                    percent_detail,
                ]
            )
        for trend_diagnostic in report.trend.diagnostics:
            writer.writerow(
                [
                    "trend_diagnostic",
                    trend_diagnostic.code,
                    trend_diagnostic.message,
                    trend_diagnostic.severity,
                    "",
                    "DETERMINISTIC_DIAGNOSTIC",
                    ENGINE_SOURCE,
                    trend_reference,
                    trend_diagnostic.recommended_action,
                ]
            )
    return "\ufeff" + output.getvalue()
