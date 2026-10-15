from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from mplacas.billing.models import UtilityBill
from mplacas.intelligence.energy_engine import (
    SAVINGS_UNAVAILABLE_NO_CONSUMPTION_DATA,
    SAVINGS_UNAVAILABLE_TARIFF_NOT_REGISTERED,
    DiagnosticSeverity,
    analyze_energy_cycle,
)


def _bill() -> UtilityBill:
    return UtilityBill(
        distributor="Equatorial GO",
        reference_month="2026-06",
        cycle_start=date(2026, 5, 18),
        cycle_end=date(2026, 6, 16),
        billed_days=30,
        imported_kwh=Decimal("278"),
        injected_kwh=Decimal("182"),
        compensated_kwh=Decimal("278"),
        credit_balance_kwh=Decimal("63.98"),
        total_amount_brl=Decimal("80.21"),
        public_lighting_brl=Decimal("30.21"),
    )


def test_builds_auditable_cycle_indicators() -> None:
    result = analyze_energy_cycle(
        bill=_bill(),
        cycle_production_kwh=Decimal("300"),
        expected_production_kwh=Decimal("320"),
    )

    assert result.reconciliation.estimated_self_consumption_kwh == Decimal("118.000")
    assert result.reconciliation.estimated_total_consumption_kwh == Decimal("396.000")
    assert result.grid_dependency_rate_percent == Decimal("70.2")
    assert result.exported_generation_rate_percent == Decimal("60.7")
    assert result.credit_coverage_rate_percent == Decimal("100.0")
    assert result.bill_energy_component_brl == Decimal("50.00")
    assert result.health_score == 100
    assert result.diagnostics[0].code == "CYCLE_WITHIN_EXPECTED_PARAMETERS"


def test_penalizes_missing_and_provisional_data() -> None:
    result = analyze_energy_cycle(
        bill=_bill(),
        cycle_production_kwh=Decimal("250"),
        expected_production_kwh=Decimal("320"),
        missing_days=2,
        provisional_days=2,
    )

    codes = {diagnostic.code for diagnostic in result.diagnostics}
    assert codes == {
        "MISSING_DAILY_DATA",
        "PROVISIONAL_DAILY_DATA",
        "PRODUCTION_BELOW_EXPECTED",
    }
    assert result.health_score == 63


def test_detects_critical_zero_production() -> None:
    result = analyze_energy_cycle(
        bill=_bill(),
        cycle_production_kwh=Decimal("0"),
        expected_production_kwh=Decimal("300"),
    )

    critical_codes = {
        diagnostic.code
        for diagnostic in result.diagnostics
        if diagnostic.severity is DiagnosticSeverity.CRITICAL
    }
    assert "ZERO_PRODUCTION_WITH_GRID_IMPORT" in critical_codes
    assert "PRODUCTION_WELL_BELOW_EXPECTED" in critical_codes
    assert result.health_score == 35


def test_exposes_financial_fields_and_computes_savings_when_tariff_registered() -> None:
    bill = UtilityBill(
        distributor="Equatorial GO",
        reference_month="2026-06",
        cycle_start=date(2026, 5, 18),
        cycle_end=date(2026, 6, 16),
        billed_days=30,
        imported_kwh=Decimal("278"),
        injected_kwh=Decimal("182"),
        compensated_kwh=Decimal("278"),
        credit_balance_kwh=Decimal("63.98"),
        total_amount_brl=Decimal("80.21"),
        public_lighting_brl=Decimal("30.21"),
        tariff_with_taxes_brl_kwh=Decimal("0.85"),
        tariff_without_taxes_brl_kwh=Decimal("0.60"),
    )

    result = analyze_energy_cycle(
        bill=bill,
        cycle_production_kwh=Decimal("300"),
        expected_production_kwh=Decimal("320"),
    )

    assert result.total_amount_brl == Decimal("80.21")
    assert result.public_lighting_brl == Decimal("30.21")
    assert result.tariff_with_taxes_brl_kwh == Decimal("0.85")
    assert result.tariff_without_taxes_brl_kwh == Decimal("0.60")
    assert result.credit_balance_kwh == Decimal("63.98")
    # estimated_total_consumption_kwh = 396.000 (ver
    # test_builds_auditable_cycle_indicators); energy_component = 50.00.
    # 396.000 * 0.85 - 50.00 = 286.60
    assert result.estimated_savings_brl == Decimal("286.60")
    assert result.savings_unavailable_reason is None


def test_omits_savings_without_fabricating_zero_when_tariff_not_registered() -> None:
    result = analyze_energy_cycle(
        bill=_bill(),
        cycle_production_kwh=Decimal("300"),
        expected_production_kwh=Decimal("320"),
    )

    assert result.estimated_savings_brl is None
    assert result.savings_unavailable_reason == SAVINGS_UNAVAILABLE_TARIFF_NOT_REGISTERED


def test_omits_savings_without_fabricating_negative_when_consumption_is_zero() -> None:
    bill = UtilityBill(
        distributor="Equatorial GO",
        reference_month="2026-06",
        cycle_start=date(2026, 5, 18),
        cycle_end=date(2026, 6, 16),
        billed_days=30,
        imported_kwh=Decimal("0"),
        injected_kwh=Decimal("0"),
        compensated_kwh=Decimal("0"),
        credit_balance_kwh=Decimal("0"),
        total_amount_brl=Decimal("30.21"),
        public_lighting_brl=Decimal("30.21"),
        tariff_with_taxes_brl_kwh=Decimal("0.85"),
        tariff_without_taxes_brl_kwh=Decimal("0.60"),
    )

    result = analyze_energy_cycle(
        bill=bill,
        cycle_production_kwh=Decimal("0"),
        expected_production_kwh=Decimal("320"),
    )

    # estimated_total_consumption_kwh = imported_kwh + max(0, cycle_production_kwh
    # - injected_kwh) = 0 + max(0, 0 - 0) = 0. Sem esta checagem, a formula
    # devolveria -energy_component (um numero negativo real, mas enganoso:
    # pareceria "voce pagou a mais" quando na verdade e ausencia de dado).
    assert result.estimated_savings_brl is None
    assert result.savings_unavailable_reason == SAVINGS_UNAVAILABLE_NO_CONSUMPTION_DATA


def test_rejects_invalid_quality_counters() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        analyze_energy_cycle(
            bill=_bill(),
            cycle_production_kwh=Decimal("300"),
            missing_days=-1,
        )


def test_bill_with_and_without_solar_and_model_check_on_real_scee_bill() -> None:
    bill = UtilityBill(
        distributor="EQUATORIAL_GO",
        reference_month="2026-09",
        cycle_start=date(2026, 8, 17),
        cycle_end=date(2026, 9, 14),
        billed_days=29,
        imported_kwh=Decimal("221"),
        injected_kwh=Decimal("221"),
        compensated_kwh=Decimal("221"),
        credit_balance_kwh=Decimal("17.98"),
        total_amount_brl=Decimal("70.22"),
        public_lighting_brl=Decimal("30.21"),
        generation_cycle_kwh=Decimal("235"),
        tariff_with_taxes_brl_kwh=Decimal("0.787589"),
        tariff_without_taxes_brl_kwh=Decimal("0.613030"),
        wire_b_tariff_brl_kwh=Decimal("0.175126"),
    )

    result = analyze_energy_cycle(bill=bill, cycle_production_kwh=Decimal("400"))

    # Consumo total = 221 da rede + 165 direto do telhado (400 − 235) = 386.
    # Sem usina: 386 × 0,787589 + 30,21 = 304,009 + 30,21 = 334,219 → 334,22.
    assert result.bill_without_solar_brl == Decimal("334.22")
    # Economia = sem usina − pago = 334,22 − 70,22 = 264,00, igual à fórmula
    # antiga (consumo × tarifa − componente de energia), agora com o consumo
    # certo.
    assert result.estimated_savings_brl == Decimal("264.00")
    # Créditos: valor líquido do Fio B = 17,98 × (0,787589 − 0,175126) = 11,01.
    assert result.credit_balance_value_brl == Decimal("11.01")
    # A identidade economia = sem usina − pago vale.
    assert result.bill_without_solar_brl - result.total_amount_brl == result.estimated_savings_brl
    # Conferência: 0 não compensado + 221 × 0,175126 (= 38,70) + 30,21 = 68,91;
    # a fatura cobrou 70,22 → R$ 1,31 que o modelo não explica (o retroativo
    # "PARC INJET S/ DESC RET 21/22" da fatura).
    assert result.modeled_bill_brl == Decimal("68.91")
    assert result.bill_model_difference_brl == Decimal("1.31")
    assert result.compensated_kwh == Decimal("221")


def test_bill_comparison_fields_are_null_without_tariff() -> None:
    bill = UtilityBill(
        distributor="EQUATORIAL_GO",
        reference_month="2026-06",
        cycle_start=date(2026, 5, 18),
        cycle_end=date(2026, 6, 16),
        billed_days=30,
        imported_kwh=Decimal("278"),
        injected_kwh=Decimal("182"),
        compensated_kwh=Decimal("278"),
        credit_balance_kwh=Decimal("63.98"),
        total_amount_brl=Decimal("80.21"),
        public_lighting_brl=Decimal("30.21"),
    )

    result = analyze_energy_cycle(bill=bill, cycle_production_kwh=Decimal("300"))

    assert result.bill_without_solar_brl is None
    assert result.credit_balance_value_brl is None
    assert result.modeled_bill_brl is None
    assert result.bill_model_difference_brl is None



def _scee(**overrides) -> UtilityBill:
    values = dict(
        distributor="EQUATORIAL_GO",
        reference_month="2026-09",
        cycle_start=date(2026, 8, 17),
        cycle_end=date(2026, 9, 14),
        billed_days=29,
        imported_kwh=Decimal("221"),
        injected_kwh=Decimal("221"),
        compensated_kwh=Decimal("221"),
        credit_balance_kwh=Decimal("17.98"),
        total_amount_brl=Decimal("70.22"),
        public_lighting_brl=Decimal("30.21"),
        generation_cycle_kwh=Decimal("235"),
        tariff_with_taxes_brl_kwh=Decimal("0.787589"),
        tariff_without_taxes_brl_kwh=Decimal("0.613030"),
        wire_b_tariff_brl_kwh=Decimal("0.175126"),
    )
    values.update(overrides)
    return UtilityBill(**values)


def test_consumption_above_credits_charges_uncompensated_energy_at_full_tariff() -> None:
    # Consumiu 300 da rede; injetou e compensou 221: 79 kWh pagos à tarifa cheia.
    bill = _scee(
        imported_kwh=Decimal("300"),
        generation_cycle_kwh=Decimal("221"),
        total_amount_brl=Decimal("132.44"),
    )
    result = analyze_energy_cycle(bill=bill, cycle_production_kwh=Decimal("400"))
    # 79 × 0,787589 + 221 × 0,175126 + 30,21 = 62,22 + 38,70 + 30,21 = 131,13.
    assert result.modeled_bill_brl == Decimal("131.13")
    assert result.bill_model_difference_brl == Decimal("1.31")
    assert result.reconciliation.excess_credit_kwh == Decimal("0.000")


def test_meter_injection_below_compensated_means_old_credits_were_used() -> None:
    # Injetou só 150 no mês, mas compensou 221 usando créditos antigos.
    bill = _scee(generation_cycle_kwh=Decimal("150"))
    result = analyze_energy_cycle(bill=bill, cycle_production_kwh=Decimal("300"))
    assert result.reconciliation.injected_kwh == Decimal("150")
    assert result.reconciliation.excess_credit_kwh == Decimal("0.000")
    assert result.reconciliation.estimated_self_consumption_kwh == Decimal("150.000")


def test_meter_above_inverter_production_never_creates_negative_self_consumption() -> None:
    # Inversor subnotificou (ex.: dias sem dado): 200 produzidos x 235 injetados.
    result = analyze_energy_cycle(bill=_scee(), cycle_production_kwh=Decimal("200"))
    assert result.reconciliation.estimated_self_consumption_kwh == Decimal("0.000")
    assert result.reconciliation.estimated_total_consumption_kwh == Decimal("221.000")


def test_compensated_above_imported_never_charges_wire_b_beyond_consumption() -> None:
    bill = _scee(compensated_kwh=Decimal("250"))
    result = analyze_energy_cycle(bill=bill, cycle_production_kwh=Decimal("400"))
    # Fio B sobre min(250, 221) = 221, não 250.
    assert result.modeled_bill_brl == Decimal("68.91")


def test_no_imported_energy_leaves_bill_check_unavailable_instead_of_inventing_a_gap() -> None:
    bill = _scee(imported_kwh=Decimal("0"), compensated_kwh=Decimal("0"))
    result = analyze_energy_cycle(bill=bill, cycle_production_kwh=Decimal("400"))
    assert result.modeled_bill_brl is None
    assert result.bill_model_difference_brl is None
