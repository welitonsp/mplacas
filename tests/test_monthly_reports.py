from __future__ import annotations

import csv
import io
import tomllib
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from mplacas import __version__
from mplacas.core.config import get_settings
from mplacas.main import app
from mplacas.reports.service import (
    MonthlyEnergyReport,
    MonthlyReportTrend,
    ReportDiagnostic,
    ReportMetric,
    ReportTrendMetric,
    build_latest_monthly_report,
    monthly_report_to_csv,
)
import mplacas.reports.router as reports_router
import mplacas.reports.service as reports_service


class FakeSession:
    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


def _dashboard(plant_id: uuid.UUID) -> SimpleNamespace:
    metric_trend = lambda absolute, percent, direction: SimpleNamespace(
        absolute_delta=Decimal(absolute),
        percent_delta=Decimal(percent) if percent is not None else None,
        direction=SimpleNamespace(value=direction),
    )
    return SimpleNamespace(
        plant_id=plant_id,
        status=SimpleNamespace(value="HEALTHY"),
        headline="Ciclo sintético dentro dos parâmetros avaliados.",
        priority_actions=("Manter o acompanhamento periódico.",),
        current_cycle=SimpleNamespace(
            bill_id=uuid.UUID("00000000-0000-0000-0000-000000000133"),
            reference_month="2026-06",
            quality=SimpleNamespace(
                missing_days=0,
                provisional_days=1,
                incomplete_days=0,
                unavailable_days=0,
            ),
            intelligence=SimpleNamespace(
                reconciliation=SimpleNamespace(
                    cycle_production_kwh=Decimal("100.000"),
                    imported_kwh=Decimal("20.000"),
                    injected_kwh=Decimal("40.000"),
                    estimated_self_consumption_kwh=Decimal("60.000"),
                    estimated_total_consumption_kwh=Decimal("80.000"),
                    self_consumption_rate_percent=Decimal("60.0"),
                    self_sufficiency_rate_percent=Decimal("75.0"),
                ),
                grid_dependency_rate_percent=Decimal("25.0"),
                exported_generation_rate_percent=Decimal("40.0"),
                credit_coverage_rate_percent=Decimal("80.0"),
                bill_energy_component_brl=Decimal("45.20"),
                health_score=97,
                diagnostics=(
                    SimpleNamespace(
                        code="PROVISIONAL_DAILY_DATA",
                        severity=SimpleNamespace(value="WARNING"),
                        message="O ciclo possui 1 dia provisório.",
                        recommended_action="Aguardar a consolidação D+1.",
                    ),
                ),
            ),
        ),
        trend=SimpleNamespace(
            comparison=SimpleNamespace(
                current_reference_month="2026-06",
                previous_reference_month="2026-05",
                production=metric_trend("10.000", "11.1", "UP"),
                total_consumption=metric_trend("2.000", "2.6", "UP"),
                imported_energy=metric_trend("-3.000", "-13.0", "DOWN"),
                self_sufficiency_delta_points=Decimal("5.0"),
                health_score_delta=3,
            ),
            diagnostics=(
                SimpleNamespace(
                    code="PRODUCTION_TREND_UP",
                    severity="INFO",
                    message="A produção aumentou.",
                    recommended_action="Manter o acompanhamento.",
                ),
            ),
        ),
    )


def _report(plant_id: uuid.UUID) -> MonthlyEnergyReport:
    return MonthlyEnergyReport(
        schema_version="1.0",
        calculation_version="0.2.0",
        plant_id=plant_id,
        bill_id=uuid.UUID("00000000-0000-0000-0000-000000000133"),
        reference_month="2026-06",
        status="HEALTHY",
        headline="Ciclo sintético dentro dos parâmetros avaliados.",
        metrics=(
            ReportMetric(
                key="cycle_production_kwh",
                label="Produção do ciclo",
                value="100.000",
                unit="kWh",
                nature="MEASURED_AGGREGATE",
                source="DAILY_ENERGY_AGGREGATE",
            ),
        ),
        quality=(
            ReportMetric(
                key="missing_days",
                label="Dias ausentes",
                value="0",
                unit="days",
                nature="QUALITY_COUNT",
                source="MPLACAS_DETERMINISTIC_ENGINE",
            ),
        ),
        diagnostics=(
            ReportDiagnostic(
                code="CYCLE_WITHIN_EXPECTED_PARAMETERS",
                severity="INFO",
                message="O ciclo está dentro dos parâmetros avaliados.",
                recommended_action="Manter o acompanhamento periódico.",
            ),
        ),
        priority_actions=("Manter o acompanhamento periódico.",),
        trend=MonthlyReportTrend(
            current_reference_month="2026-06",
            previous_reference_month="2026-05",
            metrics=(
                ReportTrendMetric(
                    key="production",
                    label="Produção",
                    absolute_delta="10.000",
                    unit="kWh",
                    percent_delta="11.1",
                    direction="UP",
                ),
            ),
            diagnostics=(),
        ),
    )


def test_package_version_matches_pyproject() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert __version__ == pyproject["project"]["version"] == "0.2.0"


@pytest.mark.asyncio
async def test_monthly_report_projects_the_existing_deterministic_dashboard(monkeypatch) -> None:
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000033")
    dashboard = _dashboard(plant_id)
    received: dict[str, object] = {}

    async def fake_dashboard(session, **kwargs):
        received.update(kwargs)
        return dashboard

    monkeypatch.setattr(reports_service, "build_executive_dashboard", fake_dashboard)
    report = await build_latest_monthly_report(
        object(),
        plant_id=plant_id,
        expected_production_kwh=Decimal("120"),
        stable_tolerance_percent=Decimal("3.0"),
    )

    assert received == {
        "plant_id": plant_id,
        "expected_production_kwh": Decimal("120"),
        "stable_tolerance_percent": Decimal("3.0"),
    }
    assert report.calculation_version == "0.2.0"
    assert report.reference_month == "2026-06"
    assert report.metrics[0].nature == "MEASURED_AGGREGATE"
    assert report.metrics[0].source == "DAILY_ENERGY_AGGREGATE"
    assert any(item.key == "health_score" for item in report.metrics)
    assert report.trend is not None
    assert report.trend.metrics[0].direction == "UP"

    exported = monthly_report_to_csv(report)
    assert exported.startswith("\ufeff")
    rows = list(csv.DictReader(io.StringIO(exported.removeprefix("\ufeff"))))
    assert any(row["key"] == "calculation_version" for row in rows)
    assert any(row["key"] == "cycle_production_kwh" for row in rows)
    assert any(row["section"] == "diagnostic" for row in rows)
    assert "password" not in exported.casefold()
    assert "token" not in exported.casefold()


def test_monthly_report_endpoints_are_protected_and_export_csv(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-key")
    get_settings.cache_clear()
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000033")
    report = _report(plant_id)

    async def fake_report(**kwargs):
        assert kwargs["plant_id"] == plant_id
        return report

    monkeypatch.setattr(reports_router, "_build_report", fake_report)
    monkeypatch.setattr(reports_router, "SessionFactory", lambda: FakeSession())
    client = TestClient(app)

    unauthorized = client.get(
        "/reports/monthly/latest",
        params={"plant_id": str(plant_id)},
    )
    assert unauthorized.status_code == 401

    response = client.get(
        "/reports/monthly/latest",
        headers={"X-API-Key": "synthetic-key"},
        params={"plant_id": str(plant_id)},
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["calculation_version"] == "0.2.0"
    assert payload["metrics"][0]["source"] == "DAILY_ENERGY_AGGREGATE"

    csv_response = client.get(
        "/reports/monthly/latest.csv",
        headers={"X-API-Key": "synthetic-key"},
        params={"plant_id": str(plant_id)},
    )
    assert csv_response.status_code == 200
    assert csv_response.headers["cache-control"] == "no-store"
    assert csv_response.headers["x-content-type-options"] == "nosniff"
    assert "mplacas-monthly-2026-06" in csv_response.headers["content-disposition"]
    assert csv_response.content.startswith(b"\xef\xbb\xbf")
    assert "cycle_production_kwh" in csv_response.text
    get_settings.cache_clear()
