from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from mplacas.billing.models import UtilityBill


class BillParseError(ValueError):
    """Raised when mandatory bill fields cannot be extracted safely."""


_FIELD_PATTERNS: dict[str, tuple[str, ...]] = {
    "reference_month": (r"(?:refer[eê]ncia|m[eê]s de refer[eê]ncia)\s*[:\-]?\s*(\d{2}/\d{4})",),
    "cycle_start": (r"(?:leitura anterior|in[ií]cio do ciclo)\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",),
    "cycle_end": (r"(?:leitura atual|fim do ciclo)\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",),
    "billed_days": (r"(?:dias faturados|dias de consumo)\s*[:\-]?\s*(\d{1,3})",),
    "imported_kwh": (
        r"(?:energia ativa consumida|consumo medido|energia importada)\s*[:\-]?\s*"
        r"([\d\.]+(?:,\d+)?)\s*kwh",
    ),
    "injected_kwh": (
        r"(?:energia injetada|gera[cç][aã]o injetada)\s*[:\-]?\s*([\d\.]+(?:,\d+)?)\s*kwh",
    ),
    "compensated_kwh": (
        r"(?:energia compensada|cr[eé]ditos utilizados)\s*[:\-]?\s*([\d\.]+(?:,\d+)?)\s*kwh",
    ),
    "credit_balance_kwh": (
        r"(?:saldo de cr[eé]ditos|cr[eé]dito acumulado)\s*[:\-]?\s*([\d\.]+(?:,\d+)?)\s*kwh",
    ),
    "total_amount_brl": (r"(?:total a pagar|valor total)\s*[:\-]?\s*r?\$?\s*([\d\.]+(?:,\d+)?)",),
    "public_lighting_brl": (
        r"(?:contribui[cç][aã]o de ilumina[cç][aã]o p[uú]blica|"
        r"custeio de ilumina[cç][aã]o p[uú]blica|cip)\s*[:\-]?\s*r?\$?\s*"
        r"([\d\.]+(?:,\d+)?)",
    ),
}


def parse_equatorial_bill_text(text: str) -> UtilityBill:
    """Parse normalized text extracted from an Equatorial Goiás bill.

    The parser is intentionally deterministic. Missing mandatory fields fail closed,
    so no financial record is silently invented or consolidated.
    """
    normalized = " ".join(text.casefold().split())
    if "equatorial" not in normalized:
        raise BillParseError("document is not identified as an Equatorial bill")

    values: dict[str, str] = {}
    for field, patterns in _FIELD_PATTERNS.items():
        match = next(
            (
                found
                for pattern in patterns
                if (found := re.search(pattern, normalized, flags=re.IGNORECASE))
            ),
            None,
        )
        if match:
            values[field] = match.group(1)

    required = {
        "reference_month",
        "cycle_start",
        "cycle_end",
        "billed_days",
        "imported_kwh",
        "injected_kwh",
        "compensated_kwh",
        "credit_balance_kwh",
        "total_amount_brl",
    }
    missing = sorted(required - values.keys())
    if missing:
        raise BillParseError(f"mandatory fields missing: {', '.join(missing)}")

    reference = datetime.strptime(values["reference_month"], "%m/%Y")
    bill = UtilityBill(
        distributor="EQUATORIAL_GO",
        reference_month=reference.strftime("%Y-%m"),
        cycle_start=datetime.strptime(values["cycle_start"], "%d/%m/%Y").date(),
        cycle_end=datetime.strptime(values["cycle_end"], "%d/%m/%Y").date(),
        billed_days=int(values["billed_days"]),
        imported_kwh=_parse_decimal(values["imported_kwh"]),
        injected_kwh=_parse_decimal(values["injected_kwh"]),
        compensated_kwh=_parse_decimal(values["compensated_kwh"]),
        credit_balance_kwh=_parse_decimal(values["credit_balance_kwh"]),
        total_amount_brl=_parse_decimal(values["total_amount_brl"]),
        public_lighting_brl=_parse_decimal(values.get("public_lighting_brl", "0")),
    )
    bill.validate()
    return bill


def _parse_decimal(value: str) -> Decimal:
    normalized = value.replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise BillParseError("invalid numeric field") from exc
