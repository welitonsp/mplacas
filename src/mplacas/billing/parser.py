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
    # CONSUMO SCEE kWh <qty> <tariff w/tax> <total> <base> <total> <pct>% <tax value>
    # <tariff w/o tax>
    "tariff_with_taxes_brl_kwh": (
        r"consumo scee kwh\s+[\d\.]+,\d+\s+([\d\.]+,\d+)",
    ),
    "tariff_without_taxes_brl_kwh": (
        r"consumo scee kwh\s+[\d\.]+,\d+\s+[\d\.]+,\d+\s+[\d\.]+,\d+\s+[\d\.]+,\d+\s+"
        r"[\d\.]+,\d+\s+\d+%\s+[\d\.]+,\d+\s+([\d\.]+,\d+)",
    ),
    # PARC INJET S/DESC - <pct>% - GD II <n> kWh <qty> <fio b tariff> ...
    "wire_b_tariff_brl_kwh": (
        r"parc injet[^k]*kwh\s+[\d\.]+,\d+\s+([\d\.]+,\d+)",
    ),
}

# SCEE four-date reading line: anterior atual dias próxima
_SCEE_READING_DATES_RE = re.compile(
    r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(\d{1,3})\s+\d{2}/\d{2}/\d{4}"
)

# --- Layout "segunda via" (Equatorial Goiás, a partir de set/2026) -----------
# No PDF baixado como segunda via, o pypdf devolve as colunas em outra ordem e
# sem separador entre algumas delas. Exemplos reais (texto normalizado):
#   "17/08/2026 15/09/2026 set/2026"            -> leitura anterior, atual, ref.
#   "16/10/202629 fornecimento"                 -> próxima leitura + nº de dias
#   "consumo scee kwh 0,787589221,00 5,51 174,06 19% 33,07 0,613030174,06"
#      preço c/ tributos (6 casas) GRUDADO na quantidade (2 casas), PIS/COFINS,
#      base ICMS, alíquota, ICMS, tarifa s/ tributos (6 casas) grudada no valor.
# Como os números vêm colados, a separação depende das casas decimais fixas.
# Por isso o resultado é conferido (preço × quantidade = base do ICMS; datas ×
# dias) e, se não fechar, a fatura é RECUSADA — nunca cai nos padrões
# genéricos, que leriam "0,787589221" como consumo.
# Rótulos das linhas de energia. Além do SCEE atual, a Equatorial já usou:
#   - até nov/2024 (antes da transição da Lei 14.300): "ENERGIA ATIVA
#     FORNECIDA" e "ENERGIA INJETADA", com as mesmas colunas coladas;
#   - dez/2024 a fev/2025: "INJEÇÃO SCEE" sem as colunas de imposto
#     (preço, quantidade, PIS/COFINS, tarifa s/ tributos colada no valor).
# Colunas de imposto podem vir com uma casa só ("8,8", "13,6"): a fatura corta
# o zero final, ou vir sem decimais ("2" para R$ 2,00). Preços e tarifas
# sempre têm 6 casas; quantidades sempre 2.
_GLUED_CONSUMPTION_LABEL = r"(?:consumo scee|energia ativa fornecida) kwh"
_GLUED_INJECTION_LABEL = r"(?:inje[cç][aã]o scee[^k]{0,40}|energia injetada) kwh"
_TAX = r"-?[\d\.]+(?:,\d{1,2})?"
_GLUED_LAYOUT_MARKER_RE = re.compile(_GLUED_CONSUMPTION_LABEL + r" -?\d+,\d{6}\d")
_GLUED_DATES_RE = re.compile(
    r"(\d{2}/\d{2}/\d{4}) (\d{2}/\d{2}/\d{4}) ([a-z]{3}/\d{4})"
)
_GLUED_DAYS_RE = re.compile(r"\d{2}/\d{2}/\d{4}(\d{1,3}) fornecimento")


def _glued_energy_line(label: str) -> re.Pattern[str]:
    # <preço c/ tributos><qtd> <PIS/COFINS> <base ICMS> <alíq>% <ICMS> <tarifa s/ tributos><valor>
    return re.compile(
        label + r" (\d+,\d{6})([\d\.]+,\d{2}) " + _TAX + r" ([\d\.]+(?:,\d{1,2})?) "
        r"\d+% " + _TAX + r" (\d+,\d{6})([\d\.]+,\d{1,2})(?![\d,])"
    )


_GLUED_CONSUMPTION_RE = _glued_energy_line(_GLUED_CONSUMPTION_LABEL)
# Energia que não foi coberta por crédito, cobrada à tarifa cheia. Soma no
# consumo da rede: sem ela, o consumo ficaria subestimado.
_GLUED_UNCOMPENSATED_RE = _glued_energy_line(r"consumo n[aã]o compensado kwh")
_GLUED_UNCOMPENSATED_LINE_RE = re.compile(r"consumo n[aã]o compensado kwh")
# Injeção completa: preço, quantidade, PIS/COFINS e base (negativa).
_GLUED_INJECTION_RE = re.compile(
    _GLUED_INJECTION_LABEL + r" (\d+,\d{6})([\d\.]+,\d{2}) " + _TAX + r" "
    r"-([\d\.]+,\d{1,2}) "
)
# Injeção curta (dez/2024 a fev/2025): preço, quantidade, PIS/COFINS e a
# tarifa s/ tributos colada no valor negativo da linha.
_GLUED_INJECTION_SHORT_RE = re.compile(
    _GLUED_INJECTION_LABEL + r" (\d+,\d{6})([\d\.]+,\d{2}) " + _TAX + r" "
    r"\d+,\d{6}-([\d\.]+,\d{2})(?![\d,])"
)
_GLUED_INJECTION_LINE_RE = re.compile(_GLUED_INJECTION_LABEL)
_GLUED_CONSUMPTION_LINE_RE = re.compile(_GLUED_CONSUMPTION_LABEL)
# Medidor de consumo: leitura atual, consumo do ciclo colado ao nº do medidor,
# leitura anterior. Confere o consumo lido nas linhas de energia.
# Sem sobreposição entre `\d+` e o resto do token (só pode seguir um caractere
# não numérico), para não haver backtracking polinomial em texto hostil.
_METER_READING_RE = re.compile(
    r"energia ativa - kwh (\d{4,6}) (\d+)(?:[^\s\d]\S*)? (\d{4,6})"
)
# Fio B: tarifa, quantidade, tarifa repetida e valor da linha (= tarifa × qtd).
_GLUED_WIRE_B_RE = re.compile(
    r"parc injet s/ ?desc[^k]{0,40}kwh (\d+,\d{6})([\d\.]+,\d{2}) "
    r"(\d+,\d{6})([\d\.]+,\d{2})(?![\d,])"
)
_GLUED_WIRE_B_LINE_RE = re.compile(r"parc injet s/ ?desc[^k]{0,40}kwh")
# Tolerância do produto preço × quantidade contra a base impressa: arredondamento
# de centavos da própria fatura.
_GLUED_PRODUCT_TOLERANCE_BRL = Decimal("0.02")
# Diferença máxima entre o consumo das linhas de energia e o do medidor: o
# medidor imprime kWh inteiros; as linhas, com centavos de kWh.
_METER_TOLERANCE_KWH = Decimal("1")
# Medidor novo: a fatura pode contar alguns dias a mais que o período impresso
# (dias desde a instalação). Mais que isso indica data mal lida.
_NEW_METER_MAX_EXTRA_DAYS = 3
_GLUED_LAYOUT_FIELDS = frozenset(
    {
        "reference_month",
        "cycle_start",
        "cycle_end",
        "billed_days",
        "imported_kwh",
        "injected_kwh",
        "compensated_kwh",
        "tariff_with_taxes_brl_kwh",
        "tariff_without_taxes_brl_kwh",
        "wire_b_tariff_brl_kwh",
    }
)

# "ADC BANDEIRA AMARELA kWh 0,01172182,02 …": o primeiro número com 6 casas
# depois de "kwh" é o preço com tributos (no layout colado vem grudado na
# quantidade, que tem 2 casas).
_FLAG_TARIFF_RE = re.compile(r"adc bandeira [a-z0-9 ]{3,30}?kwh\s+(\d+,\d{6})")
# Créditos que não vêm das placas: compensação por interrupção (DIC, FIC,
# DMIC, DICRI) e Bônus de Itaipu — sempre linhas com valor negativo.
_NON_ENERGY_CREDIT_RE = re.compile(
    r"(?:compensa[cç][aã]o de (?:dic|fic|dmic|dicri)\b.{0,30}?|bonus itaipu.{0,40}?)"
    r"\s(-[\d\.]+,\d{2})(?!\d)"
)
_SCEE_GENERATION_SHARE_RE = re.compile(
    r"cadastro rateio gera[cç][aã]o:\s*uc\s*[^\s=]+\s*=\s*(\d{1,3}(?:,\d{1,2})?)\s*%",
    re.IGNORECASE,
)
_SCEE_EXPIRING_30D_RE = re.compile(
    r"saldo a expirar em 30 dias kwh:\s*([\d\.]+,\d+)",
    re.IGNORECASE,
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

    # Campos que, no layout "segunda via", só podem vir do extrator dedicado:
    # os padrões genéricos leriam colunas coladas como um número só.
    layout_only: frozenset[str] = frozenset()
    if _GLUED_LAYOUT_MARKER_RE.search(normalized):
        values.update(_extract_glued_layout(normalized))
        layout_only = _GLUED_LAYOUT_FIELDS

    # SCEE reading-dates line (anterior atual dias próxima) gives start/end/days
    # from a single pattern. The "current" date is the meter-read date (exclusive),
    # so cycle_end = current_read - 1 day to keep inclusive domain semantics.
    scee_dates = None if layout_only else _extract_scee_reading_dates(normalized)
    if scee_dates:
        cycle_start, cycle_end, billed_days = scee_dates
        values["cycle_start"] = cycle_start.isoformat()
        values["cycle_end"] = cycle_end.isoformat()
        values["billed_days"] = str(billed_days)

    for field, patterns in _FIELD_PATTERNS.items():
        if field in values or field in layout_only:
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
        tariff_with_taxes_brl_kwh=_parse_optional_decimal(values.get("tariff_with_taxes_brl_kwh")),
        tariff_without_taxes_brl_kwh=_parse_optional_decimal(
            values.get("tariff_without_taxes_brl_kwh")
        ),
        wire_b_tariff_brl_kwh=_parse_optional_decimal(values.get("wire_b_tariff_brl_kwh")),
        generation_share_percent=_share_or_none(_extract_single_share(normalized)),
        credits_expiring_30d_kwh=_extract_optional(_SCEE_EXPIRING_30D_RE, normalized),
        flag_tariff_brl_kwh=_sum_flag_tariffs(normalized),
        non_energy_credits_brl=_sum_non_energy_credits(normalized),
    )
    bill.validate()
    return bill


def _extract_glued_layout(normalized: str) -> dict[str, str]:
    """Campos do layout "segunda via"; recusa (BillParseError) se algo não fechar.

    Cada número separado pelas casas decimais é conferido contra outro número
    impresso na mesma fatura. Em billing, recusar é sempre preferível a gravar
    um valor plausível porém errado.
    """
    # Uma única linha de consumo e uma de injeção: com mais de uma (postos
    # tarifários, GD I + GD II), ler só a primeira subestimaria o total.
    if len(_GLUED_CONSUMPTION_LINE_RE.findall(normalized)) != 1:
        raise BillParseError("second-copy layout must have exactly one consumption line")
    if len(_GLUED_INJECTION_LINE_RE.findall(normalized)) != 1:
        raise BillParseError("second-copy layout must have exactly one injection line")
    if len(_GLUED_UNCOMPENSATED_LINE_RE.findall(normalized)) > 1:
        raise BillParseError("second-copy layout has more than one uncompensated line")

    dates = _GLUED_DATES_RE.search(normalized)
    days = _GLUED_DAYS_RE.search(normalized)
    consumption = _GLUED_CONSUMPTION_RE.search(normalized)
    injection = _GLUED_INJECTION_RE.search(normalized) or _GLUED_INJECTION_SHORT_RE.search(
        normalized
    )
    if not (dates and days and consumption and injection):
        raise BillParseError("second-copy layout detected but mandatory columns not found")

    # O medidor é obrigatório: é ele que garante que nenhuma linha de consumo
    # (ex.: "CONSUMO NÃO COMPENSADO") ficou de fora do texto extraído.
    meter = _read_meter(normalized)
    if meter is None:
        raise BillParseError("second-copy layout meter reading not found")

    try:
        start = datetime.strptime(dates.group(1), "%d/%m/%Y").date()
        reading_date = datetime.strptime(dates.group(2), "%d/%m/%Y").date()
    except ValueError as exc:
        raise BillParseError("second-copy layout has invalid reading dates") from exc
    billed_days = int(days.group(1))
    if (reading_date - start).days != billed_days:
        # Única exceção: primeiro ciclo de um medidor novo (leitura anterior
        # zerada). A distribuidora conta os dias desde a instalação, que pode
        # cair fora do período impresso; as datas impressas continuam valendo.
        divergence = billed_days - (reading_date - start).days
        if meter[1] != 0 or not 0 < divergence <= _NEW_METER_MAX_EXTRA_DAYS:
            raise BillParseError("second-copy layout reading dates do not match billed days")
        billed_days = (reading_date - start).days
    cycle_end = reading_date - timedelta(days=1)

    # O mês de referência impresso precisa ser o do fim do ciclo ou o da
    # leitura atual; outro mês/ano gravaria a fatura no ciclo errado.
    reference_month = _parse_reference_month_scee(dates.group(3))
    allowed_months = {cycle_end.strftime("%Y-%m"), reading_date.strftime("%Y-%m")}
    if reference_month not in allowed_months:
        raise BillParseError("second-copy layout reference month does not match reading dates")

    compensated_quantity = _checked_energy_line(consumption, "consumption")

    injection_price = _parse_decimal(injection.group(1))
    injection_quantity = _parse_decimal(injection.group(2))
    injection_base = _parse_decimal(injection.group(3))
    if abs(injection_price * injection_quantity - injection_base) > _GLUED_PRODUCT_TOLERANCE_BRL:
        raise BillParseError("second-copy layout injection columns are inconsistent")

    imported = compensated_quantity
    if _GLUED_UNCOMPENSATED_LINE_RE.search(normalized):
        uncompensated = _GLUED_UNCOMPENSATED_RE.search(normalized)
        if not uncompensated:
            raise BillParseError("second-copy layout uncompensated line could not be read safely")
        imported += _checked_energy_line(uncompensated, "uncompensated")

    # O medidor imprime o consumo do ciclo: as linhas de energia têm de somar
    # o mesmo. Se não somarem, falta (ou sobra) alguma linha de consumo.
    if abs(imported - meter[0]) > _METER_TOLERANCE_KWH:
        raise BillParseError("second-copy layout energy lines do not match the meter reading")
    if _parse_decimal(injection.group(2)) > imported:
        raise BillParseError("second-copy layout compensated energy exceeds consumption")

    values = {
        "reference_month": dates.group(3),
        "cycle_start": start.isoformat(),
        "cycle_end": cycle_end.isoformat(),
        "billed_days": str(billed_days),
        "imported_kwh": f"{imported:.2f}".replace(".", ","),
        "injected_kwh": injection.group(2),
        # Crédito efetivamente usado no ciclo = quantidade da linha de injeção
        # (no SCEE, igual à do consumo compensado; até nov/2024, menor que o
        # consumo fornecido, que inclui o custo de disponibilidade).
        "compensated_kwh": injection.group(2),
        "tariff_with_taxes_brl_kwh": consumption.group(1),
        "tariff_without_taxes_brl_kwh": consumption.group(4),
    }

    # Fio B é opcional, mas se a linha existe ela tem de ser lida e conferida —
    # nunca deixada para os padrões genéricos nem ignorada em silêncio.
    if _GLUED_WIRE_B_LINE_RE.search(normalized):
        wire_b = _GLUED_WIRE_B_RE.search(normalized)
        if not wire_b or wire_b.group(1) != wire_b.group(3):
            raise BillParseError("second-copy layout wire B line could not be read safely")
        wire_rate = _parse_decimal(wire_b.group(1))
        wire_quantity = _parse_decimal(wire_b.group(2))
        wire_value = _parse_decimal(wire_b.group(4))
        if abs(wire_rate * wire_quantity - wire_value) > _GLUED_PRODUCT_TOLERANCE_BRL:
            raise BillParseError("second-copy layout wire B columns are inconsistent")
        values["wire_b_tariff_brl_kwh"] = wire_b.group(1)
    return values


def _checked_energy_line(match: re.Match[str], name: str) -> Decimal:
    """Quantidade da linha, conferida: preço × quantidade = base = valor."""
    price = _parse_decimal(match.group(1))
    quantity = _parse_decimal(match.group(2))
    icms_base = _parse_decimal(match.group(3))
    line_value = _parse_decimal(match.group(5))
    if abs(price * quantity - icms_base) > _GLUED_PRODUCT_TOLERANCE_BRL or line_value != icms_base:
        raise BillParseError(f"second-copy layout {name} columns are inconsistent")
    return quantity


def _read_meter(normalized: str) -> tuple[Decimal, int] | None:
    """(consumo do ciclo, leitura anterior) do medidor de consumo, se impresso.

    O consumo vem colado ao número do medidor ("14913580245-8"), então ele é
    calculado pelas leituras e só aceito se o texto colado começar por ele.
    """
    found = _METER_READING_RE.search(normalized)
    if not found:
        return None
    current, previous = int(found.group(1)), int(found.group(3))
    consumed = current - previous
    if consumed < 0 or not found.group(2).startswith(str(consumed)):
        raise BillParseError("second-copy layout meter reading could not be read safely")
    return Decimal(consumed), previous


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


def _extract_optional(pattern: re.Pattern[str], normalized: str) -> Decimal | None:
    """Campo informativo do bloco SCEE: ausente ou ilegível vira `None`."""
    m = pattern.search(normalized)
    if not m:
        return None
    try:
        return _parse_decimal(m.group(1))
    except BillParseError:
        return None


def _sum_flag_tariffs(normalized: str) -> Decimal | None:
    """Bandeira do ciclo (preço com tributos de UMA linha "ADC BANDEIRA").

    Com duas cores no ciclo, não há fatura real que mostre se cada linha traz
    o preço cheio da cor (com a quantidade pró-rata) ou o preço pró-rata —
    somar poderia inflar a economia. Até haver essa fatura, mais de uma linha
    vira `None` (falha fechada: a economia fica no piso). Valor implausível
    também vira `None` (campo informativo, não recusa a fatura).
    """
    try:
        prices = [_parse_decimal(found) for found in _FLAG_TARIFF_RE.findall(normalized)]
    except BillParseError:
        return None
    if len(prices) != 1 or normalized.count("adc bandeira") != 1:
        return None
    total = prices[0]
    if not (Decimal("0") < total <= Decimal("0.5")):
        return None
    return total


def _sum_non_energy_credits(normalized: str) -> Decimal | None:
    try:
        values = [_parse_decimal(found[1:]) for found in _NON_ENERGY_CREDIT_RE.findall(normalized)]
    except BillParseError:
        return None
    if not values:
        return None
    return sum(values, Decimal("0"))


def _extract_single_share(normalized: str) -> Decimal | None:
    """Rateio desta fatura: exige UMA linha só. Com várias UCs no rateio não
    dá para saber qual percentual é desta unidade — `None`, nunca um palpite."""
    found = _SCEE_GENERATION_SHARE_RE.findall(normalized)
    # Conta as linhas de rateio por um padrão frouxo: uma linha ilegível ao
    # lado de outra legível também é "várias UCs".
    if len(found) != 1 or normalized.count("cadastro rateio") != 1:
        return None
    try:
        return _parse_decimal(found[0])
    except BillParseError:
        return None


def _share_or_none(value: Decimal | None) -> Decimal | None:
    # Campo informativo: um percentual impossível não recusa a fatura inteira.
    if value is None or not (Decimal("0") <= value <= Decimal("100")):
        return None
    return value


def _parse_optional_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    return _parse_decimal(value)


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
