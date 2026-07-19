from __future__ import annotations

from decimal import Decimal

from mplacas import __version__
from mplacas.intelligence.executive_service import ExecutiveEnergyDashboard
from mplacas.intelligence.trends import MetricTrend
from mplacas.reports.contract import (
    REPORT_SCHEMA_VERSION,
    MonthlyEnergyReport,
    MonthlyReportTrend,
    ReportDiagnostic,
    ReportMetric,
    ReportTrendMetric,
)

ENGINE_SOURCE = "MPLACAS_DETERMINISTIC_ENGINE"
BILL_SOURCE = "UTILITY_BILL_CONFIRMED"
DAILY_SOURCE = "DAILY_ENERGY_AGGREGATE"


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
    trend: MetricTrend,
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


def _project_metrics(dashboard: ExecutiveEnergyDashboard) -> tuple[ReportMetric, ...]:
    intelligence = dashboard.current_cycle.intelligence
    reconciliation = intelligence.reconciliation
    return (
        _metric(
            "cycle_production_kwh",
            "Produção do ciclo",
            reconciliation.cycle_production_kwh,
            unit="kWh",
            nature="MEASURED_AGGREGATE",
            source=DAILY_SOURCE,
        ),
        _metric(
            "imported_kwh",
            "Energia importada da rede",
            reconciliation.imported_kwh,
            unit="kWh",
            nature="MEASURED",
            source=BILL_SOURCE,
        ),
        _metric(
            "injected_kwh",
            "Energia injetada na rede",
            reconciliation.injected_kwh,
            unit="kWh",
            nature="MEASURED",
            source=BILL_SOURCE,
        ),
        _metric(
            "estimated_self_consumption_kwh",
            "Autoconsumo estimado",
            reconciliation.estimated_self_consumption_kwh,
            unit="kWh",
            nature="CALCULATED",
            source=ENGINE_SOURCE,
        ),
        _metric(
            "estimated_total_consumption_kwh",
            "Consumo total estimado",
            reconciliation.estimated_total_consumption_kwh,
            unit="kWh",
            nature="CALCULATED",
            source=ENGINE_SOURCE,
        ),
        _metric(
            "self_consumption_rate_percent",
            "Taxa de autoconsumo",
            reconciliation.self_consumption_rate_percent,
            unit="%",
            nature="CALCULATED",
            source=ENGINE_SOURCE,
        ),
        _metric(
            "self_sufficiency_rate_percent",
            "Taxa de autossuficiência",
            reconciliation.self_sufficiency_rate_percent,
            unit="%",
            nature="CALCULATED",
            source=ENGINE_SOURCE,
        ),
        _metric(
            "grid_dependency_rate_percent",
            "Dependência da rede",
            intelligence.grid_dependency_rate_percent,
            unit="%",
            nature="CALCULATED",
            source=ENGINE_SOURCE,
        ),
        _metric(
            "exported_generation_rate_percent",
            "Parcela da geração exportada",
            intelligence.exported_generation_rate_percent,
            unit="%",
            nature="CALCULATED",
            source=ENGINE_SOURCE,
        ),
        _metric(
            "credit_coverage_rate_percent",
            "Cobertura da importação por créditos",
            intelligence.credit_coverage_rate_percent,
            unit="%",
            nature="CALCULATED",
            source=ENGINE_SOURCE,
        ),
        _metric(
            "bill_energy_component_brl",
            "Componente energético da fatura",
            intelligence.bill_energy_component_brl,
            unit="BRL",
            nature="CALCULATED",
            source=ENGINE_SOURCE,
        ),
        _metric(
            "health_score",
            "Índice de saúde",
            intelligence.health_score,
            unit="score_0_100",
            nature="CALCULATED_SCORE",
            source=ENGINE_SOURCE,
        ),
    )


def _project_quality(dashboard: ExecutiveEnergyDashboard) -> tuple[ReportMetric, ...]:
    quality = dashboard.current_cycle.quality
    return (
        _metric(
            "missing_days",
            "Dias ausentes",
            quality.missing_days,
            unit="days",
            nature="QUALITY_COUNT",
            source=ENGINE_SOURCE,
        ),
        _metric(
            "provisional_days",
            "Dias provisórios",
            quality.provisional_days,
            unit="days",
            nature="QUALITY_COUNT",
            source=ENGINE_SOURCE,
        ),
        _metric(
            "incomplete_days",
            "Dias incompletos",
            quality.incomplete_days,
            unit="days",
            nature="QUALITY_COUNT",
            source=ENGINE_SOURCE,
        ),
        _metric(
            "unavailable_days",
            "Dias indisponíveis",
            quality.unavailable_days,
            unit="days",
            nature="QUALITY_COUNT",
            source=ENGINE_SOURCE,
        ),
    )


def _project_diagnostics(
    dashboard: ExecutiveEnergyDashboard,
) -> tuple[ReportDiagnostic, ...]:
    return tuple(
        ReportDiagnostic(
            code=item.code,
            severity=item.severity.value,
            message=item.message,
            recommended_action=item.recommended_action,
        )
        for item in dashboard.current_cycle.intelligence.diagnostics
    )


def _project_trend(dashboard: ExecutiveEnergyDashboard) -> MonthlyReportTrend | None:
    if dashboard.trend is None:
        return None
    comparison = dashboard.trend.comparison
    return MonthlyReportTrend(
        current_reference_month=comparison.current_reference_month,
        previous_reference_month=comparison.previous_reference_month,
        metrics=(
            _trend_metric("production", "Produção", comparison.production, unit="kWh"),
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


def project_executive_dashboard(
    dashboard: ExecutiveEnergyDashboard,
) -> MonthlyEnergyReport:
    current = dashboard.current_cycle
    return MonthlyEnergyReport(
        schema_version=REPORT_SCHEMA_VERSION,
        calculation_version=__version__,
        plant_id=dashboard.plant_id,
        bill_id=current.bill_id,
        reference_month=current.reference_month,
        status=dashboard.status.value,
        headline=dashboard.headline,
        metrics=_project_metrics(dashboard),
        quality=_project_quality(dashboard),
        diagnostics=_project_diagnostics(dashboard),
        priority_actions=dashboard.priority_actions,
        trend=_project_trend(dashboard),
    )
