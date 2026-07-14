from __future__ import annotations

import io
import uuid
import zipfile
from decimal import Decimal

from fastapi.testclient import TestClient
from pypdf import PdfReader

import mplacas.reports.router as reports_router
from mplacas.core.config import get_settings
from mplacas.main import app
from mplacas.reports.exporters import (
    PDF_MEDIA_TYPE,
    XLSX_MEDIA_TYPE,
    build_monthly_report_pdf,
    build_monthly_report_xlsx,
)
from mplacas.reports.service import (
    MonthlyEnergyReport,
    MonthlyReportTrend,
    ReportDiagnostic,
    ReportMetric,
    ReportTrendMetric,
)


def _sample_report() -> MonthlyEnergyReport:
    return MonthlyEnergyReport(
        schema_version="1.0",
        calculation_version="0.2.0",
        plant_id=uuid.UUID("00000000-0000-0000-0000-000000000034"),
        bill_id=uuid.UUID("00000000-0000-0000-0000-000000000134"),
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
            ReportMetric(
                key="self_sufficiency_rate_percent",
                label="Taxa de autossuficiência",
                value="75.0",
                unit="%",
                nature="CALCULATED",
                source="MPLACAS_DETERMINISTIC_ENGINE",
            ),
            ReportMetric(
                key="health_score",
                label="Índice de saúde",
                value="97",
                unit="score_0_100",
                nature="CALCULATED_SCORE",
                source="MPLACAS_DETERMINISTIC_ENGINE",
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
            ReportMetric(
                key="provisional_days",
                label="Dias provisórios",
                value="1",
                unit="days",
                nature="QUALITY_COUNT",
                source="MPLACAS_DETERMINISTIC_ENGINE",
            ),
        ),
        diagnostics=(
            ReportDiagnostic(
                code="PROVISIONAL_DAILY_DATA",
                severity="WARNING",
                message="O ciclo possui 1 dia provisório.",
                recommended_action="Aguardar a consolidação D+1.",
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
            diagnostics=(
                ReportDiagnostic(
                    code="PRODUCTION_TREND_UP",
                    severity="INFO",
                    message="A produção aumentou.",
                    recommended_action="Manter o acompanhamento.",
                ),
            ),
        ),
    )


def test_pdf_export_is_readable_auditable_and_contains_no_sensitive_fields() -> None:
    pdf_bytes = build_monthly_report_pdf(_sample_report())

    assert pdf_bytes.startswith(b"%PDF-")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 2
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    normalized = text.casefold()

    assert "mplacas" in normalized
    assert "2026-06" in text
    assert "produção do ciclo" in normalized
    assert "versão do cálculo" in normalized
    assert "não recalcula indicadores" in normalized
    assert "password" not in normalized
    assert "token" not in normalized
    assert reader.metadata is not None
    assert reader.metadata.title == "Mplacas - Relatório mensal 2026-06"
    assert reader.metadata.author == "Mplacas"


def test_xlsx_export_has_expected_sheets_metadata_and_no_formulas() -> None:
    xlsx_bytes = build_monthly_report_xlsx(_sample_report())

    assert xlsx_bytes.startswith(b"PK")
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as archive:
        names = set(archive.namelist())
        assert {
            "[Content_Types].xml",
            "xl/workbook.xml",
            "xl/styles.xml",
            "xl/sharedStrings.xml",
            "docProps/core.xml",
        }.issubset(names)

        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        for sheet_name in (
            "Resumo",
            "Indicadores",
            "Qualidade",
            "Diagnosticos",
            "Tendencias",
            "Metadados",
        ):
            assert f'name="{sheet_name}"' in workbook_xml

        shared_strings = archive.read("xl/sharedStrings.xml").decode("utf-8")
        assert "Mplacas - Relatório Mensal de Energia" in shared_strings
        assert "Produção do ciclo" in shared_strings
        assert "NO_RECALCULATION" in shared_strings
        assert "MPLACAS_MONTHLY_ENERGY_REPORT" in shared_strings
        assert "password" not in shared_strings.casefold()
        assert "token" not in shared_strings.casefold()

        worksheet_xml = "".join(
            archive.read(name).decode("utf-8")
            for name in sorted(names)
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
        )
        assert "<f>" not in worksheet_xml
        assert "<f " not in worksheet_xml


def test_pdf_and_xlsx_endpoints_are_protected_downloads(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-key")
    get_settings.cache_clear()
    report = _sample_report()

    async def fake_report(**kwargs):
        assert kwargs["plant_id"] == report.plant_id
        assert kwargs["expected_production_kwh"] == Decimal("120")
        return report

    monkeypatch.setattr(reports_router, "_build_report", fake_report)
    client = TestClient(app)
    params = {
        "plant_id": str(report.plant_id),
        "expected_production_kwh": "120",
    }

    for suffix, media_type, signature in (
        ("pdf", PDF_MEDIA_TYPE, b"%PDF-"),
        ("xlsx", XLSX_MEDIA_TYPE, b"PK"),
    ):
        unauthorized = client.get(f"/reports/monthly/latest.{suffix}", params=params)
        assert unauthorized.status_code == 401

        response = client.get(
            f"/reports/monthly/latest.{suffix}",
            headers={"X-API-Key": "synthetic-key"},
            params=params,
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(media_type)
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["pragma"] == "no-cache"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert f"mplacas-monthly-2026-06-{report.plant_id}.{suffix}" in response.headers[
            "content-disposition"
        ]
        assert response.content.startswith(signature)

    get_settings.cache_clear()
