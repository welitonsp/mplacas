"""Leitura tolerante do cadastro que a marca informa (ADR-093 § 7).

Diferente da produção (onde campo estranho é erro), aqui o cadastro é um
"bônus": valor ausente, vazio ou implausível vira ``None`` e a usina segue
sem ele. Nada aqui inventa valor.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")
# Faixa plausível de potência de uma usina acompanhada pelo MPlacas.
_MIN_KWP = Decimal("0.1")
_MAX_KWP = Decimal("10000")
# A Growatt guarda a potência em W (ex.: 5400). Valor pequeno demais para W
# (ex.: 5.4) é lido como kW: ninguém cadastra uma usina de 5,4 W.
_WATTS_THRESHOLD = Decimal("100")


def _number(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    elif isinstance(value, str):
        match = _NUMBER.search(value)
        if match is None:
            return None
        text = match.group(0).replace(",", ".")
    else:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def parse_text(value: Any, *, max_length: int = 120) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text[:max_length] or None


def parse_kwp(value: Any, *, unit: str = "auto") -> Decimal | None:
    """Potência em kWp. ``unit="W"`` quando a marca tem unidade fixa em W (Growatt);
    ``"kW"`` quando fixa em kW; ``"auto"`` só para fontes sem unidade conhecida."""
    number = _number(value)
    if number is None or number <= 0:
        return None
    if unit == "W":
        kwp = number / 1000
    elif unit == "kW":
        kwp = number
    else:
        kwp = number / 1000 if number >= _WATTS_THRESHOLD else number
    if not _MIN_KWP <= kwp <= _MAX_KWP:
        return None
    return kwp.quantize(Decimal("0.001"))


def parse_coordinate(value: Any, *, limit: int) -> Decimal | None:
    number = _number(value)
    if number is None or abs(number) > limit or number == 0:
        # 0,0 é o "não preenchido" mais comum dos apps; nenhuma usina fica lá.
        return None
    return number.quantize(Decimal("0.000001"))


def parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()[:19]
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(text if " " in fmt else text[:10], fmt).date()
        except ValueError:
            continue
        if date(2000, 1, 1) <= parsed <= date.today():
            return parsed
        return None
    return None
