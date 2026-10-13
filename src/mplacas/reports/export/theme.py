"""Paleta de cores e mapeamento de severidade compartilhados pelos renderizadores."""
from __future__ import annotations

NAVY_HEX = "#17324D"
LIGHT_BLUE_HEX = "#EAF2F8"
LIGHT_GRAY_HEX = "#F4F6F7"
MID_GRAY_HEX = "#667085"
DARK_HEX = "#1F2937"
WHITE_HEX = "#FFFFFF"

INFO_HEX = "#EAF2F8"
WARNING_HEX = "#FFF8E1"
CRITICAL_HEX = "#FDECEC"
HEALTHY_HEX = "#EAF7EF"

INFO_FONT_HEX = "#1F2937"
WARNING_FONT_HEX = "#9A6700"
CRITICAL_FONT_HEX = "#B42318"
HEALTHY_FONT_HEX = "#26734D"

INFO_BORDER_HEX = "#CBD5E1"
WARNING_BORDER_HEX = "#E5C07B"
CRITICAL_BORDER_HEX = "#F2A7A0"
HEALTHY_BORDER_HEX = "#9ED5B4"

# Linguagem visual do PDF mensal (2026-10). Duas cores de marca com papel
# fixo: verde = energia efetivamente produzida/aproveitada; marinho = estrutura,
# referência e o que veio da rede. Laranja/vermelho ficam reservados a sinais
# de atenção — nunca decoração.
REPORT_GREEN_HEX = "#009C77"
REPORT_GREEN_TINT_HEX = "#DFF2ED"
REPORT_NAVY_HEX = "#00406E"
REPORT_NAVY_SOFT_HEX = "#547F9E"
REPORT_INK_HEX = "#16324F"
REPORT_MUTED_HEX = "#5B6B7C"
REPORT_SURFACE_HEX = "#F2F6FA"
REPORT_SURFACE_SOFT_HEX = "#FAFCFE"
REPORT_BORDER_HEX = "#DBE3EC"
REPORT_TRACK_HEX = "#EEF2F7"
REPORT_ORANGE_HEX = "#E6851F"
REPORT_RED_HEX = "#D64545"


def severity_token(severity: str) -> str:
    """Normalize a severity label to a canonical token for format/style lookups."""
    normalized = severity.upper()
    if normalized in {"CRITICAL", "ERROR"}:
        return "critical"
    if normalized in {"WARNING", "WARN"}:
        return "warning"
    if normalized in {"HEALTHY", "SUCCESS"}:
        return "healthy"
    return "info"
