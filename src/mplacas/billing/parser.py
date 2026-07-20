from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from mplacas.billing.models import UtilityBill


class BillParseError(ValueError):
    """Raised when mandatory bill fields cannot be extracted safely."""


_MONTH_PT_BR: dict[str, str] = {
    "jan": "01", "fev": "02", "mar": "03", "abr": "04",
    "mai": "05", "jun": "06", "jul": "07", "ago": "08",
    "set": "09", "out": "10", "nov": "11", "dez": "12",
}

# Patterns ordered SCEE-first, generic fallback last.
_FIELD_PATTERNS: dict[str, tuple[str, ...]] = {
    "reference_month": (
        r"ref:\s*m[eê]s/ano\s+([a-z]{3}/\d{4})",
        r"(?:refer[eê]ncia|m[eê]s de refer[eê]ncia)\s*[:\-]?\s*(\d{2}/\d{4})",
    ),
    "cycle_start": (
        r"(?:leitura anterior|in[ií]cio do ciclo)\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
    ),
    "cycle_end": (
        r"(?:leitura atual|fim do ciclo)\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
    ),
    "billed_days": (
        r"(?:dias faturados|dias de consumo)\s*[:\-]?\s*(\d{1,3})",
    ),
    "imported_kwh": (
        r"consumo scee kwh\s+([\d\.]+,\d+)",
        r"(?:energia ativa consumida|consumo medido|energia importada)\s*[:\-]?\s*"
        r"([\d\.]+(?:,\d+)?)\s*kwh",
    ),
    "injected_kwh": (
        r"inje[cç][aã]o scee[^k]*kwh\s+([\d\.]+,\d+)",
        r"(?:energia injetada|gera[cç][aã]o injetada)\s*[:\-]?\s*([\d\.]+(?:,\d+)?)\s*kwh",
    ),
    "compensated_kwh": (
        r"(?:energia compensada|cr[eé]ditos utilizados)\s*[:\-]?\s*([\d\.]+(?:,\d+)?)\s*kwh",
    ),
    "credit_balance_kwh": (
        r"saldo kwh:\s*([\d\.]+,\d+)",
        r"(?:saldo de cr[eé]ditos|cr[eé]dito acumulado)\s*[:\-]?\s*([\d\.]+(?:,\d+)?)\s*kwh",
    ),
    "total_amount_brl": (
        r"r\$\*+([\d\.]+,\d+)",
        r"(?:total a pagar|valor total)\s*[:\-]?\s*r?\$?\s*([\d\.]+(?:,\d+)?)",
    ),
    "public_lighting_brl": (
        r"contrib\.\s+ilum\.\s+p[uú]blica\s*[-–]\s*municipal\s+([\d\.]+,\d+)",
        r"(?:contribui[cç][aã]o de ilumina[cç][aã]o p[uú]blica|"
        r"custeio de ilumina[cç][aã]o p[uú]blica|cip)\s*[:\-]?\s*r?\$?\s*"
        r"([\d\.]+(?:,\d+)?)",
    ),
}

# SCEE four-date reading line: anterior atual dias próxima
_SCEE_READING_DATES_RE = re.compile(
    r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(\d{1,3})\s+\d{2}/\d{2}/\d{4}"
)

_SCEE_GENERATION_CYCLE_RE = re.compile(
    r"gera[cç][aã]o\s+ciclo\s*\(\d+/\d+\)\s+kwh:\s*uc[^:]+:\s*([\d\.]+,\d+)",
    re.IGNORECASE,
)


def parse_equatorial_bill_text(text: str) -> UtilityBill:
    """Parse normalized text extracted from an Equatorial Goiás bill.

    The parser is intentionally deterministic. Missing mandatory fields fail closed,
    so no financial record is silently invented or consolidated.
    """
    normalized = " ".join(text.casefold().split())
    if "equatorial" not in normalized:
        raise BillParseError("document is not identified as an Equatorial bill")

    values: dict[str, str] = {}

    # SCEE reading-dates line (anterior atual dias próxima) gives start/end/days
    # from a single pattern. The "current" date is the meter-read date (exclusive),
    # so cycle_end = current_read - 1 day to keep inclusive domain semantics.
    scee_dates = _extract_scee_reading_dates(normalized)
    if scee_dates:
        cycle_start, cycle_end, billed_days = scee_dates
        values["cycle_start"] = cycle_start.isoformat()
        values["cycle_end"] = cycle_end.isoformat()
        values["billed_days"] = str(billed_days)

    for field, patterns in _FIELD_PATTERNS.items():
        if field in values:
            continue
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
    # In SCEE billing, compensated energy equals imported energy (credits cover 100%
    # of grid consumption). Derive it when the generic pattern finds no label.
    if "compensated_kwh" not in values and "imported_kwh" in values:
        values["compensated_kwh"] = values["imported_kwh"]

    missing = sorted(required - values.keys())
    if missing:
        raise BillParseError(f"mandatory fields missing: {', '.join(missing)}")

    ref_raw = values["reference_month"]
    if re.match(r"[a-z]{3}/\d{4}", ref_raw):
        reference_month = _parse_reference_month_scee(ref_raw)
    else:
        reference_month = datetime.strptime(ref_raw, "%m/%Y").strftime("%Y-%m")

    bill = UtilityBill(
        distributor="EQUATORIAL_GO",
        reference_month=reference_month,
        cycle_start=_parse_date(values["cycle_start"]),
        cycle_end=_parse_date(values["cycle_end"]),
        billed_days=int(values["billed_days"]),
        imported_kwh=_parse_decimal(values["imported_kwh"]),
        injected_kwh=_parse_decimal(values["injected_kwh"]),
        compensated_kwh=_parse_decimal(values["compensated_kwh"]),
        credit_balance_kwh=_parse_decimal(values["credit_balance_kwh"]),
        total_amount_brl=_parse_decimal(values["total_amount_brl"]),
        public_lighting_brl=_parse_decimal(values.get("public_lighting_brl", "0")),
        generation_cycle_kwh=_extract_generation_cycle_kwh(normalized),
    )
    bill.validate()
    return bill


def _extract_scee_reading_dates(normalized: str) -> tuple[date, date, int] | None:
    m = _SCEE_READING_DATES_RE.search(normalized)
    if not m:
        return None
    try:
        start = datetime.strptime(m.group(1), "%d/%m/%Y").date()
        reading_date = datetime.strptime(m.group(2), "%d/%m/%Y").date()
        billed_days = int(m.group(3))
    except ValueError:
        return None
    cycle_end = reading_date - timedelta(days=1)
    if (cycle_end - start).days + 1 != billed_days:
        return None
    return start, cycle_end, billed_days


def _extract_generation_cycle_kwh(normalized: str) -> Decimal | None:
    m = _SCEE_GENERATION_CYCLE_RE.search(normalized)
    if not m:
        return None
    try:
        return _parse_decimal(m.group(1))
    except BillParseError:
        return None


def _parse_reference_month_scee(raw: str) -> str:
    parts = raw.split("/")
    if len(parts) != 2:
        raise BillParseError(f"unrecognised SCEE reference month: {raw!r}")
    month_abbr, year = parts[0], parts[1]
    month_num = _MONTH_PT_BR.get(month_abbr)
    if month_num is None:
        raise BillParseError(f"unknown Portuguese month abbreviation: {month_abbr!r}")
    return f"{year}-{month_num}"


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return datetime.strptime(value, "%d/%m/%Y").date()


def _parse_decimal(value: str) -> Decimal:
    normalized = value.replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise BillParseError("invalid numeric field") from exc
