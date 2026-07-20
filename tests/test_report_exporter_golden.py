"""Golden tests for report exporters — verify content contract is preserved after refactoring."""
from __future__ import annotations

import uuid
import zipfile
import io

from mplacas.reports.contract import MonthlyEnergyReport, ReportMetric, ReportDiagnostic
from mplacas.reports.exporters import (
    PDF_MEDIA_TYPE,
    XLSX_MEDIA_TYPE,
    build_monthly_report_pdf,
    build_monthly_report_xlsx,
)
from mplacas.reports.export.theme import severity_token


def _make_report(*, with_diagnostics: bool = False, with_trend: bool = False) -> MonthlyEnergyReport:
    metrics = (
        ReportMetric(
            key="production_kwh",
            label="Produção total",
            value="610.00",
            unit="kWh",
            nature="medido",
            source="NEPViewer",
        ),
    )
    diagnostics = (
        ReportDiagnostic(
            code="D001",
            severity="WARNING",
            message="Produção abaixo do esperado",
            recommended_action="Verificar painéis",
        ),
    ) if with_diagnostics else ()
    return MonthlyEnergyReport(
        schema_version="1.0",
        calculation_version="test-1",
        plant_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        bill_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        reference_month="2026-06",
        status="healthy",
        headline="Operação normal.",
        metrics=metrics,
        quality=metrics,
        diagnostics=diagnostics,
        priority_actions=("Manter monitoramento.",),
        trend=None,
    )


# ---------------------------------------------------------------------------
# Theme tests
# ---------------------------------------------------------------------------

def test_severity_token_critical() -> None:
    assert severity_token("CRITICAL") == "critical"
    assert severity_token("ERROR") == "critical"


def test_severity_token_warning() -> None:
    assert severity_token("WARNING") == "warning"
    assert severity_token("WARN") == "warning"


def test_severity_token_healthy() -> None:
    assert severity_token("HEALTHY") == "healthy"
    assert severity_token("SUCCESS") == "healthy"


def test_severity_token_info_fallback() -> None:
    assert severity_token("INFO") == "info"
    assert severity_token("unknown") == "info"


# ---------------------------------------------------------------------------
# PDF golden tests
# ---------------------------------------------------------------------------

def test_pdf_output_is_valid_pdf() -> None:
    report = _make_report()
    pdf_bytes = build_monthly_report_pdf(report)
    assert pdf_bytes[:4] == b"%PDF"


def test_pdf_media_type_constant() -> None:
    assert PDF_MEDIA_TYPE == "application/pdf"


def test_pdf_contains_reference_month() -> None:
    report = _make_report()
    pdf_bytes = build_monthly_report_pdf(report)
    assert b"2026-06" in pdf_bytes or b"2026" in pdf_bytes


def test_pdf_with_diagnostics_renders() -> None:
    report = _make_report(with_diagnostics=True)
    pdf_bytes = build_monthly_report_pdf(report)
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 1000


# ---------------------------------------------------------------------------
# XLSX golden tests
# ---------------------------------------------------------------------------

def test_xlsx_output_is_valid_zip() -> None:
    report = _make_report()
    xlsx_bytes = build_monthly_report_xlsx(report)
    assert zipfile.is_zipfile(io.BytesIO(xlsx_bytes))


def test_xlsx_media_type_constant() -> None:
    assert XLSX_MEDIA_TYPE == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_xlsx_contains_expected_sheet_names() -> None:
    report = _make_report()
    xlsx_bytes = build_monthly_report_xlsx(report)
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as zf:
        names = zf.namelist()
    assert any("sheet" in n.lower() for n in names)


def test_xlsx_with_diagnostics_renders() -> None:
    report = _make_report(with_diagnostics=True)
    xlsx_bytes = build_monthly_report_xlsx(report)
    assert zipfile.is_zipfile(io.BytesIO(xlsx_bytes))
    assert len(xlsx_bytes) > 1000


# ---------------------------------------------------------------------------
# Facade re-export contract
# ---------------------------------------------------------------------------

def test_exporters_facade_re_exports_pdf() -> None:
    from mplacas.reports import exporters
    assert hasattr(exporters, "build_monthly_report_pdf")
    assert hasattr(exporters, "PDF_MEDIA_TYPE")


def test_exporters_facade_re_exports_xlsx() -> None:
    from mplacas.reports import exporters
    assert hasattr(exporters, "build_monthly_report_xlsx")
    assert hasattr(exporters, "XLSX_MEDIA_TYPE")
