"""Layout do PDF mensal (2026-10): formatação de leitura sem recalcular nada.

Os cartões mostram o valor do snapshot em formato brasileiro; o anexo de
auditoria mantém o valor exato gravado. Economia indisponível nunca vira
número estimado.
"""

from __future__ import annotations

import io
import uuid

from pypdf import PdfReader

from mplacas.reports.contract import (
    MonthlyEnergyReport,
    MonthlyReportTrend,
    ReportDiagnostic,
    ReportMetric,
    ReportTrendMetric,
)
from mplacas.reports.export.pdf_renderer import _format_value, _month_label
from mplacas.reports.exporters import build_monthly_report_pdf

ENGINE = "MPLACAS_DETERMINISTIC_ENGINE"


def _metric(key: str, value: str, unit: str | None, nature: str = "CALCULATED") -> ReportMetric:
    return ReportMetric(key=key, label=key, value=value, unit=unit, nature=nature, source=ENGINE)


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

    assert "14.625,4 kWh" in text  # cartão: pt-BR, sem inventar casa decimal
    assert "14625.4 kWh" in text  # anexo: valor exato gravado, sem arredondar
    assert "R$ 412,37" in text
    assert "Setembro/2026" in text
    assert "2026-09" in text


def test_unavailable_savings_shows_reason_and_never_a_number() -> None:
    text = _text(build_monthly_report_pdf(_report(savings="", reason="TARIFF_NOT_AVAILABLE")))

    assert "Indisponível" in text
    assert "não registra a tarifa com impostos" in text
    assert "R$" not in text


def test_unknown_unavailability_code_is_shown_verbatim() -> None:
    text = _text(build_monthly_report_pdf(_report(savings="", reason="NEW_REASON_CODE")))

    assert "NEW_REASON_CODE" in text


def _with(report: MonthlyEnergyReport, **changes: object) -> MonthlyEnergyReport:
    fields = {field: getattr(report, field) for field in report.__dataclass_fields__}
    fields.update(changes)
    return MonthlyEnergyReport(**fields)  # type: ignore[arg-type]


def test_snapshot_without_metrics_renders_placeholders_instead_of_failing() -> None:
    empty = _with(_report(savings="412.37", reason=""), metrics=(), quality=())

    text = _text(build_monthly_report_pdf(empty))

    assert "—" in text  # cartões sem valor mostram travessão, não zero
    assert "kWh" not in text


def test_split_bars_never_print_derived_percentages() -> None:
    # Nenhuma métrica em % no snapshot: qualquer "%" no PDF seria um derivado.
    text = _text(build_monthly_report_pdf(_report(savings="412.37", reason="")))

    assert "Destino da produção" in text
    assert "Injetada na rede" in text
    assert "Importada da rede" in text
    assert "%" not in text


def test_production_split_is_omitted_when_injection_exceeds_production() -> None:
    base = _report(savings="412.37", reason="")
    mismatched = _with(
        base,
        metrics=tuple(
            _metric("injected_kwh", "20000", "kWh", "MEASURED") if m.key == "injected_kwh" else m
            for m in base.metrics
        ),
    )

    text = _text(build_monthly_report_pdf(mismatched))

    assert "não desenhado" in text
    assert "Consumida na própria casa" not in text
    assert "De onde veio o consumo" in text  # a outra barra continua coerente


def test_snapshot_text_is_escaped_and_hostile_values_do_not_break_export() -> None:
    report = _with(
        _report(savings="1e400", reason=""),
        headline="<b>sem negrito</b> & " + "x" * 5000,
        diagnostics=(
            ReportDiagnostic(
                code="WEIRD",
                severity="SOMETHING_NEW",
                message="m" * 6000,
                recommended_action="<font color='red'>a</font>",
            ),
        ),
        trend=MonthlyReportTrend(
            current_reference_month="2026-09",
            previous_reference_month="2026-08",
            metrics=(
                ReportTrendMetric("production", "Produção", "NaN", "kWh", None, "SIDEWAYS"),
                ReportTrendMetric("x", "Outro", "1E+999999", "kWh", "0.004", "UP"),
            ),
            diagnostics=(),
        ),
    )

    text = _text(build_monthly_report_pdf(report))

    assert "<b>sem negrito</b> &" in text
    assert "<font color='red'>a</font>" in text
    assert "1e400" in text  # grande demais para formatar: volta como gravado
    assert "1E+999999 kWh" in text


def test_format_value_is_presentation_only() -> None:
    assert _format_value("33.9", "%") == "33,9%"  # não inventa a segunda casa
    assert _format_value("-12.3", "BRL") == "-R$ 12,30"
    assert _format_value("-0.001", "kWh") == "0,00 kWh"  # nunca "-0,00"
    assert _format_value("1e400", "kWh") == "1e400"
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


def _cycle(month: str, production: str, provisional: str | None = "0") -> MonthlyEnergyReport:
    base = _report(savings="412.37", reason="")
    quality = (
        ()
        if provisional is None
        else (
            _metric("missing_days", "0", "days", "QUALITY_COUNT"),
            _metric("provisional_days", provisional, "days", "QUALITY_COUNT"),
            _metric("incomplete_days", "0", "days", "QUALITY_COUNT"),
            _metric("unavailable_days", "0", "days", "QUALITY_COUNT"),
        )
    )
    return _with(
        base,
        reference_month=month,
        metrics=(_metric("cycle_production_kwh", production, "kWh", "MEASURED_AGGREGATE"),),
        quality=quality,
    )


def test_history_section_is_absent_without_history() -> None:
    text = _text(build_monthly_report_pdf(_report(savings="412.37", reason="")))

    assert "HISTÓRICO" not in text


def test_history_lists_cycles_newest_first_with_quality_labels() -> None:
    current = _cycle("2026-09", "610.16")
    history = (
        _cycle("2026-07", "576.64", provisional="2"),
        _cycle("2026-08", "", provisional=None),
        _cycle("2026-06", "516.84"),
    )

    text = _text(build_monthly_report_pdf(current, history=history))
    section = text[text.index("HISTÓRICO DOS ÚLTIMOS CICLOS") :]

    order = [
        section.index(month)
        for month in ("Setembro/2026", "Agosto/2026", "Julho/2026", "Junho/2026")
    ]
    assert order == sorted(order)
    assert "Com ressalvas" in section  # julho: 2 dias provisórios
    assert "Sem registro" in section  # agosto: sem contagens de qualidade
    assert "Completa" in section
    assert "576,64 kWh" in section
    assert "—" in section  # agosto sem produção gravada: nunca vira zero


def test_history_keeps_one_row_per_month_and_at_most_twelve() -> None:
    current = _cycle("2026-12", "100")
    history = tuple(_cycle(f"2025-{month:02d}", "50") for month in range(1, 13)) + (
        _cycle("2026-12", "999"),  # mesmo mês do relatório atual: o atual vence
    )

    text = _text(build_monthly_report_pdf(current, history=history))
    section = text[text.index("HISTÓRICO DOS ÚLTIMOS CICLOS") :]

    assert section.count("Dezembro/2026") == 1
    assert "999" not in section
    assert "Janeiro/2025" not in section  # 13º ciclo mais antigo fica de fora
    assert "Fevereiro/2025" in section
