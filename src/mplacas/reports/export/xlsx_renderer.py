from __future__ import annotations

import io
from typing import Any, Final

import xlsxwriter

from mplacas.reports.contract import MonthlyEnergyReport, ReportMetric
from mplacas.reports.export import theme

XLSX_MEDIA_TYPE: Final = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _formats(workbook: Any) -> dict[str, Any]:
    return {
        "title": workbook.add_format(
            {
                "bold": True,
                "font_size": 18,
                "font_color": theme.WHITE_HEX,
                "bg_color": theme.NAVY_HEX,
                "align": "center",
                "valign": "vcenter",
            }
        ),
        "section": workbook.add_format(
            {
                "bold": True,
                "font_size": 12,
                "font_color": theme.NAVY_HEX,
                "bg_color": theme.LIGHT_BLUE_HEX,
                "border": 1,
                "border_color": "#CBD5E1",
            }
        ),
        "label": workbook.add_format(
            {
                "bold": True,
                "font_color": theme.NAVY_HEX,
                "bg_color": theme.LIGHT_GRAY_HEX,
                "border": 1,
                "border_color": "#D0D5DD",
                "valign": "top",
            }
        ),
        "value": workbook.add_format(
            {
                "font_color": theme.DARK_HEX,
                "border": 1,
                "border_color": "#D0D5DD",
                "text_wrap": True,
                "valign": "top",
            }
        ),
        "note": workbook.add_format(
            {
                "italic": True,
                "font_color": theme.MID_GRAY_HEX,
                "text_wrap": True,
                "valign": "top",
            }
        ),
        "info": workbook.add_format(
            {
                "font_color": theme.INFO_FONT_HEX,
                "bg_color": theme.INFO_HEX,
                "border": 1,
                "border_color": theme.INFO_BORDER_HEX,
                "text_wrap": True,
            }
        ),
        "warning": workbook.add_format(
            {
                "font_color": theme.WARNING_FONT_HEX,
                "bg_color": theme.WARNING_HEX,
                "border": 1,
                "border_color": theme.WARNING_BORDER_HEX,
                "text_wrap": True,
            }
        ),
        "critical": workbook.add_format(
            {
                "font_color": theme.CRITICAL_FONT_HEX,
                "bg_color": theme.CRITICAL_HEX,
                "border": 1,
                "border_color": theme.CRITICAL_BORDER_HEX,
                "text_wrap": True,
            }
        ),
        "healthy": workbook.add_format(
            {
                "font_color": theme.HEALTHY_FONT_HEX,
                "bg_color": theme.HEALTHY_HEX,
                "border": 1,
                "border_color": theme.HEALTHY_BORDER_HEX,
                "text_wrap": True,
            }
        ),
    }


def _configure_sheet(
    worksheet: Any,
    *,
    widths: tuple[tuple[int, int, float], ...],
) -> None:
    worksheet.hide_gridlines(2)
    worksheet.freeze_panes(4, 0)
    worksheet.set_landscape()
    worksheet.fit_to_pages(1, 0)
    worksheet.set_margins(
        left=0.35,
        right=0.35,
        top=0.55,
        bottom=0.55,
    )
    worksheet.set_header("&CMplacas - Relatório Mensal")
    worksheet.set_footer("&LMplacas&C&P de &N&RExportação auditável")
    for first_column, last_column, width in widths:
        worksheet.set_column(first_column, last_column, width)


def _write_title(
    worksheet: Any,
    title: str,
    formats: dict[str, Any],
    last_column: int,
) -> None:
    worksheet.set_row(0, 30)
    worksheet.merge_range(
        0,
        0,
        0,
        last_column,
        title,
        formats["title"],
    )


def _table_columns(headers: tuple[str, ...]) -> list[dict[str, str]]:
    return [{"header": header} for header in headers]


def _write_table(
    worksheet: Any,
    *,
    first_row: int,
    first_column: int,
    rows: list[list[str]],
    headers: tuple[str, ...],
    table_name: str,
    formats: dict[str, Any],
) -> int:
    last_column = first_column + len(headers) - 1
    if not rows:
        worksheet.write_row(
            first_row,
            first_column,
            headers,
            formats["label"],
        )
        worksheet.merge_range(
            first_row + 1,
            first_column,
            first_row + 1,
            last_column,
            "Nenhum registro disponível.",
            formats["info"],
        )
        return first_row + 1

    last_row = first_row + len(rows)
    worksheet.add_table(
        first_row,
        first_column,
        last_row,
        last_column,
        {
            "name": table_name,
            "style": "Table Style Medium 2",
            "columns": _table_columns(headers),
            "data": rows,
        },
    )
    return last_row


def _metric_rows(metrics: tuple[ReportMetric, ...]) -> list[list[str]]:
    return [
        [
            metric.label,
            metric.value,
            metric.unit or "",
            metric.nature,
            metric.source,
        ]
        for metric in metrics
    ]


def _write_metrics_sheet(
    worksheet: Any,
    *,
    title: str,
    metrics: tuple[ReportMetric, ...],
    formats: dict[str, Any],
    table_name: str,
) -> None:
    _configure_sheet(
        worksheet,
        widths=(
            (0, 0, 34),
            (1, 1, 16),
            (2, 2, 15),
            (3, 3, 24),
            (4, 4, 34),
        ),
    )
    _write_title(worksheet, title, formats, 4)
    worksheet.write(
        2,
        0,
        "Os valores são exportados sem recálculo.",
        formats["note"],
    )
    _write_table(
        worksheet,
        first_row=3,
        first_column=0,
        rows=_metric_rows(metrics),
        headers=("Indicador", "Valor", "Unidade", "Natureza", "Fonte"),
        table_name=table_name,
        formats=formats,
    )


def _severity_format(
    formats: dict[str, Any],
    severity: str,
) -> Any:
    return formats[theme.severity_token(severity)]


def _write_summary(
    workbook: Any,
    report: MonthlyEnergyReport,
    formats: dict[str, Any],
) -> None:
    worksheet = workbook.add_worksheet("Resumo")
    _configure_sheet(
        worksheet,
        widths=(
            (0, 0, 27),
            (1, 1, 44),
            (2, 2, 27),
            (3, 3, 44),
            (4, 5, 16),
        ),
    )
    _write_title(
        worksheet,
        "Mplacas - Relatório Mensal de Energia",
        formats,
        5,
    )
    worksheet.write(2, 0, "Síntese executiva", formats["section"])
    worksheet.merge_range(
        2,
        1,
        2,
        5,
        report.headline,
        formats["value"],
    )
    metadata = (
        ("Mês de referência", report.reference_month),
        ("Status", report.status),
        ("Usina", str(report.plant_id)),
        ("Fatura", str(report.bill_id)),
        ("Versão do esquema", report.schema_version),
        ("Versão do cálculo", report.calculation_version),
    )
    row = 4
    for index in range(0, len(metadata), 2):
        left_label, left_value = metadata[index]
        right_label, right_value = metadata[index + 1]
        worksheet.write(row, 0, left_label, formats["label"])
        worksheet.write(row, 1, left_value, formats["value"])
        worksheet.write(row, 2, right_label, formats["label"])
        worksheet.write(row, 3, right_value, formats["value"])
        row += 1
    worksheet.write(row + 1, 0, "Rastreabilidade", formats["section"])
    worksheet.merge_range(
        row + 1,
        1,
        row + 2,
        5,
        (
            "Este arquivo não recalcula indicadores. Os valores, diagnósticos e "
            "recomendações são projeções do relatório mensal auditado produzido "
            "pelo backend do Mplacas."
        ),
        formats["note"],
    )


def _write_diagnostics(
    workbook: Any,
    report: MonthlyEnergyReport,
    formats: dict[str, Any],
) -> None:
    worksheet = workbook.add_worksheet("Diagnosticos")
    _configure_sheet(
        worksheet,
        widths=(
            (0, 0, 28),
            (1, 1, 16),
            (2, 2, 55),
            (3, 3, 55),
        ),
    )
    _write_title(
        worksheet,
        "Diagnósticos e ações prioritárias",
        formats,
        3,
    )
    worksheet.write(2, 0, "Diagnósticos do ciclo", formats["section"])
    worksheet.write_row(
        3,
        0,
        ("Código", "Severidade", "Mensagem", "Ação recomendada"),
        formats["label"],
    )
    row = 4
    if report.diagnostics:
        for diagnostic in report.diagnostics:
            row_format = _severity_format(formats, diagnostic.severity)
            worksheet.write_row(
                row,
                0,
                (
                    diagnostic.code,
                    diagnostic.severity,
                    diagnostic.message,
                    diagnostic.recommended_action,
                ),
                row_format,
            )
            row += 1
    else:
        worksheet.merge_range(
            row,
            0,
            row,
            3,
            "Nenhum diagnóstico registrado para o ciclo.",
            formats["info"],
        )
        row += 1

    action_start = row + 2
    worksheet.write(
        action_start,
        0,
        "Ações prioritárias",
        formats["section"],
    )
    if report.priority_actions:
        for offset, action in enumerate(report.priority_actions, start=1):
            worksheet.write(
                action_start + offset,
                0,
                offset,
                formats["label"],
            )
            worksheet.merge_range(
                action_start + offset,
                1,
                action_start + offset,
                3,
                action,
                formats["value"],
            )
    else:
        worksheet.merge_range(
            action_start + 1,
            0,
            action_start + 1,
            3,
            "Nenhuma ação prioritária registrada.",
            formats["info"],
        )


def _write_trends(
    workbook: Any,
    report: MonthlyEnergyReport,
    formats: dict[str, Any],
) -> None:
    worksheet = workbook.add_worksheet("Tendencias")
    _configure_sheet(
        worksheet,
        widths=(
            (0, 0, 34),
            (1, 1, 18),
            (2, 2, 22),
            (3, 3, 22),
            (4, 4, 18),
        ),
    )
    _write_title(worksheet, "Tendência entre ciclos", formats, 4)
    if report.trend is None:
        worksheet.merge_range(
            3,
            0,
            4,
            4,
            "Não há ciclo anterior elegível para comparação.",
            formats["info"],
        )
        return

    worksheet.write(2, 0, "Período comparado", formats["label"])
    worksheet.merge_range(
        2,
        1,
        2,
        4,
        (
            f"{report.trend.previous_reference_month} para "
            f"{report.trend.current_reference_month}"
        ),
        formats["value"],
    )
    trend_rows = [
        [
            metric.label,
            metric.absolute_delta,
            metric.unit,
            metric.percent_delta or "",
            metric.direction,
        ]
        for metric in report.trend.metrics
    ]
    last_trend_row = _write_table(
        worksheet,
        first_row=4,
        first_column=0,
        rows=trend_rows,
        headers=(
            "Indicador",
            "Delta",
            "Unidade",
            "Delta percentual",
            "Direção",
        ),
        table_name="MonthlyTrends",
        formats=formats,
    )
    diagnostic_start = last_trend_row + 3
    worksheet.write(
        diagnostic_start,
        0,
        "Diagnósticos de tendência",
        formats["section"],
    )
    if report.trend.diagnostics:
        worksheet.write_row(
            diagnostic_start + 1,
            0,
            ("Código", "Severidade", "Mensagem", "Ação recomendada"),
            formats["label"],
        )
        for offset, diagnostic in enumerate(
            report.trend.diagnostics,
            start=2,
        ):
            row_format = _severity_format(formats, diagnostic.severity)
            worksheet.write_row(
                diagnostic_start + offset,
                0,
                (
                    diagnostic.code,
                    diagnostic.severity,
                    diagnostic.message,
                    diagnostic.recommended_action,
                ),
                row_format,
            )
    else:
        worksheet.merge_range(
            diagnostic_start + 1,
            0,
            diagnostic_start + 1,
            4,
            "Nenhum diagnóstico de tendência registrado.",
            formats["info"],
        )


def _write_metadata(
    workbook: Any,
    report: MonthlyEnergyReport,
    formats: dict[str, Any],
) -> None:
    worksheet = workbook.add_worksheet("Metadados")
    _configure_sheet(
        worksheet,
        widths=((0, 0, 30), (1, 1, 70)),
    )
    _write_title(
        worksheet,
        "Metadados e rastreabilidade",
        formats,
        1,
    )
    metadata_rows = (
        ("schema_version", report.schema_version),
        ("calculation_version", report.calculation_version),
        ("plant_id", str(report.plant_id)),
        ("bill_id", str(report.bill_id)),
        ("reference_month", report.reference_month),
        ("status", report.status),
        ("export_contract", "NO_RECALCULATION"),
        ("source", "MPLACAS_MONTHLY_ENERGY_REPORT"),
    )
    for row_index, (key, value) in enumerate(metadata_rows, start=3):
        worksheet.write(row_index, 0, key, formats["label"])
        worksheet.write(row_index, 1, value, formats["value"])


def build_monthly_report_xlsx(report: MonthlyEnergyReport) -> bytes:
    """Render the audited report to XLSX without formulas or recalculation."""

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(
        output,
        {
            "in_memory": True,
            "strings_to_formulas": False,
            "strings_to_urls": False,
        },
    )
    workbook.set_properties(
        {
            "title": f"Mplacas - Relatório mensal {report.reference_month}",
            "subject": "Relatório mensal auditável de energia",
            "author": "Mplacas",
            "comments": (
                "Exportação dos resultados determinísticos do Mplacas. "
                "Nenhum indicador é recalculado no arquivo."
            ),
        }
    )
    formats = _formats(workbook)

    _write_summary(workbook, report, formats)
    _write_metrics_sheet(
        workbook.add_worksheet("Indicadores"),
        title="Indicadores do ciclo",
        metrics=report.metrics,
        formats=formats,
        table_name="MonthlyMetrics",
    )
    _write_metrics_sheet(
        workbook.add_worksheet("Qualidade"),
        title="Qualidade dos dados",
        metrics=report.quality,
        formats=formats,
        table_name="MonthlyQuality",
    )
    _write_diagnostics(workbook, report, formats)
    _write_trends(workbook, report, formats)
    _write_metadata(workbook, report, formats)

    workbook.close()
    return output.getvalue()
