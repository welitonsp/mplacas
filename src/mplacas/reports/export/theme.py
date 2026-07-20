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
