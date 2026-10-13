"""PDF do relatório mensal.

Renderiza o snapshot auditado (:class:`MonthlyEnergyReport`) sem recalcular
nenhum indicador: tudo o que aparece aqui é um valor já persistido, apenas
formatado para leitura (separador decimal, unidade, rótulo em português). As
barras de divisão de energia desenham proporções visuais entre valores do
próprio snapshot e não exibem percentuais derivados.

Linguagem visual (2026-10): cabeçalho com régua marinho, bloco de
identificação, seções numeradas com barra lateral, cartões de número grande e
um anexo de auditoria com os valores exatos, a natureza e a fonte de cada
indicador.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from html import escape
from typing import Any, Final

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
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

from mplacas.reports.contract import (
    MonthlyEnergyReport,
    ReportDiagnostic,
    ReportMetric,
)
from mplacas.reports.export import theme

PDF_MEDIA_TYPE: Final = "application/pdf"

_PAGE_WIDTH, _PAGE_HEIGHT = A4
_MARGIN_X: Final = 16 * mm
# O Frame do SimpleDocTemplate tem 6 pt de padding em cada lado: a largura útil
# real é menor que a área entre margens. Tudo (tabelas, cartões, réguas do
# cabeçalho/rodapé) usa estas medidas para alinhar na mesma coluna.
_FRAME_PADDING: Final = 6
_CONTENT_LEFT: Final = _MARGIN_X + _FRAME_PADDING
_CONTENT_RIGHT: Final = _PAGE_WIDTH - _MARGIN_X - _FRAME_PADDING
_CONTENT_WIDTH: Final = _CONTENT_RIGHT - _CONTENT_LEFT

_REGULAR: Final = "Helvetica"
_BOLD: Final = "Helvetica-Bold"

_GREEN = colors.HexColor(theme.REPORT_GREEN_HEX)
_GREEN_TINT = colors.HexColor(theme.REPORT_GREEN_TINT_HEX)
_NAVY = colors.HexColor(theme.REPORT_NAVY_HEX)
_NAVY_SOFT = colors.HexColor(theme.REPORT_NAVY_SOFT_HEX)
_INK = colors.HexColor(theme.REPORT_INK_HEX)
_MUTED = colors.HexColor(theme.REPORT_MUTED_HEX)
_SURFACE = colors.HexColor(theme.REPORT_SURFACE_HEX)
_SURFACE_SOFT = colors.HexColor(theme.REPORT_SURFACE_SOFT_HEX)
_BORDER = colors.HexColor(theme.REPORT_BORDER_HEX)
_TRACK = colors.HexColor(theme.REPORT_TRACK_HEX)
_ORANGE = colors.HexColor(theme.REPORT_ORANGE_HEX)
_RED = colors.HexColor(theme.REPORT_RED_HEX)
_WHITE = colors.white

_MONTHS_PT: Final = (
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)

_STATUS_LABELS: Final = {
    "HEALTHY": ("Saudável", _GREEN),
    "ATTENTION": ("Atenção", _ORANGE),
    "CRITICAL": ("Crítico", _RED),
}

_SEVERITY_LABELS: Final = {
    "critical": ("Crítico", _RED, colors.HexColor(theme.CRITICAL_HEX)),
    "warning": ("Atenção", _ORANGE, colors.HexColor(theme.WARNING_HEX)),
    "healthy": ("Saudável", _GREEN, _GREEN_TINT),
    "info": ("Informativo", _NAVY, _SURFACE),
}

_NATURE_LABELS: Final = {
    "MEASURED": "Medido",
    "MEASURED_AGGREGATE": "Medido (soma diária)",
    "CALCULATED": "Calculado",
    "CALCULATED_SCORE": "Pontuação calculada",
    "QUALITY_COUNT": "Contagem de qualidade",
    "UNAVAILABILITY_REASON": "Motivo de indisponibilidade",
}

_SOURCE_LABELS: Final = {
    "DAILY_ENERGY_AGGREGATE": "Leituras diárias do inversor",
    "UTILITY_BILL_CONFIRMED": "Fatura confirmada",
    "MPLACAS_DETERMINISTIC_ENGINE": "Motor determinístico MPlacas",
}

_UNAVAILABILITY_LABELS: Final = {
    "TARIFF_NOT_AVAILABLE": "a tarifa da concessionária não está cadastrada",
    "NO_CONSUMPTION_DATA": "não há dados de consumo neste ciclo",
}

_DIRECTION_LABELS: Final = {
    "UP": "Alta",
    "DOWN": "Queda",
    "STABLE": "Estável",
    "DELTA": "Variação",
}

_TREND_UNIT_LABELS: Final = {
    "percentage_points": "p.p.",
    "score_points": "pontos",
}

_AUDIT_UNIT_LABELS: Final = {
    "days": "dias",
    "score_0_100": "(escala 0–100)",
}


# ---------------------------------------------------------------------------
# Formatação (apresentação apenas — nenhum valor novo é calculado)
# ---------------------------------------------------------------------------


def _safe_text(value: object) -> str:
    return escape(str(value), quote=False).replace("\n", "<br/>")


def _decimal(value: str) -> Decimal | None:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _number_br(value: Decimal, places: int = 2) -> str:
    quantum = Decimal(1).scaleb(-places)
    rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
    text = f"{rounded:,.{places}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _month_label(reference_month: str) -> str:
    year, _, month = reference_month.partition("-")
    if year.isdigit() and month.isdigit() and 1 <= int(month) <= 12:
        return f"{_MONTHS_PT[int(month) - 1]}/{year}"
    return reference_month


def _find(metrics: Sequence[ReportMetric], key: str) -> ReportMetric | None:
    for metric in metrics:
        if metric.key == key:
            return metric
    return None


def _format_value(value: str, unit: str | None) -> str | None:
    """Valor legível com unidade, ou ``None`` quando indisponível."""
    if value == "":
        return None
    number = _decimal(value)
    if number is None:
        return value
    if unit == "BRL":
        return f"R$ {_number_br(number)}"
    if unit == "%":
        return f"{_number_br(number)}%"
    if unit == "days":
        days = _number_br(number, 0)
        return f"{days} dia" if days == "1" else f"{days} dias"
    if unit == "score_0_100":
        places = 0 if number == number.to_integral_value() else 1
        return f"{_number_br(number, places)}/100"
    if unit:
        return f"{_number_br(number)} {unit}"
    return _number_br(number)


def _format_metric(metric: ReportMetric | None) -> str | None:
    if metric is None:
        return None
    return _format_value(metric.value, metric.unit)


# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "brand": ParagraphStyle(
            "MplacasBrand", fontName=_BOLD, fontSize=20, leading=22, textColor=_NAVY
        ),
        "doc_title": ParagraphStyle(
            "MplacasDocTitle",
            fontName=_BOLD,
            fontSize=12.5,
            leading=15,
            textColor=_NAVY,
            alignment=TA_RIGHT,
        ),
        "notice": ParagraphStyle(
            "MplacasNotice",
            fontName=_REGULAR,
            fontSize=7.5,
            leading=10,
            textColor=_MUTED,
        ),
        "id_label": ParagraphStyle(
            "MplacasIdLabel",
            fontName=_BOLD,
            fontSize=6.3,
            leading=8,
            textColor=_MUTED,
        ),
        "id_value": ParagraphStyle(
            "MplacasIdValue",
            fontName=_BOLD,
            fontSize=9,
            leading=11.5,
            textColor=_INK,
        ),
        "id_value_small": ParagraphStyle(
            "MplacasIdValueSmall",
            fontName=_REGULAR,
            fontSize=7.4,
            leading=9.5,
            textColor=_INK,
        ),
        "section": ParagraphStyle(
            "MplacasSection",
            fontName=_BOLD,
            fontSize=9.3,
            leading=11,
            textColor=_NAVY,
        ),
        "section_note": ParagraphStyle(
            "MplacasSectionNote",
            fontName=_REGULAR,
            fontSize=6.8,
            leading=9,
            textColor=_MUTED,
            alignment=TA_RIGHT,
        ),
        "headline": ParagraphStyle(
            "MplacasHeadline",
            fontName=_REGULAR,
            fontSize=9.6,
            leading=13.5,
            textColor=_INK,
        ),
        "body": ParagraphStyle(
            "MplacasBody",
            fontName=_REGULAR,
            fontSize=8.4,
            leading=11.5,
            textColor=_INK,
            alignment=TA_LEFT,
        ),
        "caption": ParagraphStyle(
            "MplacasCaption",
            fontName=_REGULAR,
            fontSize=7.2,
            leading=9.5,
            textColor=_MUTED,
        ),
        "card_kicker": ParagraphStyle(
            "MplacasCardKicker",
            fontName=_BOLD,
            fontSize=6.5,
            leading=8.5,
            textColor=_MUTED,
        ),
        "card_title": ParagraphStyle(
            "MplacasCardTitle",
            fontName=_BOLD,
            fontSize=8.8,
            leading=11.5,
            textColor=_INK,
        ),
        "table_header": ParagraphStyle(
            "MplacasTableHeader",
            fontName=_BOLD,
            fontSize=6.8,
            leading=8.5,
            textColor=_WHITE,
        ),
        "table_cell": ParagraphStyle(
            "MplacasTableCell",
            fontName=_REGULAR,
            fontSize=7.5,
            leading=9.5,
            textColor=_INK,
            wordWrap="CJK",
        ),
        "table_cell_strong": ParagraphStyle(
            "MplacasTableCellStrong",
            fontName=_BOLD,
            fontSize=7.5,
            leading=9.5,
            textColor=_NAVY,
            wordWrap="CJK",
        ),
    }


# ---------------------------------------------------------------------------
# Componentes desenhados
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Kpi:
    label: str
    value: str | None
    tone: str  # "green" | "navy"
    unavailable_text: str = "—"


def _fit_font_size(text: str, font: str, preferred: float, minimum: float, width: float) -> float:
    size = preferred
    while size > minimum and stringWidth(text, font, size) > width:
        size -= 0.5
    return size


class _KpiRow(Flowable):
    """Cartões lado a lado: rótulo pequeno em caixa alta + número grande."""

    def __init__(
        self,
        cards: Sequence[_Kpi],
        *,
        height: float = 17 * mm,
        value_size: float = 16,
        gap: float = 4 * mm,
    ) -> None:
        super().__init__()
        self._cards = tuple(cards)
        self._height = height
        self._value_size = value_size
        self._gap = gap
        self._width = _CONTENT_WIDTH

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        self._width = availWidth
        return availWidth, self._height

    def draw(self) -> None:
        canvas = self.canv
        count = len(self._cards)
        card_width = (self._width - self._gap * (count - 1)) / count
        for index, card in enumerate(self._cards):
            x = index * (card_width + self._gap)
            accent = _GREEN if card.tone == "green" else _NAVY
            border = _GREEN if card.tone == "green" else _BORDER
            canvas.setFillColor(_WHITE)
            canvas.setStrokeColor(border)
            canvas.setLineWidth(0.8)
            canvas.roundRect(x, 0, card_width, self._height, 2.2 * mm, stroke=1, fill=1)

            center = x + card_width / 2
            label = card.label.upper()
            label_size = _fit_font_size(
                label, _BOLD, 6.2, 5, card_width - 4 * mm - len(label) * 0.35
            )
            canvas.setFillColor(accent)
            canvas.setFont(_BOLD, label_size)
            canvas.drawCentredString(center, self._height - 5 * mm, label, charSpace=0.35)

            available = card.value is not None
            text = card.value if card.value is not None else card.unavailable_text
            font_size = _fit_font_size(text, _BOLD, self._value_size, 8, card_width - 6 * mm)
            canvas.setFillColor(accent if available else _MUTED)
            canvas.setFont(_BOLD, font_size)
            baseline = (self._height - 5 * mm) / 2 - font_size * 0.32
            canvas.drawCentredString(center, max(baseline, 2.2 * mm), text)


@dataclass(frozen=True, slots=True)
class _Segment:
    label: str
    value: Decimal
    display: str
    color: Any


@dataclass(frozen=True, slots=True)
class _Split:
    title: str
    segments: tuple[_Segment, ...]


class _SplitBars(Flowable):
    """Barras horizontais empilhadas, uma por coluna.

    As larguras são proporcionais aos valores do snapshot; nenhuma
    porcentagem derivada é exibida — a legenda mostra o valor registrado.
    """

    _TITLE_GAP = 4.5 * mm
    _BAR_HEIGHT = 4 * mm
    _LINE = 4.2 * mm

    def __init__(self, splits: Sequence[_Split], *, gap: float = 9 * mm) -> None:
        super().__init__()
        self._splits = tuple(splits)
        self._gap = gap
        self._width = _CONTENT_WIDTH
        lines = max(len(split.segments) for split in self._splits)
        self._height = self._TITLE_GAP + self._BAR_HEIGHT + 2.2 * mm + lines * self._LINE

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        self._width = availWidth
        return availWidth, self._height

    def draw(self) -> None:
        canvas = self.canv
        count = len(self._splits)
        column = (self._width - self._gap * (count - 1)) / count
        for index, split in enumerate(self._splits):
            x0 = index * (column + self._gap)
            top = self._height
            canvas.setFillColor(_INK)
            canvas.setFont(_BOLD, 7.6)
            canvas.drawString(x0, top - 3 * mm, split.title)

            bar_y = top - self._TITLE_GAP - self._BAR_HEIGHT
            radius = self._BAR_HEIGHT / 2
            total = sum((segment.value for segment in split.segments), Decimal(0))
            canvas.saveState()
            path = canvas.beginPath()
            path.roundRect(x0, bar_y, column, self._BAR_HEIGHT, radius)
            canvas.clipPath(path, stroke=0, fill=0)
            canvas.setFillColor(_TRACK)
            canvas.rect(x0, bar_y, column, self._BAR_HEIGHT, stroke=0, fill=1)
            cursor = x0
            if total > 0:
                for segment in split.segments:
                    width = float(segment.value / total) * column
                    canvas.setFillColor(segment.color)
                    canvas.rect(cursor, bar_y, width, self._BAR_HEIGHT, stroke=0, fill=1)
                    cursor += width
            canvas.restoreState()

            y = bar_y - 2.2 * mm - 2.6 * mm
            for segment in split.segments:
                canvas.setFillColor(segment.color)
                canvas.roundRect(x0, y - 0.2 * mm, 2.4 * mm, 2.4 * mm, 0.5 * mm, stroke=0, fill=1)
                canvas.setFillColor(_MUTED)
                canvas.setFont(_REGULAR, 7.2)
                canvas.drawString(x0 + 4 * mm, y, segment.label)
                canvas.setFillColor(_INK)
                canvas.setFont(_BOLD, 7.4)
                canvas.drawRightString(x0 + column, y, segment.display)
                y -= self._LINE


class _Pill(Flowable):
    """Selo arredondado com texto branco (ex.: direção da tendência)."""

    def __init__(self, text: str, color: Any) -> None:
        super().__init__()
        self._text = text
        self._color = color
        self._height = 4.6 * mm
        self._width = stringWidth(text, _BOLD, 6.6) + 6 * mm
        self.hAlign = "CENTER"

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        return self._width, self._height

    def draw(self) -> None:
        canvas = self.canv
        canvas.setFillColor(self._color)
        canvas.roundRect(0, 0, self._width, self._height, self._height / 2, stroke=0, fill=1)
        canvas.setFillColor(_WHITE)
        canvas.setFont(_BOLD, 6.6)
        canvas.drawCentredString(self._width / 2, self._height / 2 - 2.3, self._text)


# ---------------------------------------------------------------------------
# Blocos de layout
# ---------------------------------------------------------------------------


def _header(styles: dict[str, ParagraphStyle]) -> Table:
    table = Table(
        [
            [
                Paragraph(
                    f'M<font color="{theme.REPORT_GREEN_HEX}">Placas</font>', styles["brand"]
                ),
                Paragraph("RELATÓRIO MENSAL DE ENERGIA", styles["doc_title"]),
            ]
        ],
        colWidths=[_CONTENT_WIDTH * 0.4, _CONTENT_WIDTH * 0.6],
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, 0), 1.6, _NAVY),
            ]
        )
    )
    return table


def _id_cell(
    label: str, value: str, style: ParagraphStyle, styles: dict[str, ParagraphStyle]
) -> list[Paragraph]:
    return [Paragraph(_safe_text(label), styles["id_label"]), Paragraph(value, style)]


def _identification(report: MonthlyEnergyReport, styles: dict[str, ParagraphStyle]) -> Table:
    status_label, status_color = _STATUS_LABELS.get(report.status.upper(), (report.status, _NAVY))
    status_html = (
        f'<font color="{status_color.hexval().replace("0x", "#")}">•</font> '
        f"{_safe_text(status_label)}"
    )
    cycle_html = (
        f"{_safe_text(_month_label(report.reference_month))} "
        f'<font name="{_REGULAR}" color="{theme.REPORT_MUTED_HEX}">'
        f"({_safe_text(report.reference_month)})</font>"
    )
    half = _CONTENT_WIDTH / 2
    table = Table(
        [
            [
                _id_cell("CICLO DE REFERÊNCIA", cycle_html, styles["id_value"], styles),
                _id_cell("SITUAÇÃO DO CICLO", status_html, styles["id_value"], styles),
            ],
            [
                _id_cell("USINA", _safe_text(report.plant_id), styles["id_value_small"], styles),
                _id_cell("FATURA", _safe_text(report.bill_id), styles["id_value_small"], styles),
            ],
        ],
        colWidths=[half, half],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _SURFACE_SOFT),
                ("BOX", (0, 0), (-1, -1), 0.7, _BORDER),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, _BORDER),
                ("ROUNDEDCORNERS", [5, 5, 5, 5]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _section(number: int, title: str, styles: dict[str, ParagraphStyle], note: str = "") -> Table:
    table = Table(
        [
            [
                Paragraph(_safe_text(f"{number}. {title.upper()}"), styles["section"]),
                Paragraph(_safe_text(note), styles["section_note"]),
            ]
        ],
        colWidths=[_CONTENT_WIDTH * 0.66, _CONTENT_WIDTH * 0.34],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _SURFACE),
                ("LINEBEFORE", (0, 0), (0, 0), 3, _NAVY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 8),
                ("LEFTPADDING", (1, 0), (1, 0), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
            ]
        )
    )
    table.keepWithNext = True
    return table


def _callout(content: list[Flowable], *, border: Any, background: Any) -> Table:
    table = Table([[content]], colWidths=[_CONTENT_WIDTH])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.8, border),
                ("ROUNDEDCORNERS", [5, 5, 5, 5]),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _diagnostic_card(diagnostic: ReportDiagnostic, styles: dict[str, ParagraphStyle]) -> Table:
    label, accent, background = _SEVERITY_LABELS[theme.severity_token(diagnostic.severity)]
    accent_hex = accent.hexval().replace("0x", "#")
    table = Table(
        [
            [
                [
                    Paragraph(
                        f'<font color="{accent_hex}">{_safe_text(label.upper())}</font>'
                        f"  ·  {_safe_text(diagnostic.code)}",
                        styles["card_kicker"],
                    ),
                    Paragraph(_safe_text(diagnostic.message), styles["card_title"]),
                    Paragraph(
                        f"<b>Ação recomendada:</b> {_safe_text(diagnostic.recommended_action)}",
                        styles["body"],
                    ),
                ]
            ]
        ],
        colWidths=[_CONTENT_WIDTH],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("LINEBEFORE", (0, 0), (0, 0), 3, accent),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _data_table(
    headers: tuple[str, ...],
    rows: list[list[Flowable]],
    *,
    widths: tuple[float, ...],
    styles: dict[str, ParagraphStyle],
    center_columns: tuple[int, ...] = (),
) -> LongTable:
    data: list[list[Flowable]] = [
        [Paragraph(_safe_text(header), styles["table_header"]) for header in headers]
    ]
    data.extend(rows)
    table = LongTable(data, colWidths=list(widths), repeatRows=1, hAlign="LEFT", splitByRow=1)
    commands: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _SURFACE_SOFT]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, _BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 1), (-1, -1), 5.5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5.5),
    ]
    for column in center_columns:
        commands.append(("ALIGN", (column, 0), (column, -1), "CENTER"))
    table.setStyle(TableStyle(commands))
    return table


def _cell(value: object, styles: dict[str, ParagraphStyle], *, strong: bool = False) -> Paragraph:
    return Paragraph(_safe_text(value), styles["table_cell_strong" if strong else "table_cell"])


# ---------------------------------------------------------------------------
# Seções
# ---------------------------------------------------------------------------


def _energy_section(
    report: MonthlyEnergyReport, styles: dict[str, ParagraphStyle]
) -> list[Flowable]:
    metrics = report.metrics
    savings = _find(metrics, "estimated_savings_brl")
    savings_unavailable = savings is not None and savings.value == ""
    flowables: list[Flowable] = [
        _KpiRow(
            (
                _Kpi(
                    "Produção do ciclo",
                    _format_metric(_find(metrics, "cycle_production_kwh")),
                    "green",
                ),
                _Kpi(
                    "Consumo total estimado",
                    _format_metric(_find(metrics, "estimated_total_consumption_kwh")),
                    "navy",
                ),
                _Kpi(
                    "Economia estimada",
                    _format_metric(savings),
                    "green",
                    unavailable_text="Indisponível" if savings_unavailable else "—",
                ),
            )
        )
    ]
    if savings_unavailable:
        reason = _find(metrics, "savings_unavailable_reason")
        reason_text = (
            _UNAVAILABILITY_LABELS.get(reason.value, reason.value)
            if reason is not None and reason.value
            else "o motivo não foi registrado neste relatório"
        )
        flowables.extend(
            [
                Spacer(1, 1.8 * mm),
                Paragraph(
                    f"Economia não exibida porque {_safe_text(reason_text)} — "
                    "o MPlacas não estima valores sem a base necessária.",
                    styles["caption"],
                ),
            ]
        )

    splits = [
        split
        for split in (
            _split(
                "Para onde foi a produção",
                metrics,
                (
                    (
                        "estimated_self_consumption_kwh",
                        "Consumida na própria casa (estimado)",
                        _GREEN,
                    ),
                    ("injected_kwh", "Injetada na rede", _NAVY),
                ),
            ),
            _split(
                "De onde veio o consumo",
                metrics,
                (
                    ("estimated_self_consumption_kwh", "Da própria usina (estimado)", _GREEN),
                    ("imported_kwh", "Importada da rede", _NAVY_SOFT),
                ),
            ),
        )
        if split is not None
    ]
    if splits:
        flowables.extend([Spacer(1, 5 * mm), _SplitBars(splits)])
    return flowables


def _split(
    title: str,
    metrics: Sequence[ReportMetric],
    parts: tuple[tuple[str, str, Any], ...],
) -> _Split | None:
    segments: list[_Segment] = []
    for key, label, color in parts:
        metric = _find(metrics, key)
        if metric is None:
            return None
        number = _decimal(metric.value)
        display = _format_value(metric.value, metric.unit)
        if number is None or number < 0 or display is None:
            return None
        segments.append(_Segment(label, number, display, color))
    return _Split(title, tuple(segments))


def _efficiency_section(report: MonthlyEnergyReport) -> list[Flowable]:
    metrics = report.metrics
    return [
        _KpiRow(
            (
                _Kpi(
                    "Autoconsumo",
                    _format_metric(_find(metrics, "self_consumption_rate_percent")),
                    "navy",
                ),
                _Kpi(
                    "Autossuficiência",
                    _format_metric(_find(metrics, "self_sufficiency_rate_percent")),
                    "navy",
                ),
                _Kpi(
                    "Cobertura por créditos",
                    _format_metric(_find(metrics, "credit_coverage_rate_percent")),
                    "navy",
                ),
                _Kpi("Índice de saúde", _format_metric(_find(metrics, "health_score")), "navy"),
            ),
            height=14 * mm,
            value_size=12.5,
            gap=3 * mm,
        )
    ]


class _QualityRow(Flowable):
    """Quatro contadores de qualidade; zero em verde, ocorrência em laranja."""

    _KEYS: Final = (
        ("missing_days", "Dias ausentes"),
        ("provisional_days", "Dias provisórios"),
        ("incomplete_days", "Dias incompletos"),
        ("unavailable_days", "Dias indisponíveis"),
    )

    def __init__(self, quality: Sequence[ReportMetric]) -> None:
        super().__init__()
        self._quality = tuple(quality)
        self._height = 14 * mm
        self._width = _CONTENT_WIDTH

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        self._width = availWidth
        return availWidth, self._height

    def draw(self) -> None:
        canvas = self.canv
        gap = 3 * mm
        width = (self._width - gap * 3) / 4
        for index, (key, label) in enumerate(self._KEYS):
            x = index * (width + gap)
            metric = _find(self._quality, key)
            number = _decimal(metric.value) if metric is not None else None
            if number is None:
                accent, fill, text = _MUTED, _SURFACE_SOFT, "—"
            elif number == 0:
                accent, fill, text = _GREEN, _GREEN_TINT, "0"
            else:
                accent, fill, text = (
                    _ORANGE,
                    colors.HexColor(theme.WARNING_HEX),
                    _number_br(number, 0),
                )
            canvas.setFillColor(fill)
            canvas.setStrokeColor(_BORDER)
            canvas.setLineWidth(0.6)
            canvas.roundRect(x, 0, width, self._height, 2 * mm, stroke=1, fill=1)
            canvas.setFillColor(accent)
            canvas.setFont(_BOLD, 15)
            canvas.drawString(x + 4 * mm, self._height / 2 - 2.2 * mm, text)
            canvas.setFillColor(_INK)
            canvas.setFont(_BOLD, 7)
            label_x = x + 4 * mm + stringWidth(text, _BOLD, 15) + 3 * mm
            canvas.drawString(label_x, self._height / 2 + 0.6 * mm, label)
            canvas.setFillColor(_MUTED)
            canvas.setFont(_REGULAR, 6.4)
            canvas.drawString(label_x, self._height / 2 - 2.6 * mm, "no ciclo")


def _actions_block(
    report: MonthlyEnergyReport, styles: dict[str, ParagraphStyle]
) -> list[Flowable]:
    flowables: list[Flowable] = []
    for diagnostic in report.diagnostics:
        flowables.extend([_diagnostic_card(diagnostic, styles), Spacer(1, 2.5 * mm)])
    if report.priority_actions:
        items: list[Flowable] = [Paragraph("<b>Ações prioritárias</b>", styles["card_title"])]
        items.extend(
            Paragraph(f"{index}. {_safe_text(action)}", styles["body"])
            for index, action in enumerate(report.priority_actions, start=1)
        )
        flowables.append(_callout(items, border=_NAVY, background=_SURFACE_SOFT))
    return flowables


def _trend_block(report: MonthlyEnergyReport, styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    trend = report.trend
    assert trend is not None
    rows: list[list[Flowable]] = []
    for metric in trend.metrics:
        unit = _TREND_UNIT_LABELS.get(metric.unit, metric.unit)
        delta = _decimal(metric.absolute_delta)
        places = (
            0
            if delta is not None
            and delta == delta.to_integral_value()
            and metric.unit == "score_points"
            else 2
        )
        delta_text = (
            f"{'+' if delta > 0 else ''}{_number_br(delta, places)} {unit}"
            if delta is not None
            else f"{metric.absolute_delta} {unit}"
        )
        percent = _decimal(metric.percent_delta) if metric.percent_delta else None
        percent_text = (
            f"{'+' if percent > 0 else ''}{_number_br(percent)}%" if percent is not None else "—"
        )
        rows.append(
            [
                _cell(metric.label, styles, strong=True),
                _cell(delta_text, styles),
                _cell(percent_text, styles),
                (
                    _Pill(_DIRECTION_LABELS[metric.direction], _NAVY_SOFT)
                    if metric.direction in ("UP", "DOWN", "STABLE")
                    else _cell("—", styles)
                ),
            ]
        )
    flowables: list[Flowable] = [
        _data_table(
            ("Indicador", "Variação", "Variação %", "Direção"),
            rows,
            widths=(
                _CONTENT_WIDTH * 0.38,
                _CONTENT_WIDTH * 0.24,
                _CONTENT_WIDTH * 0.18,
                _CONTENT_WIDTH * 0.20,
            ),
            styles=styles,
            center_columns=(3,),
        )
    ]
    for diagnostic in trend.diagnostics:
        flowables.extend([Spacer(1, 2.5 * mm), _diagnostic_card(diagnostic, styles)])
    return flowables


def _audit_unit(unit: str | None) -> str:
    if unit is None:
        return ""
    return _AUDIT_UNIT_LABELS.get(unit, unit)


def _audit_rows(
    metrics: Sequence[ReportMetric], styles: dict[str, ParagraphStyle]
) -> list[list[Flowable]]:
    return [
        [
            _cell(metric.label, styles, strong=True),
            _cell(
                (
                    f"{metric.value} {_audit_unit(metric.unit)}".strip()
                    if metric.value != ""
                    else "(indisponível)"
                ),
                styles,
            ),
            _cell(_NATURE_LABELS.get(metric.nature, metric.nature), styles),
            _cell(_SOURCE_LABELS.get(metric.source, metric.source), styles),
        ]
        for metric in metrics
    ]


def _audit_block(report: MonthlyEnergyReport, styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    widths = (
        _CONTENT_WIDTH * 0.34,
        _CONTENT_WIDTH * 0.19,
        _CONTENT_WIDTH * 0.23,
        _CONTENT_WIDTH * 0.24,
    )
    headers = ("Indicador", "Valor registrado", "Natureza", "Fonte")
    metadata = (
        ("Mês de referência", report.reference_month),
        ("Situação", report.status),
        ("Usina", str(report.plant_id)),
        ("Fatura", str(report.bill_id)),
        ("Versão do esquema", report.schema_version),
        ("Versão do cálculo", report.calculation_version),
    )
    return [
        Paragraph(
            "Valores exatos gravados no relatório deste ciclo, sem arredondamento, "
            "com a natureza e a origem de cada um.",
            styles["caption"],
        ),
        Spacer(1, 2.5 * mm),
        _data_table(headers, _audit_rows(report.metrics, styles), widths=widths, styles=styles),
        Spacer(1, 3 * mm),
        _data_table(
            ("Qualidade dos dados", "Valor registrado", "Natureza", "Fonte"),
            _audit_rows(report.quality, styles),
            widths=widths,
            styles=styles,
        ),
        Spacer(1, 3 * mm),
        _data_table(
            ("Registro", "Valor"),
            [
                [_cell(label, styles, strong=True), _cell(value, styles)]
                for label, value in metadata
            ],
            widths=(_CONTENT_WIDTH * 0.36, _CONTENT_WIDTH * 0.64),
            styles=styles,
        ),
    ]


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------


def _page_decorator(report: MonthlyEnergyReport) -> Callable[[Any, Any], None]:
    def draw_page(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setTitle(f"Mplacas - Relatório mensal {report.reference_month}")
        canvas.setAuthor("Mplacas")
        canvas.setSubject("Relatório mensal auditável de energia")

        if document.page > 1:
            canvas.setFillColor(_NAVY)
            canvas.setFont(_BOLD, 8)
            canvas.drawString(_CONTENT_LEFT, _PAGE_HEIGHT - 12 * mm, "MPlacas")
            canvas.drawRightString(
                _CONTENT_RIGHT,
                _PAGE_HEIGHT - 12 * mm,
                f"RELATÓRIO MENSAL · {_month_label(report.reference_month).upper()}",
            )
            canvas.setStrokeColor(_NAVY)
            canvas.setLineWidth(1)
            canvas.line(
                _CONTENT_LEFT, _PAGE_HEIGHT - 14 * mm, _CONTENT_RIGHT, _PAGE_HEIGHT - 14 * mm
            )

        canvas.setStrokeColor(_BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(_CONTENT_LEFT, 15 * mm, _CONTENT_RIGHT, 15 * mm)
        canvas.setFont(_REGULAR, 7)
        canvas.setFillColor(_MUTED)
        canvas.drawString(
            _CONTENT_LEFT,
            10.5 * mm,
            f"MPlacas  |  esquema {report.schema_version}  |  cálculo {report.calculation_version}",
        )
        canvas.drawRightString(_CONTENT_RIGHT, 10.5 * mm, f"Página {document.page}")
        canvas.restoreState()

    return draw_page


def build_monthly_report_pdf(report: MonthlyEnergyReport) -> bytes:
    """Render the audited monthly report without recalculating indicators."""

    output = io.BytesIO()
    styles = _styles()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=_MARGIN_X,
        leftMargin=_MARGIN_X,
        topMargin=19 * mm,
        bottomMargin=21 * mm,
        title=f"Mplacas - Relatório mensal {report.reference_month}",
        author="Mplacas",
        subject="Relatório mensal auditável de energia",
    )

    number = 0

    def section(title: str, note: str = "") -> Table:
        nonlocal number
        number += 1
        return _section(number, title, styles, note)

    gap = Spacer(1, 3 * mm)
    block_gap = Spacer(1, 6 * mm)
    story: list[Flowable] = [
        _header(styles),
        Spacer(1, 2.5 * mm),
        Paragraph(
            "Exportação auditável: este documento não recalcula indicadores — "
            "mostra os valores gravados no fechamento do ciclo.",
            styles["notice"],
        ),
        Spacer(1, 4 * mm),
        _identification(report, styles),
        block_gap,
        section("Síntese do ciclo"),
        gap,
        _callout(
            [Paragraph(_safe_text(report.headline), styles["headline"])],
            border=_BORDER,
            background=_SURFACE_SOFT,
        ),
        block_gap,
        section("Energia do ciclo", "Leituras do inversor e fatura confirmada"),
        gap,
        *_energy_section(report, styles),
        block_gap,
        section("Eficiência e saúde"),
        gap,
        *_efficiency_section(report),
        block_gap,
        KeepTogether(
            [
                section("Qualidade dos dados", "Dias do ciclo com leitura problemática"),
                gap,
                _QualityRow(report.quality),
            ]
        ),
    ]

    if report.diagnostics or report.priority_actions:
        story.extend(
            [block_gap, section("Diagnósticos e ações"), gap, *_actions_block(report, styles)]
        )

    if report.trend is not None:
        story.extend(
            [
                block_gap,
                section(
                    "Tendência entre ciclos",
                    f"De {_month_label(report.trend.previous_reference_month)} para "
                    f"{_month_label(report.trend.current_reference_month)}",
                ),
                gap,
                *_trend_block(report, styles),
            ]
        )

    story.extend([block_gap, section("Anexo de auditoria"), gap, *_audit_block(report, styles)])

    decorate = _page_decorator(report)
    document.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return output.getvalue()
