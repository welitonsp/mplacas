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
SALDO A EXPIRAR EM 60 DIAS KWH: 0,00, CADASTRO RATEIO GERAÇÃO: UC XXXXXXXXXXX = 100%
ENERGIA ATIVA - KWH 01234 221XXXXXXXX 01013 1,000000ÚNICO
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


def _replace_line(text: str, prefix: str, new_line: str) -> str:
    return "\n".join(
        new_line if line.startswith(prefix) else line for line in text.splitlines()
    )


def test_second_copy_layout_rejects_injection_quantity_that_does_not_match_its_value() -> None:
    # Revisão de billing: antes, "100,00" passava e gravava injeção errada.
    tampered = _replace_line(
        SECOND_COPY_BILL_TEXT,
        "INJEÇÃO SCEE",
        "INJEÇÃO SCEE - GD II 2 kWh 0,787589100,00 -5,51 -174,06 19% -33,07 0,613030-174,06",
    )

    with pytest.raises(BillParseError, match="injection columns are inconsistent"):
        parse_equatorial_bill_text(tampered)


@pytest.mark.parametrize(
    "duplicated_prefix",
    ["CONSUMO SCEE", "INJEÇÃO SCEE"],
)
def test_second_copy_layout_refuses_more_than_one_consumption_or_injection_line(
    duplicated_prefix: str,
) -> None:
    lines = SECOND_COPY_BILL_TEXT.splitlines()
    original = next(line for line in lines if line.startswith(duplicated_prefix))
    duplicated = SECOND_COPY_BILL_TEXT.replace(original, original + "\n" + original)

    with pytest.raises(BillParseError, match="exactly one"):
        parse_equatorial_bill_text(duplicated)


@pytest.mark.parametrize("wrong_reference", ["OUT/2026", "SET/2020", "JUL/2026"])
def test_second_copy_layout_rejects_reference_month_outside_the_reading_dates(
    wrong_reference: str,
) -> None:
    tampered = SECOND_COPY_BILL_TEXT.replace("\nSET/2026\n", f"\n{wrong_reference}\n")

    with pytest.raises(BillParseError, match="reference month"):
        parse_equatorial_bill_text(tampered)


def test_second_copy_layout_rejects_wire_b_line_that_cannot_be_read_safely() -> None:
    # Linha de Fio B presente, mas valor da linha não bate com tarifa × qtd:
    # recusa, em vez de cair no padrão genérico ou virar None em silêncio.
    tampered = _replace_line(
        SECOND_COPY_BILL_TEXT,
        "PARC INJET S/DESC",
        "PARC INJET S/DESC - 28,57% - GD II 2 kWh 0,175126221,00 0,17512699,99",
    )

    with pytest.raises(BillParseError, match="wire B"):
        parse_equatorial_bill_text(tampered)


def test_second_copy_layout_reads_wire_b_with_spaced_label() -> None:
    spaced = _replace_line(
        SECOND_COPY_BILL_TEXT,
        "PARC INJET S/DESC",
        "PARC INJET S/ DESC - 28,57% - GD II 2 kWh 0,175126221,00 0,17512638,70",
    )

    assert parse_equatorial_bill_text(spaced).wire_b_tariff_brl_kwh == Decimal("0.175126")


def test_second_copy_layout_handles_thousands_separator_in_quantity() -> None:
    # 0,787589 × 1.221 = 961,65 ; 0,175126 × 1.221 = 213,83
    big = _replace_line(
        SECOND_COPY_BILL_TEXT,
        "CONSUMO SCEE",
        "CONSUMO SCEE kWh 0,7875891.221,00 15,51 961,65 19% 182,71 0,613030961,65",
    )
    big = _replace_line(
        big,
        "INJEÇÃO SCEE",
        "INJEÇÃO SCEE - GD II 2 kWh 0,7875891.221,00 -15,51 -961,65 19% -182,71 0,613030-961,65",
    )
    big = _replace_line(
        big,
        "PARC INJET S/DESC",
        "PARC INJET S/DESC - 28,57% - GD II 2 kWh 0,1751261.221,00 0,175126213,83",
    )
    # O medidor precisa contar o mesmo consumo (02234 − 01013 = 1.221).
    big = _replace_line(
        big,
        "ENERGIA ATIVA - KWH",
        "ENERGIA ATIVA - KWH 02234 1221XXXXXXXX 01013 1,000000ÚNICO",
    )

    bill = parse_equatorial_bill_text(big)

    assert bill.imported_kwh == Decimal("1221.00")
    assert bill.injected_kwh == Decimal("1221.00")


def test_old_layout_does_not_trigger_second_copy_extractor() -> None:
    text = _real_scee_bill_with_tariff_text(
        month="jul",
        cycle_start="17/06/2026",
        reading_date="17/07/2026",
        billed_days="30",
        next_month="08",
        with_taxes="0,814841",
    )

    bill = parse_equatorial_bill_text(text)

    assert bill.reference_month == "2026-07"
    assert bill.imported_kwh == Decimal("278.00")
    assert bill.tariff_with_taxes_brl_kwh == Decimal("0.814841")


# --- Layouts antigos da Equatorial (faturas reais de 2024 a 2026, anonimizadas) ---
# Só as linhas que o leitor usa; nome, CPF, endereço, UC, nº do medidor e PIX
# foram removidos.


def _old_bill(*, days_line: str, energy: str, total: str, dates: str, ref: str,
              scee: str, meter: str, lighting: str = "21,32") -> str:
    return "\n".join(
        [
            days_line,
            "FORNECIMENTO",
            energy.strip(),
            f"CONTRIB. ILUM. PÚBLICA - MUNICIPAL {lighting}",
            "ITENS FINANCEIROS",
            f"R$**********{total} 10/10/2024",
            dates,
            ref,
            scee,
            meter,
            "EQUATORIAL GOIAS DISTRIBUIDORA DE ENERGIA S/A",
        ]
    )


# Set/2024: antes da transição da Lei 14.300 ("ENERGIA ATIVA FORNECIDA" /
# "ENERGIA INJETADA", sem Fio B) e primeiro ciclo do medidor novo: a fatura
# imprime 32 dias para o período 16/08–16/09 (31 dias).
PRE_TRANSITION_FIRST_CYCLE_TEXT = _old_bill(
    days_line="16/10/202432",
    energy="""
AD. BAND. VERMELHA EN. ATIVA FORN. kWh 0,02865130,00 0,02 0,86 19% 0,16 0,0223150,86
ENERGIA ATIVA FORNECIDA kWh 0,912400149,00 4,23 135,95 19% 25,83 0,710630135,95
ENERGIA INJETADA kWh 0,912400119,00 -3,38 -108,58 19% -20,63 0,710630-108,58
""",
    total="49,55",
    dates="16/08/2024 16/09/2024",
    ref="SET/2024",
    scee=(
        "INFORMAÇÕES DO SCEE: GERAÇÃO CICLO (9/2024) KWH: UC XXXXXXXXXXX : 352,00, "
        "EXCEDENTE RECEBIDO KWH: UC XXXXXXXXXXX : 233,00, CRÉDITO RECEBIDO KWH 119,00, "
        "SALDO KWH: 233,00, SALDO A EXPIRAR EM 30 DIAS KWH: 0,00,"
    ),
    meter="ENERGIA ATIVA - KWH 00149 149XXXXXXXX-8 00000 1,000000ÚNICO",
)


def test_pre_transition_layout_reads_supplied_and_compensated_energy() -> None:
    bill = parse_equatorial_bill_text(PRE_TRANSITION_FIRST_CYCLE_TEXT)

    assert bill.reference_month == "2024-09"
    assert bill.cycle_start.isoformat() == "2024-08-16"
    assert bill.cycle_end.isoformat() == "2024-09-15"
    # Medidor novo: vale o período impresso, não os 32 dias contados desde a instalação.
    assert bill.billed_days == 31
    assert bill.imported_kwh == Decimal("149.00")
    # 30 kWh de custo de disponibilidade não são compensados.
    assert bill.compensated_kwh == Decimal("119.00")
    assert bill.injected_kwh == Decimal("119.00")
    assert bill.generation_cycle_kwh == Decimal("352.00")
    assert bill.tariff_with_taxes_brl_kwh == Decimal("0.912400")
    assert bill.tariff_without_taxes_brl_kwh == Decimal("0.710630")
    assert bill.wire_b_tariff_brl_kwh is None
    assert bill.total_amount_brl == Decimal("49.55")


def test_days_mismatch_is_still_rejected_when_meter_is_not_new() -> None:
    not_new = PRE_TRANSITION_FIRST_CYCLE_TEXT.replace(
        "ENERGIA ATIVA - KWH 00149 149XXXXXXXX-8 00000",
        "ENERGIA ATIVA - KWH 01149 149XXXXXXXX-8 01000",
    )

    with pytest.raises(BillParseError, match="billed days"):
        parse_equatorial_bill_text(not_new)


# Jan/2025: transição, injeção sem colunas de imposto e consumo não compensado.
TRANSITION_SHORT_INJECTION_TEXT = _old_bill(
    days_line="15/02/202530",
    energy="""
CONSUMO NÃO COMPENSADO kWh 0,9382839,75 0,13 9,15 19% 1,74 0,7459309,15
CONSUMO SCEE kWh 0,626570144,25 1,35 90,38 19% 17,17 0,49812090,38
INJEÇÃO SCEE - GD II 2 kWh 0,507522144,25 -1,35 0,498120-73,21
BENEFÍCIO TARIFÁRIO BRUTO SCEE 56,75
PARC INJET S/DESC - 21,02% - GD II 2 kWh 0,104716144,25 0,10471615,11
PARC INJET S/ DESC RET 1/22 1,31
BONUS ITAIPU ART.21 LEI 10438/02(-) -30,38
""",
    total="46,02",
    dates="18/12/2024 17/01/2025",
    ref="JAN/2025",
    scee=(
        "INFORMAÇÕES DO SCEE: GERAÇÃO CICLO (1/2025) KWH: UC XXXXXXXXXXX : 168,00, "
        "CRÉDITO RECEBIDO KWH 144,25, SALDO KWH: 551,73,"
    ),
    meter="ENERGIA ATIVA - KWH 00768 154XXXXXXXX-8 00614 1,000000ÚNICO",
    lighting="31,98",
)


def test_transition_layout_sums_uncompensated_consumption() -> None:
    bill = parse_equatorial_bill_text(TRANSITION_SHORT_INJECTION_TEXT)

    assert bill.reference_month == "2025-01"
    # 144,25 compensados + 9,75 não compensados = 154 do medidor.
    assert bill.imported_kwh == Decimal("154.00")
    assert bill.compensated_kwh == Decimal("144.25")
    assert bill.injected_kwh == Decimal("144.25")
    assert bill.tariff_with_taxes_brl_kwh == Decimal("0.626570")
    assert bill.wire_b_tariff_brl_kwh == Decimal("0.104716")
    assert bill.total_amount_brl == Decimal("46.02")
    assert bill.public_lighting_brl == Decimal("31.98")


def test_missing_uncompensated_line_is_caught_by_the_meter() -> None:
    without = "\n".join(
        line
        for line in TRANSITION_SHORT_INJECTION_TEXT.splitlines()
        if not line.startswith("CONSUMO NÃO COMPENSADO")
    )

    with pytest.raises(BillParseError, match="meter reading"):
        parse_equatorial_bill_text(without)


def test_unreadable_uncompensated_line_fails_closed() -> None:
    tampered = TRANSITION_SHORT_INJECTION_TEXT.replace(
        "0,9382839,75 0,13 9,15", "0,9382839,75 0,13 19,15"
    )

    with pytest.raises(BillParseError, match="uncompensated"):
        parse_equatorial_bill_text(tampered)


def test_short_injection_must_close_price_times_quantity() -> None:
    tampered = TRANSITION_SHORT_INJECTION_TEXT.replace(
        "0,498120-73,21", "0,498120-83,21"
    )

    with pytest.raises(BillParseError, match="injection"):
        parse_equatorial_bill_text(tampered)


def test_tax_columns_with_one_or_zero_decimals_are_accepted() -> None:
    # Fev/2025: a base do não compensado vem como "2" (R$ 2,00) e o PIS/COFINS
    # da linha SCEE como "1,7"; ago/2026 imprimiu a base como "194,6".
    text = _old_bill(
        days_line="18/03/202529",
        energy="""
CONSUMO NÃO COMPENSADO kWh 0,9394672,13 0,04 2 19% 0,38 0,7459302,00
CONSUMO SCEE kWh 0,627360169,87 1,7 106,57 19% 20,25 0,498120106,57
INJEÇÃO SCEE - GD II 2 kWh 0,627360169,87 -1,7 -106,57 19% -20,25 0,498120-106,57
PARC INJET S/DESC - 24,57% - GD II 2 kWh 0,122387169,87 0,12238720,79
""",
        total="49,70",
        dates="17/01/2025 15/02/2025",
        ref="FEV/2025",
        scee="INFORMAÇÕES DO SCEE: GERAÇÃO CICLO (2/2025) KWH: UC XXXXXXXXXXX : 124,00, "
        "SALDO KWH: 505,86,",
        meter="ENERGIA ATIVA - KWH 00940 172XXXXXXXX-8 00768 1,000000ÚNICO",
    )
    bill = parse_equatorial_bill_text(text)
    assert bill.imported_kwh == Decimal("172.00")
    assert bill.compensated_kwh == Decimal("169.87")

    august = _replace_line(
        SECOND_COPY_BILL_TEXT,
        "CONSUMO SCEE",
        "CONSUMO SCEE kWh 0,807464241,00 9,89 194,6 19% 36,97 0,613030194,60",
    )
    august = _replace_line(
        august,
        "INJEÇÃO SCEE",
        "INJEÇÃO SCEE - GD II 2 kWh 0,807464241,00 -9,89 -194,6 19% -36,97 0,613030-194,60",
    )
    august = _replace_line(
        august,
        "PARC INJET S/DESC",
        "PARC INJET S/DESC - 28,57% - GD II 2 kWh 0,175126241,00 0,17512642,21",
    )
    august = _replace_line(
        august, "ENERGIA ATIVA - KWH", "ENERGIA ATIVA - KWH 01254 241XXXXXXXX 01013 1,000000ÚNICO"
    )
    assert parse_equatorial_bill_text(august).imported_kwh == Decimal("241.00")


def test_meter_reading_that_does_not_match_its_glued_consumption_fails_closed() -> None:
    tampered = _replace_line(
        SECOND_COPY_BILL_TEXT,
        "ENERGIA ATIVA - KWH",
        "ENERGIA ATIVA - KWH 01234 999XXXXXXXX 01013 1,000000ÚNICO",
    )

    with pytest.raises(BillParseError, match="meter reading"):
        parse_equatorial_bill_text(tampered)


def test_second_copy_layout_without_meter_reading_fails_closed() -> None:
    # Sem o medidor não há como saber se alguma linha de consumo ficou de fora.
    without_meter = "\n".join(
        line
        for line in TRANSITION_SHORT_INJECTION_TEXT.splitlines()
        if not line.startswith("ENERGIA ATIVA - KWH")
    )

    with pytest.raises(BillParseError, match="meter reading not found"):
        parse_equatorial_bill_text(without_meter)


def test_new_meter_exception_is_limited_to_a_few_extra_days() -> None:
    far_off = PRE_TRANSITION_FIRST_CYCLE_TEXT.replace("16/10/202432", "16/10/202445")

    with pytest.raises(BillParseError, match="billed days"):
        parse_equatorial_bill_text(far_off)


def test_second_copy_layout_reads_generation_share_and_expiring_credits() -> None:
    # ADR-084: rateio de 100% confirma que todo crédito é desta UC; o saldo a
    # expirar em 30 dias separa vencimento de crédito sumido.
    bill = parse_equatorial_bill_text(SECOND_COPY_BILL_TEXT)
    assert bill.generation_share_percent == Decimal("100")
    assert bill.credits_expiring_30d_kwh == Decimal("0.00")


def test_expiring_credits_and_share_are_read_when_present() -> None:
    text = SECOND_COPY_BILL_TEXT.replace(
        "SALDO A EXPIRAR EM 30 DIAS KWH: 0,00,", "SALDO A EXPIRAR EM 30 DIAS KWH: 12,50,"
    ).replace("= 100%", "= 60%")
    bill = parse_equatorial_bill_text(text)
    assert bill.credits_expiring_30d_kwh == Decimal("12.50")
    assert bill.generation_share_percent == Decimal("60")


def test_missing_or_impossible_share_is_none_never_presumed() -> None:
    without = parse_equatorial_bill_text(
        SECOND_COPY_BILL_TEXT.replace("CADASTRO RATEIO GERAÇÃO: UC XXXXXXXXXXX = 100%", "")
    )
    assert without.generation_share_percent is None
    impossible = parse_equatorial_bill_text(SECOND_COPY_BILL_TEXT.replace("= 100%", "= 250%"))
    assert impossible.generation_share_percent is None
