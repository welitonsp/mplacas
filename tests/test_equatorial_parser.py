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
