"""ADR-085: bandeira na conta "sem a usina" e créditos que não vêm das placas
fora da economia. Números da fatura real de out/2026 (anonimizada)."""

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from mplacas.billing.models import UtilityBill
from mplacas.billing.parser import _sum_flag_tariffs, _sum_non_energy_credits
from mplacas.intelligence.energy_engine import analyze_energy_cycle
from mplacas.reports.savings_gaps import SavingsGapCause, _gap_for


def _october(**overrides: object) -> UtilityBill:
    values: dict[str, object] = dict(
        distributor="EQUATORIAL_GO",
        reference_month="2026-10",
        cycle_start=date(2026, 9, 15),
        cycle_end=date(2026, 10, 15),
        billed_days=31,
        imported_kwh=Decimal("338"),
        injected_kwh=Decimal("255.98"),
        compensated_kwh=Decimal("255.98"),
        credit_balance_kwh=Decimal("0"),
        total_amount_brl=Decimal("171.32"),
        public_lighting_brl=Decimal("30.21"),
        generation_cycle_kwh=Decimal("238"),
        tariff_with_taxes_brl_kwh=Decimal("0.787884"),
        tariff_without_taxes_brl_kwh=Decimal("0.613030"),
        wire_b_tariff_brl_kwh=Decimal("0.175126"),
        flag_tariff_brl_kwh=Decimal("0.011721"),
    )
    values.update(overrides)
    return UtilityBill(**values)  # type: ignore[arg-type]


def _analyze(bill: UtilityBill):
    return analyze_energy_cycle(
        bill=bill,
        cycle_production_kwh=Decimal("538"),  # 300 consumidos em casa + 238 enviados
        production_days=31,
        full_tariff_without_taxes=Decimal("0.891810"),
    )


def test_parser_reads_single_flag_line_glued_price() -> None:
    one = "adc bandeira amarela kwh 0,01172182,02 0,04 0,96"
    assert _sum_flag_tariffs(one) == Decimal("0.011721")
    # Duas cores no ciclo: formato não confirmado em fatura real — falha fechada.
    two = one + " adc bandeira vermelha patamar 1 kwh 0,03000010,00 0,01 0,30"
    assert _sum_flag_tariffs(two) is None
    assert _sum_flag_tariffs("consumo scee kwh 0,787884255,98") is None
    # Valor total no lugar do preço (coluna deslocada): implausível, vira None.
    assert _sum_flag_tariffs("adc bandeira amarela kwh 1,23456782,02") is None


def test_parser_reads_interruption_compensation_and_itaipu_bonus() -> None:
    text = (
        "compensação de dic mensal -6,38 bonus itaipu art.21 lei 10438/02(-) -30,38 "
        "parc injet s/ desc ret 2/22 1,31"
    )
    assert _sum_non_energy_credits(text) == Decimal("36.76")
    assert _sum_non_energy_credits("parc injet s/ desc ret 2/22 1,31") is None


def test_flag_enters_bill_without_solar_and_model_matches_real_bill() -> None:
    with_flag = _analyze(_october())
    without_flag = _analyze(_october(flag_tariff_brl_kwh=None))
    total_consumption = Decimal("338") + Decimal("300")
    # Sem a usina, todo o consumo pagaria a bandeira.
    assert with_flag.estimated_savings_brl - without_flag.estimated_savings_brl == (
        total_consumption * Decimal("0.011721")
    ).quantize(Decimal("0.01"))
    # A fatura real (R$ 171,32) menos o modelo deixa só a parcela retroativa
    # do Fio B (R$ 1,31): a bandeira passou a ser explicada.
    assert with_flag.bill_model_difference_brl == Decimal("1.31")
    assert with_flag.flag_tariff_brl_kwh == Decimal("0.011721")


def test_non_energy_credits_do_not_become_plant_savings() -> None:
    base = _analyze(_october(flag_tariff_brl_kwh=None))
    bonus = _analyze(
        _october(
            flag_tariff_brl_kwh=None,
            total_amount_brl=Decimal("171.32") - Decimal("30.38"),
            non_energy_credits_brl=Decimal("30.38"),
        )
    )
    # O Bônus de Itaipu baixou a fatura, mas a economia da usina é a mesma.
    assert bonus.estimated_savings_brl == base.estimated_savings_brl
    assert bonus.bill_model_difference_brl == base.bill_model_difference_brl
    # O componente de energia continua sendo o valor PAGO (cabe no total).
    assert bonus.bill_energy_component_brl == Decimal("171.32") - Decimal("30.38") - Decimal(
        "30.21"
    )
    # "Sem a usina − você pagou" continua igual à economia.
    assert bonus.bill_without_solar_brl - bonus.total_amount_brl == bonus.estimated_savings_brl


def _snapshot(version: str) -> SimpleNamespace:
    def metric(key: str, value: str) -> SimpleNamespace:
        return SimpleNamespace(key=key, value=value)

    report = SimpleNamespace(
        calculation_version=version,
        metrics=(
            metric("estimated_savings_brl", "300.00"),
            metric("savings_tariff_source", "DISTRIBUTOR_FULL_TARIFF"),
        ),
        quality=(),
    )
    return SimpleNamespace(report=report, revision=1)


def test_pre_0_5_report_is_outdated_only_when_bill_has_flag_or_credits() -> None:
    bill_id = uuid.uuid4()
    plain = _october(flag_tariff_brl_kwh=None)
    with_flag = _october()
    with_credit = _october(flag_tariff_brl_kwh=None, non_energy_credits_brl=Decimal("6.38"))

    assert _gap_for(bill_id, "2026-10", _snapshot("0.4.0"), plain) is None  # type: ignore[arg-type]
    for bill in (with_flag, with_credit):
        gap = _gap_for(bill_id, "2026-10", _snapshot("0.4.0"), bill)  # type: ignore[arg-type]
        assert gap is not None and gap.cause is SavingsGapCause.OUTDATED_CALCULATION
    assert _gap_for(bill_id, "2026-10", _snapshot("0.5.0"), with_flag) is None  # type: ignore[arg-type]
