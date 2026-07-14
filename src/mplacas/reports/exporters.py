from __future__ import annotations

import io
from html import escape
from typing import Final

import xlsxwriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from mplacas.reports.service import MonthlyEnergyReport, ReportMetric

PDF_MEDIA_TYPE: Final = "application/pdf"
XLSX_MEDIA_TYPE: Final = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

_NAVY = colors.HexColor("#17324D")
_BLUE = colors.HexColor("#285F8F")
_LIGHT_BLUE = colors.HexColor("#EAF2F8")
_LIGHT_GRAY = colors.HexColor("#F4F6F7")
_MID_GRAY = colors.HexColor("#667085")
_DARK = colors.HexColor("#1F2937")
_GREEN = colors.HexColor("#26734D")
_AMBER = colors.HexColor("#9A6700")
_RED = colors.HexColor("#B42318")
_WHITE = colors.white


def _paragraph_text(value: object) -> str:
    return escape(str(value), quote=False).replace("\n", "<br/>")


def _pdf_styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            "MplacasTitle",
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=_NAVY,
            alignment=TA_CENTER,
            spaceAfter=5 * mm,
        ),
        "subtitle": ParagraphStyle(
            "MplacasSubtitle",
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=_MID_GRAY,
            alignment=TA_CENTER,
            spaceAfter=5 * mm,
        ),
        "section": ParagraphStyle(
            "MplacasSection",
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=_NAVY,
            spaceBefore=3 * mm,
            spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "MplacasBody",
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=_DARK,
            alignment=TA_LEFT,
        ),
        "small": ParagraphStyle(
            "MplacasSmall",
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=_MID_GRAY,
            alignment=TA_LEFT,
        ),
        "table_header": ParagraphStyle(
            "MplacasTableHeader",
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=_WHITE,
            alignment=TA_LEFT,
        ),
        "table_cell": ParagraphStyle(
            "MplacasTableCell",
            fontName="Helvetica",
            fontSize=7.7,
            leading=9.5,
            textColor=_DARK,
            alignment=TA_LEFT,
        ),
    }


def _pdf_table(
    headers: tuple[str, ...],
    rows: list[tuple[object, ...]],
    *,
    widths: tuple[float, ...],
    styles: dict[str, ParagraphStyle],
) -> LongTable:
    data: list[list[Paragraph]] = [
        [Paragraph(_paragraph_text(header), styles["table_header"]) for header in headers]
    ]
    data.extend(
        [
            [Paragraph(_paragraph_text(value), styles["table_cell"]) for value in row]
            for row in rows
        ]
    )
    table = LongTable(
        data,
        colWidths=list(widths),
        repeatRows=1,
        hAlign="LEFT",
        splitByRow=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _LIGHT_GRAY]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _metric_rows(metrics: tuple[ReportMetric, ...]) -> list[tuple[object, ...]]:
    return [
        (
            metric.label,
            metric.value,
            metric.unit or "-",
            metric.nature,
            metric.source,
        )
        for metric in metrics
    ]


def _pdf_page_decorator(report: MonthlyEnergyReport):
    def draw_page(canvas, document) -> None:
        canvas.saveState()
        canvas.setTitle(f"Mplacas - Relatório mensal {report.reference_month}")
        canvas.setAuthor("Mplacas")
        canvas.setSubject("Relatório mensal auditável de energia")
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(_MID_GRAY)
        footer = (
            f"Mplacas | esquema {report.schema_version} | "
            f"cálculo {report.calculation_version}"
        )
        canvas.drawString(18 * mm, 11 * mm, footer)
        canvas.drawRightString(A4[0] - 18 * mm, 11 * mm, f"Página {document.page}")
        canvas.setStrokeColor(colors.HexColor("#D0D5DD"))
        canvas.setLineWidth(0.4)
        canvas.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
        canvas.restoreState()

    return draw_page


def build_monthly_report_pdf(report: MonthlyEnergyReport) -> bytes:
    """Render the audited monthly report to PDF without recalculating indicators."""

    output = io.BytesIO()
    styles = _pdf_styles()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=22 * mm,
        title=f"Mplacas - Relatório mensal {report.reference_month}",
        author="Mplacas",
        subject="Relatório mensal auditável de energia",
    )
    story: list[object] = [
        Paragraph("Mplacas - Relatório Mensal de Energia", styles["title"]),
        Paragraph(
            "Exportação auditável dos resultados produzidos pelo motor determinístico.",
            styles["subtitle"],
        ),
    ]

    metadata = Table(
        [
            ["Mês de referência", report.reference_month, "Status", report.status],
            ["Usina", str(report.plant_id), "Fatura", str(report.bill_id)],
            ["Versão do esquema", report.schema_version, "Versão do cálculo", report.calculation_version],
        ],
        colWidths=[35 * mm, 52 * mm, 35 * mm, 52 * mm],
        hAlign="LEFT",
    )
    metadata.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), _LIGHT_BLUE),
                ("BACKGROUND", (2, 0), (2, -1), _LIGHT_BLUE),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.8),
                ("TEXTCOLOR", (0, 0), (-1, -1), _DARK),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.extend(
        [
            metadata,
            Spacer(1, 5 * mm),
            KeepTogether(
                [
                    Paragraph("Síntese executiva", styles["section"]),
                    Paragraph(_paragraph_text(report.headline), styles["body"]),
                ]
            ),
            Paragraph("Indicadores do ciclo", styles["section"]),
            _pdf_table(
                ("Indicador", "Valor", "Unidade", "Natureza", "Fonte"),
                _metric_rows(report.metrics),
                widths=(50 * mm, 24 * mm, 18 * mm, 35 * mm, 47 * mm),
                styles=styles,
            ),
            Paragraph("Qualidade dos dados", styles["section"]),
            _pdf_table(
                ("Indicador", "Valor", "Unidade", "Natureza", "Fonte"),
                _metric_rows(report.quality),
                widths=(50 * mm, 24 * mm, 18 * mm, 35 * mm, 47 * mm),
                styles=styles,
            ),
        ]
    )

    if report.diagnostics:
        story.extend(
            [
                Paragraph("Diagnósticos", styles["section"]),
                _pdf_table(
                    ("Código", "Severidade", "Mensagem", "Ação recomendada"),
                    [
                        (
                            diagnostic.code,
                            diagnostic.severity,
                            diagnostic.message,
                            diagnostic.recommended_action,
                        )
                        for diagnostic in report.diagnostics
                    ],
                    widths=(38 * mm, 25 * mm, 56 * mm, 55 * mm),
                    styles=styles,
                ),
            ]
        )

    if report.priority_actions:
        story.extend(
            [
                Paragraph("Ações prioritárias", styles["section"]),
                *[
                    Paragraph(
                        f"{index}. {_paragraph_text(action)}",
                        styles["body"],
                    )
                    for index, action in enumerate(report.priority_actions, start=1)
                ],
            ]
        )

    if report.trend is not None:
        story.extend(
            [
                PageBreak(),
                Paragraph("Tendência entre ciclos", styles["section"]),
                Paragraph(
                    (
                        f"Comparação: {report.trend.previous_reference_month} para "
                        f"{report.trend.current_reference_month}."
                    ),
                    styles["body"],
                ),
                Spacer(1, 2 * mm),
                _pdf_table(
                    ("Indicador", "Delta", "Unidade", "Delta percentual", "Direção"),
                    [
                        (
                            metric.label,
                            metric.absolute_delta,
                            metric.unit,
                            metric.percent_delta or "-",
                            metric.direction,
                        )
                        for metric in report.trend.metrics
                    ],
                    widths=(52 * mm, 30 * mm, 31 * mm, 33 * mm, 28 * mm),
                    styles=styles,
                ),
            ]
        )
        if report.trend.diagnostics:
            story.extend(
                [
                    Paragraph("Diagnósticos de tendência", styles["section"]),
                    _pdf_table(
                        ("Código", "Severidade", "Mensagem", "Ação recomendada"),
                        [
                            (
                                diagnostic.code,
                                diagnostic.severity,
                                diagnostic.message,
                                diagnostic.recommended_action,
                            )
                            for diagnostic in report.trend.diagnostics
                        ],
                        widths=(38 * mm, 25 * mm, 56 * mm, 55 * mm),
                        styles=styles,
                    ),
                ]
            )

    story.extend(
        [
            Spacer(1, 5 * mm),
            Paragraph(
                (
                    "Nota de rastreabilidade: este documento não recalcula indicadores. "
                    "Os valores, diagnósticos e recomendações são projeções do relatório "
                    "mensal auditado produzido pelo backend do Mplacas."
                ),
                styles["small"],
            ),
        ]
    )
    decorate = _pdf_page_decorator(report)
    document.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return output.getvalue()


def _xlsx_formats(workbook) -> dict[str, object]:
    return {
        "title": workbook.add_format(
            {
                "bold": True,
                "font_size": 18,
                "font_color": "#FFFFFF",
                "bg_color": "#17324D",
                "align": "center",
                "valign": "vcenter",
            }
        ),
        "section": workbook.add_format(
            {
                "bold": True,
                "font_size": 12,
                "font_color": "#17324D",
                "bg_color": "#EAF2F8",
                "border": 1,
                "border_color": "#CBD5E1",
            }
        ),
        "label": workbook.add_format(
            {
                "bold": True,
                "font_color": "#17324D",
                "bg_color": "#F4F6F7",
                "border": 1,
                "border_color": "#D0D5DD",
                "valign": "top",
            }
        ),
        "value": workbook.add_format(
            {
                "font_color": "#1F2937",
                "border": 1,
                "border_color": "#D0D5DD",
                "text_wrap": True,
                "valign": "top",
            }
        ),
        "note": workbook.add_format(
            {
                "italic": True,
                "font_color": "#667085",
                "text_wrap": True,
                "valign": "top",
            }
        ),
        "info": workbook.add_format(
            {
                "font_color": "#1F2937",
                "bg_color": "#EAF2F8",
                "border": 1,
                "border_color": "#CBD5E1",
                "text_wrap": True,
            }
        ),
        "warning": workbook.add_format(
            {
                "font_color": "#9A6700",
                "bg_color": "#FFF8E1",
                "border": 1,
                "border_color": "#E5C07B",
                "text_wrap": True,
            }
        ),
        "critical": workbook.add_format(
            {
                "font_color": "#B42318",
                "bg_color": "#FDECEC",
                "border": 1,
                "border_color": "#F2A7A0",
                "text_wrap": True,
            }
        ),
        "healthy": workbook.add_format(
            {
                "font_color": "#26734D",
                "bg_color": "#EAF7EF",
                "border": 1,
                "border_color": "#9ED5B4",
                "text_wrap": True,
            }
        ),
    }


def _configure_sheet(worksheet, *, widths: tuple[tuple[int, int, float], ...]) -> None:
    worksheet.hide_gridlines(2)
    worksheet.freeze_panes(4, 0)
    worksheet.set_landscape()
    worksheet.fit_to_pages(1, 0)
    worksheet.set_margins(left=0.35, right=0.35, top=0.55, bottom=0.55)
    worksheet.set_header("&CMplacas - Relatório Mensal")
    worksheet.set_footer("&LEsquema &F&C&P de &N&RExportação auditável")
    for first_column, last_column, width in widths:
        worksheet.set_column(first_column, last_column, width)


def _write_sheet_title(worksheet, title: str, formats: dict[str, object], last_column: int) -> None:
    worksheet.set_row(0, 30)
    worksheet.merge_range(0, 0, 0, last_column, title, formats["title"])


def _table_columns(headers: tuple[str, ...]) -> list[dict[str, str]]:
    return [{"header": header} for header in headers]


def _write_metrics_sheet(
    workbook,
    worksheet,
    *,
    title: str,
    metrics: tuple[ReportMetric, ...],
    formats: dict[str, object],
    table_name: str,
) -> None:
    _configure_sheet(
        worksheet,
        widths=((0, 0, 34), (1, 1, 16), (2, 2, 15), (3, 3, 24), (4, 4, 34)),
    )
    _write_sheet_title(worksheet, title, formats, 4)
    worksheet.write(2, 0, "Os valores são exportados sem recálculo.", formats["note"])
    rows = [
        [metric.label, metric.value, metric.unit or "", metric.nature, metric.source]
        for metric in metrics
    ]
    worksheet.add_table(
        3,
        0,
        3 + len(rows),
        4,
        {
            "name": table_name,
            "style": "Table Style Medium 2",
            "columns": _table_columns(("Indicador", "Valor", "Unidade", "Natureza", "Fonte")),
            "data": rows,
        },
    )
    worksheet.autofilter(3, 0, 3 + len(rows), 4)


def _severity_format(formats: dict[str, object], severity: str):
    normalized = severity.upper()
    if normalized in {"CRITICAL", "ERROR"}:
        return formats["critical"]
    if normalized in {"WARNING", "WARN"}:
        return formats["warning"]
    if normalized in {"HEALTHY", "SUCCESS"}:
        return formats["healthy"]
    return formats["info"]


def build_monthly_report_xlsx(report: MonthlyEnergyReport) -> bytes:
    """Render the audited monthly report to XLSX without formulas or recalculation."""

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
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
    formats = _xlsx_formats(workbook)

    summary = workbook.add_worksheet("Resumo")
    _configure_sheet(
        summary,
        widths=((0, 0, 27), (1, 1, 44), (2, 2, 27), (3, 3, 44), (4, 5, 16)),
    )
    _write_sheet_title(summary, "Mplacas - Relatório Mensal de Energia", formats, 5)
    summary.write(2, 0, "Síntese executiva", formats["section"])
    summary.merge_range(2, 1, 2, 5, report.headline, formats["value"])
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
        summary.write(row, 0, left_label, formats["label"])
        summary.write(row, 1, left_value, formats["value"])
        summary.write(row, 2, right_label, formats["label"])
        summary.write(row, 3, right_value, formats["value"])
        row += 1
    summary.write(row + 1, 0, "Rastreabilidade", formats["section"])
    summary.merge_range(
        row + 1,
        1,
        row + 2,
        5,
        (
            "Este arquivo não recalcula indicadores. Os valores, diagnósticos e recomendações "
            "são projeções do relatório mensal auditado produzido pelo backend do Mplacas."
        ),
        formats["note"],
    )

    metrics_sheet = workbook.add_worksheet("Indicadores")
    _write_metrics_sheet(
        workbook,
        metrics_sheet,
        title="Indicadores do ciclo",
        metrics=report.metrics,
        formats=formats,
        table_name="MonthlyMetrics",
    )

    quality_sheet = workbook.add_worksheet("Qualidade")
    _write_metrics_sheet(
        workbook,
        quality_sheet,
        title="Qualidade dos dados",
        metrics=report.quality,
        formats=formats,
        table_name="MonthlyQuality",
    )

    diagnostics_sheet = workbook.add_worksheet("Diagnosticos")
    _configure_sheet(
        diagnostics_sheet,
        widths=((0, 0, 28), (1, 1, 16), (2, 2, 55), (3, 3, 55)),
    )
    _write_sheet_title(diagnostics_sheet, "Diagnósticos e ações prioritárias", formats, 3)
    diagnostics_sheet.write(2, 0, "Diagnósticos do ciclo", formats["section"])
    diagnostic_row = 4
    diagnostics_sheet.write_row(
        3,
        0,
        ("Código", "Severidade", "Mensagem", "Ação recomendada"),
        formats["label"],
    )
    if report.diagnostics:
        for diagnostic in report.diagnostics:
            row_format = _severity_format(formats, diagnostic.severity)
            diagnostics_sheet.write_row(
                diagnostic_row,
                0,
                (
                    diagnostic.code,
                    diagnostic.severity,
                    diagnostic.message,
                    diagnostic.recommended_action,
                ),
                row_format,
            )
            diagnostic_row += 1
    else:
        diagnostics_sheet.merge_range(
            diagnostic_row,
            0,
            diagnostic_row,
            3,
            "Nenhum diagnóstico registrado para o ciclo.",
            formats["info"],
        )
        diagnostic_row += 1
    action_start = diagnostic_row + 2
    diagnostics_sheet.write(action_start, 0, "Ações prioritárias", formats["section"])
    if report.priority_actions:
        for offset, action in enumerate(report.priority_actions, start=1):
            diagnostics_sheet.write(action_start + offset, 0, offset, formats["label"])
            diagnostics_sheet.merge_range(
                action_start + offset,
                1,
                action_start + offset,
                3,
                action,
                formats["value"],
            )
    else:
        diagnostics_sheet.merge_range(
            action_start + 1,
            0,
            action_start + 1,
            3,
            "Nenhuma ação prioritária registrada.",
            formats["info"],
        )

    trends_sheet = workbook.add_worksheet("Tendencias")
    _configure_sheet(
        trends_sheet,
        widths=((0, 0, 34), (1, 1, 18), (2, 2, 22), (3, 3, 22), (4, 4, 18)),
    )
    _write_sheet_title(trends_sheet, "Tendência entre ciclos", formats, 4)
    if report.trend is None:
        trends_sheet.merge_range(
            3,
            0,
            4,
            4,
            "Não há ciclo anterior elegível para comparação.",
            formats["info"],
        )
    else:
        trends_sheet.write(2, 0, "Período comparado", formats["label"])
        trends_sheet.merge_range(
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
        trends_sheet.add_table(
            4,
            0,
            4 + len(trend_rows),
            4,
            {
                "name": "MonthlyTrends",
                "style": "Table Style Medium 2",
                "columns": _table_columns(
                    ("Indicador", "Delta", "Unidade", "Delta percentual", "Direção")
                ),
                "data": trend_rows,
            },
        )
        trend_diagnostic_start = 7 + len(trend_rows)
        trends_sheet.write(
            trend_diagnostic_start,
            0,
            "Diagnósticos de tendência",
            formats["section"],
        )
        if report.trend.diagnostics:
            trends_sheet.write_row(
                trend_diagnostic_start + 1,
                0,
                ("Código", "Severidade", "Mensagem", "Ação recomendada"),
                formats["label"],
            )
            for offset, diagnostic in enumerate(report.trend.diagnostics, start=2):
                row_format = _severity_format(formats, diagnostic.severity)
                trends_sheet.write_row(
                    trend_diagnostic_start + offset,
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
            trends_sheet.merge_range(
                trend_diagnostic_start + 1,
                0,
                trend_diagnostic_start + 1,
                4,
                "Nenhum diagnóstico de tendência registrado.",
                formats["info"],
            )

    metadata_sheet = workbook.add_worksheet("Metadados")
    _configure_sheet(metadata_sheet, widths=((0, 0, 30), (1, 1, 70)))
    _write_sheet_title(metadata_sheet, "Metadados e rastreabilidade", formats, 1)
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
        metadata_sheet.write(row_index, 0, key, formats["label"])
        metadata_sheet.write(row_index, 1, value, formats["value"])

    workbook.close()
    return output.getvalue()
