"""Layout do PDF mensal (2026-10): formatação de leitura sem recalcular nada.

Os cartões mostram o valor do snapshot em formato brasileiro; o anexo de
auditoria mantém o valor exato gravado. Economia indisponível nunca vira
número estimado.
"""

from __future__ import annotations

import io
import uuid

from pypdf import PdfReader

from mplacas.reports.contract import MonthlyEnergyReport, ReportMetric
from mplacas.reports.export.pdf_renderer import _format_value, _month_label
from mplacas.reports.exporters import build_monthly_report_pdf

ENGINE = "MPLACAS_DETERMINISTIC_ENGINE"


def _metric(key: str, value: str, unit: str | None, nature: str = "CALCULATED") -> ReportMetric:
    return ReportMetric(
        key=key, label=key, value=value, unit=unit, nature=nature, source=ENGINE
    )


def _report(*, savings: str, reason: str, quality_provisional: str = "0") -> MonthlyEnergyReport:
    return MonthlyEnergyReport(
        schema_version="1.0",
        calculation_version="test",
        plant_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        bill_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        reference_month="2026-09",
        status="HEALTHY",
        headline="Ciclo de teste.",
        metrics=(
            _metric("cycle_production_kwh", "14625.4", "kWh", "MEASURED_AGGREGATE"),
            _metric("estimated_total_consumption_kwh", "445.66", "kWh"),
            _metric("estimated_self_consumption_kwh", "207.26", "kWh"),
            _metric("injected_kwh", "402.90", "kWh", "MEASURED"),
            _metric("imported_kwh", "238.40", "kWh", "MEASURED"),
            _metric("estimated_savings_brl", savings, "BRL"),
            _metric("savings_unavailable_reason", reason, None, "UNAVAILABILITY_REASON"),
        ),
        quality=(
            _metric("missing_days", "0", "days", "QUALITY_COUNT"),
            _metric("provisional_days", quality_provisional, "days", "QUALITY_COUNT"),
        ),
        diagnostics=(),
        priority_actions=(),
        trend=None,
    )


def _text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_cards_use_brazilian_format_and_annex_keeps_exact_value() -> None:
    text = _text(build_monthly_report_pdf(_report(savings="412.37", reason="")))

    assert "14.625,40 kWh" in text  # cartão: leitura em pt-BR
    assert "14625.4 kWh" in text  # anexo: valor exato gravado, sem arredondar
    assert "R$ 412,37" in text
    assert "Setembro/2026" in text
    assert "2026-09" in text


def test_unavailable_savings_shows_reason_and_never_a_number() -> None:
    text = _text(
        build_monthly_report_pdf(_report(savings="", reason="TARIFF_NOT_AVAILABLE"))
    )

    assert "Indisponível" in text
    assert "tarifa da concessionária não está cadastrada" in text
    assert "R$" not in text


def test_unknown_unavailability_code_is_shown_verbatim() -> None:
    text = _text(build_monthly_report_pdf(_report(savings="", reason="NEW_REASON_CODE")))

    assert "NEW_REASON_CODE" in text


def test_snapshot_without_new_metrics_still_renders() -> None:
    report = _report(savings="412.37", reason="")
    legacy = MonthlyEnergyReport(
        **{
            **{field: getattr(report, field) for field in report.__dataclass_fields__},
            "metrics": (_metric("production_kwh", "610.00", "kWh"),),
            "quality": (),
        }
    )

    pdf_bytes = build_monthly_report_pdf(legacy)

    assert pdf_bytes.startswith(b"%PDF-")
    assert "não recalcula indicadores" in _text(pdf_bytes)


def test_format_value_is_presentation_only() -> None:
    assert _format_value("", "kWh") is None
    assert _format_value("1452.8", "BRL") == "R$ 1.452,80"
    assert _format_value("33.97", "%") == "33,97%"
    assert _format_value("1", "days") == "1 dia"
    assert _format_value("2", "days") == "2 dias"
    assert _format_value("92", "score_0_100") == "92/100"
    assert _format_value("not-a-number", "kWh") == "not-a-number"


def test_month_label_falls_back_to_raw_value() -> None:
    assert _month_label("2026-06") == "Junho/2026"
    assert _month_label("2026-13") == "2026-13"
    assert _month_label("ciclo-x") == "ciclo-x"
