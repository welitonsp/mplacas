from __future__ import annotations

import io
from html import escape
from typing import Any, Callable, Final

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from mplacas.reports.service import MonthlyEnergyReport, ReportMetric

PDF_MEDIA_TYPE: Final = "application/pdf"

_NAVY = colors.HexColor("#17324D")
_LIGHT_BLUE = colors.HexColor("#EAF2F8")
_LIGHT_GRAY = colors.HexColor("#F4F6F7")
_MID_GRAY = colors.HexColor("#667085")
_DARK = colors.HexColor("#1F2937")
_WHITE = colors.white


def _safe_text(value: object) -> str:
    return escape(str(value), quote=False).replace("\n", "<br/>")


def _styles() -> dict[str, ParagraphStyle]:
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
            wordWrap="CJK",
        ),
        "metadata_label": ParagraphStyle(
            "MplacasMetadataLabel",
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=_NAVY,
            alignment=TA_LEFT,
        ),
        "metadata_value": ParagraphStyle(
            "MplacasMetadataValue",
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=_DARK,
            alignment=TA_LEFT,
        ),
    }


def _table(
    headers: tuple[str, ...],
    rows: list[tuple[object, ...]],
    *,
    widths: tuple[float, ...],
    styles: dict[str, ParagraphStyle],
) -> LongTable:
    data: list[list[Paragraph]] = [
        [Paragraph(_safe_text(header), styles["table_header"]) for header in headers]
    ]
    data.extend(
        [
            [Paragraph(_safe_text(value), styles["table_cell"]) for value in row]
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


def _page_decorator(
    report: MonthlyEnergyReport,
) -> Callable[[Any, Any], None]:
    def draw_page(canvas: Any, document: Any) -> None:
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
        canvas.drawRightString(
            A4[0] - 18 * mm,
            11 * mm,
            f"Página {document.page}",
        )
        canvas.setStrokeColor(colors.HexColor("#D0D5DD"))
        canvas.setLineWidth(0.4)
        canvas.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
        canvas.restoreState()

    return draw_page


def _metadata_table(
    report: MonthlyEnergyReport,
    styles: dict[str, ParagraphStyle],
) -> Table:
    rows = (
        ("Mês de referência", report.reference_month),
        ("Status", report.status),
        ("Usina", str(report.plant_id)),
        ("Fatura", str(report.bill_id)),
        ("Versão do esquema", report.schema_version),
        ("Versão do cálculo", report.calculation_version),
    )
    table = Table(
        [
            [
                Paragraph(_safe_text(label), styles["metadata_label"]),
                Paragraph(_safe_text(value), styles["metadata_value"]),
            ]
            for label, value in rows
        ],
        colWidths=[45 * mm, 129 * mm],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), _LIGHT_BLUE),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def build_monthly_report_pdf(report: MonthlyEnergyReport) -> bytes:
    """Render the audited monthly report without recalculating indicators."""

    output = io.BytesIO()
    styles = _styles()
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
    story: list[Flowable] = [
        Paragraph("Mplacas - Relatório Mensal de Energia", styles["title"]),
        Paragraph(
            "Exportação auditável: este documento não recalcula indicadores.",
            styles["subtitle"],
        ),
        _metadata_table(report, styles),
        Spacer(1, 5 * mm),
        KeepTogether(
            [
                Paragraph("Síntese executiva", styles["section"]),
                Paragraph(_safe_text(report.headline), styles["body"]),
            ]
        ),
        Paragraph("Indicadores do ciclo", styles["section"]),
        _table(
            ("Indicador", "Valor", "Unidade", "Natureza", "Fonte"),
            _metric_rows(report.metrics),
            widths=(48 * mm, 22 * mm, 22 * mm, 36 * mm, 46 * mm),
            styles=styles,
        ),
        Paragraph("Qualidade dos dados", styles["section"]),
        _table(
            ("Indicador", "Valor", "Unidade", "Natureza", "Fonte"),
            _metric_rows(report.quality),
            widths=(48 * mm, 22 * mm, 22 * mm, 36 * mm, 46 * mm),
            styles=styles,
        ),
    ]

    if report.diagnostics:
        story.extend(
            [
                Paragraph("Diagnósticos", styles["section"]),
                _table(
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
                    widths=(44 * mm, 24 * mm, 53 * mm, 53 * mm),
                    styles=styles,
                ),
            ]
        )

    if report.priority_actions:
        story.append(Paragraph("Ações prioritárias", styles["section"]))
        story.extend(
            Paragraph(
                f"{index}. {_safe_text(action)}",
                styles["body"],
            )
            for index, action in enumerate(report.priority_actions, start=1)
        )

    if report.trend is not None:
        trend_table = _table(
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
        )
        story.append(
            KeepTogether(
                [
                    Paragraph("Tendência entre ciclos", styles["section"]),
                    Paragraph(
                        (
                            f"Comparação: {report.trend.previous_reference_month} para "
                            f"{report.trend.current_reference_month}."
                        ),
                        styles["body"],
                    ),
                    Spacer(1, 2 * mm),
                    trend_table,
                ]
            )
        )
        if report.trend.diagnostics:
            trend_diagnostics_table = _table(
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
                widths=(44 * mm, 24 * mm, 53 * mm, 53 * mm),
                styles=styles,
            )
            story.append(
                KeepTogether(
                    [
                        Paragraph("Diagnósticos de tendência", styles["section"]),
                        trend_diagnostics_table,
                    ]
                )
            )

    decorate = _page_decorator(report)
    document.build(
        story,
        onFirstPage=decorate,
        onLaterPages=decorate,
    )
    return output.getvalue()
