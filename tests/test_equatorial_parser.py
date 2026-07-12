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


def test_parser_extracts_anonimized_equatorial_bill() -> None:
    bill = parse_equatorial_bill_text(SYNTHETIC_BILL_TEXT)
    assert bill.reference_month == "2026-06"
    assert bill.billed_days == 30
    assert bill.imported_kwh == Decimal("278.000")
    assert bill.injected_kwh == Decimal("182.000")
    assert bill.credit_balance_kwh == Decimal("63.980")
    assert bill.total_amount_brl == Decimal("80.21")
    assert bill.public_lighting_brl == Decimal("30.21")


def test_parser_fails_closed_when_mandatory_field_is_missing() -> None:
    text = SYNTHETIC_BILL_TEXT.replace("Energia injetada: 182,000 kWh", "")
    with pytest.raises(BillParseError, match="injected_kwh"):
        parse_equatorial_bill_text(text)


def test_parser_rejects_unidentified_distributor() -> None:
    with pytest.raises(BillParseError, match="not identified"):
        parse_equatorial_bill_text(SYNTHETIC_BILL_TEXT.replace("Equatorial", "Distribuidora X"))
