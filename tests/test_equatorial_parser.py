from decimal import Decimal

import pytest

from mplacas.billing.parser import BillParseError, parse_equatorial_bill_text


SYNTHETIC_BILL_TEXT = """
Equatorial Energia Goiás
Referência: 06/2026
Leitura anterior: 18/05/2026
Leitura atual: 16/06/2026
Dias faturados: 30
Energia ativa consumida: 278,000 kWh
Energia injetada: 182,000 kWh
Energia compensada: 278,000 kWh
Saldo de créditos: 63,980 kWh
Contribuição de iluminação pública: R$ 30,21
Total a pagar: R$ 80,21
"""

# Anonymised reproduction of the real SCEE Equatorial Goiás layout (June/2026).
# UC number, subscriber name and CPF replaced with placeholders.
REAL_SCEE_BILL_TEXT = """
Equatorial Goiás
Unidade Consumidora: UC XXXXXXXXXXX
Ref: Mês/Ano  jun/2026
18/05/2026 17/06/2026 30 17/07/2026
CONSUMO SCEE KWH 278,00 R$ 0,00
INJEÇÃO SCEE - GD II 2 KWH 278,00 R$ 0,00
SALDO KWH: 63,98
GERAÇÃO CICLO (6/2026) KWH: UC XXXXXXXXXXX: 182,00
CONTRIB. ILUM. PÚBLICA - MUNICIPAL 30,21
R$**********80,21
"""

# Anonymised reproduction of the real SCEE Equatorial Goiás layout including the
# full tariff columns (unit price with/without taxes, Fio B rate) as printed on
# the three real production bills (mai/jun/jul 2026).
_REAL_SCEE_BILL_WITH_TARIFF_TEMPLATE = """
Equatorial Goiás
Unidade Consumidora: UC XXXXXXXXXXX
Ref: Mês/Ano  {month}/2026
{cycle_start} {reading_date} {billed_days} 17/{next_month}/2026
CONSUMO SCEE KWH 278,00 {with_taxes} 222,14 9,51 222,14 19% 42,21 {without_taxes}
INJEÇÃO SCEE - GD II 2 KWH 278,00 R$ 0,00
PARC INJET S/DESC - 28,57% - GD II 2 KWH 278,00 {wire_b} 48,69 {wire_b}
SALDO KWH: 63,98
CONTRIB. ILUM. PÚBLICA - MUNICIPAL 30,21
R$**********80,21
"""

# Real values from the three confirmed production bills.
REAL_TARIFF_CASES = [
    # (month, cycle_start, reading_date, billed_days, next_month, with_taxes)
    ("mai", "18/04/2026", "18/05/2026", "30", "06", "0,774023"),
    ("jun", "18/05/2026", "17/06/2026", "30", "07", "0,799059"),
    ("jul", "17/06/2026", "17/07/2026", "30", "08", "0,814841"),
]
REAL_WITHOUT_TAXES = "0,613030"
REAL_WIRE_B = "0,175126"


def _real_scee_bill_with_tariff_text(
    *, month: str, cycle_start: str, reading_date: str, billed_days: str, next_month: str,
    with_taxes: str,
) -> str:
    return _REAL_SCEE_BILL_WITH_TARIFF_TEMPLATE.format(
        month=month,
        cycle_start=cycle_start,
        reading_date=reading_date,
        billed_days=billed_days,
        next_month=next_month,
        with_taxes=with_taxes,
        without_taxes=REAL_WITHOUT_TAXES,
        wire_b=REAL_WIRE_B,
    )


# ---------------------------------------------------------------------------
# Tests for the SYNTHETIC layout (existing, must not regress)
# ---------------------------------------------------------------------------


def test_parser_extracts_anonimized_equatorial_bill() -> None:
    bill = parse_equatorial_bill_text(SYNTHETIC_BILL_TEXT)
    assert bill.reference_month == "2026-06"
    assert bill.billed_days == 30
    assert bill.imported_kwh == Decimal("278.000")
    assert bill.injected_kwh == Decimal("182.000")
    assert bill.credit_balance_kwh == Decimal("63.980")
    assert bill.total_amount_brl == Decimal("80.21")
    assert bill.public_lighting_brl == Decimal("30.21")
    assert bill.generation_cycle_kwh is None
    assert bill.tariff_with_taxes_brl_kwh is None
    assert bill.tariff_without_taxes_brl_kwh is None
    assert bill.wire_b_tariff_brl_kwh is None


def test_parser_fails_closed_when_mandatory_field_is_missing() -> None:
    text = SYNTHETIC_BILL_TEXT.replace("Energia injetada: 182,000 kWh", "")
    with pytest.raises(BillParseError, match="injected_kwh"):
        parse_equatorial_bill_text(text)


def test_parser_rejects_unidentified_distributor() -> None:
    with pytest.raises(BillParseError, match="not identified"):
        parse_equatorial_bill_text(SYNTHETIC_BILL_TEXT.replace("Equatorial", "Distribuidora X"))


# ---------------------------------------------------------------------------
# Tests for the real SCEE layout
# ---------------------------------------------------------------------------


def test_scee_parser_extracts_all_mandatory_fields() -> None:
    bill = parse_equatorial_bill_text(REAL_SCEE_BILL_TEXT)
    assert bill.reference_month == "2026-06"
    assert bill.cycle_start.isoformat() == "2026-05-18"
    # reading date 17/06 is exclusive; domain stores inclusive end = 16/06
    assert bill.cycle_end.isoformat() == "2026-06-16"
    assert bill.billed_days == 30
    assert bill.imported_kwh == Decimal("278.00")
    assert bill.injected_kwh == Decimal("278.00")
    assert bill.compensated_kwh == Decimal("278.00")
    assert bill.credit_balance_kwh == Decimal("63.98")
    assert bill.total_amount_brl == Decimal("80.21")
    assert bill.public_lighting_brl == Decimal("30.21")


def test_scee_parser_extracts_generation_cycle_kwh() -> None:
    bill = parse_equatorial_bill_text(REAL_SCEE_BILL_TEXT)
    assert bill.generation_cycle_kwh == Decimal("182.00")


def test_scee_parser_absent_generation_cycle_is_none() -> None:
    text = REAL_SCEE_BILL_TEXT.replace("GERAÇÃO CICLO (6/2026) KWH: UC XXXXXXXXXXX: 182,00", "")
    bill = parse_equatorial_bill_text(text)
    assert bill.generation_cycle_kwh is None


def test_scee_parser_invalid_month_abbreviation_fails_closed() -> None:
    text = REAL_SCEE_BILL_TEXT.replace("jun/2026", "xyz/2026")
    with pytest.raises(BillParseError, match="month abbreviation"):
        parse_equatorial_bill_text(text)


def test_scee_parser_masked_total_is_parsed_correctly() -> None:
    bill = parse_equatorial_bill_text(REAL_SCEE_BILL_TEXT)
    assert bill.total_amount_brl == Decimal("80.21")


def test_scee_parser_absent_tariff_fields_are_none() -> None:
    """Regression: the fallback/older SCEE fixture (no tariff columns) must not break."""
    bill = parse_equatorial_bill_text(REAL_SCEE_BILL_TEXT)
    assert bill.tariff_with_taxes_brl_kwh is None
    assert bill.tariff_without_taxes_brl_kwh is None
    assert bill.wire_b_tariff_brl_kwh is None


# ---------------------------------------------------------------------------
# Tests for tariff extraction against the three real production bills
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("month", "cycle_start", "reading_date", "billed_days", "next_month", "with_taxes"),
    REAL_TARIFF_CASES,
)
def test_scee_parser_extracts_real_tariff_fields(
    month: str,
    cycle_start: str,
    reading_date: str,
    billed_days: str,
    next_month: str,
    with_taxes: str,
) -> None:
    text = _real_scee_bill_with_tariff_text(
        month=month,
        cycle_start=cycle_start,
        reading_date=reading_date,
        billed_days=billed_days,
        next_month=next_month,
        with_taxes=with_taxes,
    )
    bill = parse_equatorial_bill_text(text)
    assert bill.tariff_with_taxes_brl_kwh == Decimal(with_taxes.replace(",", "."))
    assert bill.tariff_without_taxes_brl_kwh == Decimal(REAL_WITHOUT_TAXES.replace(",", "."))
    assert bill.wire_b_tariff_brl_kwh == Decimal(REAL_WIRE_B.replace(",", "."))


def test_scee_parser_tariff_fields_do_not_break_mandatory_field_extraction() -> None:
    text = _real_scee_bill_with_tariff_text(
        month="jun",
        cycle_start="18/05/2026",
        reading_date="17/06/2026",
        billed_days="30",
        next_month="07",
        with_taxes="0,799059",
    )
    bill = parse_equatorial_bill_text(text)
    assert bill.imported_kwh == Decimal("278.00")
    assert bill.injected_kwh == Decimal("278.00")


# ---------------------------------------------------------------------------
# End-to-end guard against the ordinal-position failure mode (ADR-056)
# ---------------------------------------------------------------------------


def test_shifted_wire_b_column_is_rejected_at_intake_not_persisted() -> None:
    """A layout shift must fail closed instead of persisting a monetary total.

    The tariff patterns are anchored by ordinal column position, so if the
    distributor drops the quantity column the ``wire_b_tariff_brl_kwh`` pattern
    silently captures the line's R$ total (48,69) instead of the R$/kWh rate
    (0,175126). The plausible-range guard in ``UtilityBill.validate()`` is what
    turns that silent miscapture into a loud rejection — see ADR-056.
    """
    text = _real_scee_bill_with_tariff_text(
        month="jun",
        cycle_start="18/05/2026",
        reading_date="17/06/2026",
        billed_days="30",
        next_month="07",
        with_taxes="0,799059",
    )
    shifted = text.replace(
        f"PARC INJET S/DESC - 28,57% - GD II 2 KWH 278,00 {REAL_WIRE_B} 48,69",
        f"PARC INJET S/DESC - 28,57% - GD II 2 KWH {REAL_WIRE_B} 48,69",
    )
    assert shifted != text, "fixture did not change; the shifted-column setup is stale"

    with pytest.raises(ValueError, match="wire_b_tariff_brl_kwh"):
        parse_equatorial_bill_text(shifted)


# ---------------------------------------------------------------------------
# Layout "segunda via" (set/2026): colunas coladas pelo pypdf
# ---------------------------------------------------------------------------

# Reprodução anonimizada do texto extraído (pypdf) da segunda via real de
# set/2026: nome, endereço, CPF, nº da UC e códigos trocados por marcadores,
# ordem e "cola" entre colunas preservadas exatamente como no PDF.
SECOND_COPY_BILL_TEXT = """
16/10/202629
FORNECIMENTO
CONSUMO SCEE kWh 0,787589221,00 5,51 174,06 19% 33,07 0,613030174,06
BENEFÍCIO TARIFÁRIO BRUTO SCEE 96,78
INJEÇÃO SCEE - GD II 2 kWh 0,787589221,00 -5,51 -174,06 19% -33,07 0,613030-174,06
PARC INJET S/DESC - 28,57% - GD II 2 kWh 0,175126221,00 0,17512638,70
PARC INJET S/ DESC RET 21/22 1,31
CONTRIB. ILUM. PÚBLICA - MUNICIPAL 30,21
ITENS FINANCEIROS
BENEFÍCIO TARIFÁRIO LÍQUIDO SCEE -96,78
Tipo de fornecimento: MONOFÁSICO
NOME DO TITULAR
CNPJ/CPF: XXX.XXX.XXX-XX
R$**********70,22 10/10/2026
17/08/2026 15/09/2026
SET/2026
INFORMAÇÕES DO SCEE: GERAÇÃO CICLO (9/2026) KWH: UC XXXXXXXXXXX : 235,00,
EXCEDENTE RECEBIDO KWH: UC XXXXXXXXXXX : 14,00, CRÉDITO RECEBIDO KWH 221,00,
SALDO KWH: 17,98, SALDO A EXPIRAR EM 30 DIAS KWH: 0,00,
ENERGIA ATIVA - KWH 05649 221XXXXXXXX 05428 1,000000ÚNICO
TOTAL 0,00 0,00 0,0070,22
Equatorial Goiás Distribuidora de Energia S.A.
"""


def test_second_copy_layout_extracts_every_field() -> None:
    bill = parse_equatorial_bill_text(SECOND_COPY_BILL_TEXT)

    assert bill.reference_month == "2026-09"
    assert bill.cycle_start.isoformat() == "2026-08-17"
    assert bill.cycle_end.isoformat() == "2026-09-14"  # leitura 15/09 é exclusiva
    assert bill.billed_days == 29
    assert bill.imported_kwh == Decimal("221.00")  # e não 0,787589221
    assert bill.injected_kwh == Decimal("221.00")
    assert bill.compensated_kwh == Decimal("221.00")
    assert bill.credit_balance_kwh == Decimal("17.98")
    assert bill.total_amount_brl == Decimal("70.22")
    assert bill.public_lighting_brl == Decimal("30.21")
    assert bill.generation_cycle_kwh == Decimal("235.00")
    assert bill.tariff_with_taxes_brl_kwh == Decimal("0.787589")
    assert bill.tariff_without_taxes_brl_kwh == Decimal("0.613030")
    assert bill.wire_b_tariff_brl_kwh == Decimal("0.175126")


def test_second_copy_layout_rejects_inconsistent_price_times_quantity() -> None:
    # Preço adulterado: 0,887589 × 221 ≠ 174,06 → a separação das colunas não é
    # confiável, então a fatura é recusada em vez de gravada.
    tampered = SECOND_COPY_BILL_TEXT.replace(
        "CONSUMO SCEE kWh 0,787589221,00", "CONSUMO SCEE kWh 0,887589221,00"
    )

    with pytest.raises(BillParseError, match="inconsistent"):
        parse_equatorial_bill_text(tampered)


def test_second_copy_layout_rejects_dates_that_do_not_match_days() -> None:
    tampered = SECOND_COPY_BILL_TEXT.replace("16/10/202629", "16/10/202630")

    with pytest.raises(BillParseError, match="billed days"):
        parse_equatorial_bill_text(tampered)


def test_second_copy_layout_missing_column_fails_closed_instead_of_falling_back() -> None:
    # Sem a linha de injeção, os padrões genéricos poderiam "achar" algo errado;
    # o layout detectado exige o extrator dedicado e recusa.
    without_injection = "\n".join(
        line for line in SECOND_COPY_BILL_TEXT.splitlines() if not line.startswith("INJEÇÃO")
    )

    with pytest.raises(BillParseError, match="second-copy"):
        parse_equatorial_bill_text(without_injection)


def test_second_copy_layout_without_wire_b_line_leaves_it_empty() -> None:
    without_wire_b = "\n".join(
        line
        for line in SECOND_COPY_BILL_TEXT.splitlines()
        if not line.startswith("PARC INJET S/DESC")
    )

    bill = parse_equatorial_bill_text(without_wire_b)

    assert bill.wire_b_tariff_brl_kwh is None  # nunca um valor colado lido pela metade
