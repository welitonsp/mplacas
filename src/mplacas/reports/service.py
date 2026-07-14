from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas import __version__
from mplacas.intelligence.executive_service import build_executive_dashboard

REPORT_SCHEMA_VERSION = "1.0"
_ENGINE_SOURCE = "MPLACAS_DETERMINISTIC_ENGINE"
_BILL_SOURCE = "UTILITY_BILL_CONFIRMED"
_DAILY_SOURCE = "DAILY_ENERGY_AGGREGATE"


@dataclass(frozen=True, slots=True)
class ReportMetric:
    key: str
    label: str
    value: str
    unit: str | None
    nature: str
    source: str


@dataclass(frozen=True, slots=True)
class ReportDiagnostic:
    code: str
    severity: str
    message: str
    recommended_action: str


@dataclass(frozen=True, slots=True)
class ReportTrendMetric:
    key: str
    label: str
    absolute_delta: str
    unit: str
    percent_delta: str | None
    direction: str


@dataclass(frozen=True, slots=True)
class MonthlyReportTrend:
    current_reference_month: str
    previous_reference_month: str
    metrics: tuple[ReportTrendMetric, ...]
    diagnostics: tuple[ReportDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class MonthlyEnergyReport:
    schema_version: str
    calculation_version: str
    plant_id: uuid.UUID
    bill_id: uuid.UUID
    reference_month: str
    status: str
    headline: str
    metrics: tuple[ReportMetric, ...]
    quality: tuple[ReportMetric, ...]
    diagnostics: tuple[ReportDiagnostic, ...]
    priority_actions: tuple[str, ...]
    trend: MonthlyReportTrend | None


def _metric(
    key: str,
    label: str,
    value: Decimal | int,
    *,
    unit: str | None,
    nature: str,
    source: str,
) -> ReportMetric:
    return ReportMetric(
        key=key,
        label=label,
        value=str(value),
        unit=unit,
        nature=nature,
        source=source,
    )


def _trend_metric(
    key: str,
    label: str,
    trend,
    *,
    unit: str,
) -> ReportTrendMetric:
    return ReportTrendMetric(
        key=key,
        label=label,
        absolute_delta=str(trend.absolute_delta),
        unit=unit,
        percent_delta=str(trend.percent_delta) if trend.percent_delta is not None else None,
        direction=trend.direction.value,
    )


async def build_latest_monthly_report(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    expected_production_kwh: Decimal | None = None,
    stable_tolerance_percent: Decimal = Decimal("2.0"),
) -> MonthlyEnergyReport:
    dashboard = await build_executive_dashboard(
        session,
        plant_id=plant_id,
        expected_production_kwh=expected_production_kwh,
        stable_tolerance_percent=stable_tolerance_percent,
    )
    current = dashboard.current_cycle
    intelligence = current.intelligence
    reconciliation = intelligence.reconciliation

    metrics = (
        _metric(
            "cycle_production_kwh",
            "Produção do ciclo",
            reconciliation.cycle_production_kwh,
            unit="kWh",
            nature="MEASURED_AGGREGATE",
            source=_DAILY_SOURCE,
        ),
        _metric(
            "imported_kwh",
            "Energia importada da rede",
            reconciliation.imported_kwh,
            unit="kWh",
            nature="MEASURED",
            source=_BILL_SOURCE,
        ),
        _metric(
            "injected_kwh",
            "Energia injetada na rede",
            reconciliation.injected_kwh,
            unit="kWh",
            nature="MEASURED",
            source=_BILL_SOURCE,
        ),
        _metric(
            "estimated_self_consumption_kwh",
            "Autoconsumo estimado",
            reconciliation.estimated_self_consumption_kwh,
            unit="kWh",
            nature="CALCULATED",
            source=_ENGINE_SOURCE,
        ),
        _metric(
            "estimated_total_consumption_kwh",
            "Consumo total estimado",
            reconciliation.estimated_total_consumption_kwh,
            unit="kWh",
            nature="CALCULATED",
            source=_ENGINE_SOURCE,
        ),
        _metric(
            "self_consumption_rate_percent",
            "Taxa de autoconsumo",
            reconciliation.self_consumption_rate_percent,
            unit="%",
            nature="CALCULATED",
            source=_ENGINE_SOURCE,
        ),
        _metric(
            "self_sufficiency_rate_percent",
            "Taxa de autossuficiência",
            reconciliation.self_sufficiency_rate_percent,
            unit="%",
            nature="CALCULATED",
            source=_ENGINE_SOURCE,
        ),
        _metric(
            "grid_dependency_rate_percent",
            "Dependência da rede",
            intelligence.grid_dependency_rate_percent,
            unit="%",
            nature="CALCULATED",
            source=_ENGINE_SOURCE,
        ),
        _metric(
            "exported_generation_rate_percent",
            "Parcela da geração exportada",
            intelligence.exported_generation_rate_percent,
            unit="%",
            nature="CALCULATED",
            source=_ENGINE_SOURCE,
        ),
        _metric(
            "credit_coverage_rate_percent",
            "Cobertura da importação por créditos",
            intelligence.credit_coverage_rate_percent,
            unit="%",
            nature="CALCULATED",
            source=_ENGINE_SOURCE,
        ),
        _metric(
            "bill_energy_component_brl",
            "Componente energético da fatura",
            intelligence.bill_energy_component_brl,
            unit="BRL",
            nature="CALCULATED",
            source=_ENGINE_SOURCE,
        ),
        _metric(
            "health_score",
            "Índice de saúde",
            intelligence.health_score,
            unit="score_0_100",
            nature="CALCULATED_SCORE",
            source=_ENGINE_SOURCE,
        ),
    )
    quality = (
        _metric(
            "missing_days",
            "Dias ausentes",
            current.quality.missing_days,
            unit="days",
            nature="QUALITY_COUNT",
            source=_ENGINE_SOURCE,
        ),
        _metric(
            "provisional_days",
            "Dias provisórios",
            current.quality.provisional_days,
            unit="days",
            nature="QUALITY_COUNT",
            source=_ENGINE_SOURCE,
        ),
        _metric(
            "incomplete_days",
            "Dias incompletos",
            current.quality.incomplete_days,
            unit="days",
            nature="QUALITY_COUNT",
            source=_ENGINE_SOURCE,
        ),
        _metric(
            "unavailable_days",
            "Dias indisponíveis",
            current.quality.unavailable_days,
            unit="days",
            nature="QUALITY_COUNT",
            source=_ENGINE_SOURCE,
        ),
    )
    diagnostics = tuple(
        ReportDiagnostic(
            code=item.code,
            severity=item.severity.value,
            message=item.message,
            recommended_action=item.recommended_action,
        )
        for item in intelligence.diagnostics
    )

    trend: MonthlyReportTrend | None = None
    if dashboard.trend is not None:
        comparison = dashboard.trend.comparison
        trend = MonthlyReportTrend(
            current_reference_month=comparison.current_reference_month,
            previous_reference_month=comparison.previous_reference_month,
            metrics=(
                _trend_metric(
                    "production",
                    "Produção",
                    comparison.production,
                    unit="kWh",
                ),
                _trend_metric(
                    "total_consumption",
                    "Consumo total estimado",
                    comparison.total_consumption,
                    unit="kWh",
                ),
                _trend_metric(
                    "imported_energy",
                    "Energia importada",
                    comparison.imported_energy,
                    unit="kWh",
                ),
                ReportTrendMetric(
                    key="self_sufficiency",
                    label="Autossuficiência",
                    absolute_delta=str(comparison.self_sufficiency_delta_points),
                    unit="percentage_points",
                    percent_delta=None,
                    direction="DELTA",
                ),
                ReportTrendMetric(
                    key="health_score",
                    label="Índice de saúde",
                    absolute_delta=str(comparison.health_score_delta),
                    unit="score_points",
                    percent_delta=None,
                    direction="DELTA",
                ),
            ),
            diagnostics=tuple(
                ReportDiagnostic(
                    code=item.code,
                    severity=item.severity,
                    message=item.message,
                    recommended_action=item.recommended_action,
                )
                for item in dashboard.trend.diagnostics
            ),
        )

    return MonthlyEnergyReport(
        schema_version=REPORT_SCHEMA_VERSION,
        calculation_version=__version__,
        plant_id=dashboard.plant_id,
        bill_id=current.bill_id,
        reference_month=current.reference_month,
        status=dashboard.status.value,
        headline=dashboard.headline,
        metrics=metrics,
        quality=quality,
        diagnostics=diagnostics,
        priority_actions=dashboard.priority_actions,
        trend=trend,
    )


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
    writer: object,
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
                _ENGINE_SOURCE,
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
                _ENGINE_SOURCE,
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
                    _ENGINE_SOURCE,
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
                    _ENGINE_SOURCE,
                    trend_reference,
                    trend_diagnostic.recommended_action,
                ]
            )
    return "\ufeff" + output.getvalue()
