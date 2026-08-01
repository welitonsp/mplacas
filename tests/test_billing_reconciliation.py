from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from mplacas.billing.models import UtilityBill, reconcile_bill


def make_bill() -> UtilityBill:
    return UtilityBill(
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


def test_reconciliation_uses_exact_billing_cycle_values() -> None:
    result = reconcile_bill(bill=make_bill(), cycle_production_kwh=Decimal("610"))
    assert result.estimated_self_consumption_kwh == Decimal("428.000")
    assert result.estimated_total_consumption_kwh == Decimal("706.000")
    assert result.self_consumption_rate_percent == Decimal("70.2")
    assert result.self_sufficiency_rate_percent == Decimal("60.6")


def test_bill_rejects_inconsistent_cycle_days() -> None:
    invalid = replace(make_bill(), billed_days=31)
    with pytest.raises(ValueError, match="billed days"):
        invalid.validate()


def test_reconciliation_never_creates_negative_self_consumption() -> None:
    result = reconcile_bill(bill=make_bill(), cycle_production_kwh=Decimal("100"))
    assert result.estimated_self_consumption_kwh == Decimal("0.000")


def test_reconciliation_without_generation_cycle_has_no_three_way_fields() -> None:
    result = reconcile_bill(bill=make_bill(), cycle_production_kwh=Decimal("610"))
    assert result.generation_cycle_kwh is None
    assert result.meter_vs_injection_delta_kwh is None
    assert result.origin_vs_meter_delta_kwh is None


def test_reconciliation_three_way_deltas_with_generation_cycle() -> None:
    bill = replace(make_bill(), generation_cycle_kwh=Decimal("182"))
    # origin=610, meter=182, injected=182
    # meter_vs_injection = 182 - 182 = 0 (all generation was injected, no autoconsumo via meter)
    # origin_vs_meter = 610 - 182 = 428 (self-consumed at origin, not seen by gen meter)
    result = reconcile_bill(bill=bill, cycle_production_kwh=Decimal("610"))
    assert result.generation_cycle_kwh == Decimal("182")
    assert result.meter_vs_injection_delta_kwh == Decimal("0.000")
    assert result.origin_vs_meter_delta_kwh == Decimal("428.000")


def test_bill_rejects_negative_generation_cycle_kwh() -> None:
    invalid = replace(make_bill(), generation_cycle_kwh=Decimal("-1"))
    with pytest.raises(ValueError, match="negative"):
        invalid.validate()


def test_bill_accepts_absent_generation_cycle_kwh() -> None:
    bill = replace(make_bill(), generation_cycle_kwh=None)
    bill.validate()  # must not raise


def test_bill_rejects_negative_tariff_with_taxes() -> None:
    invalid = replace(make_bill(), tariff_with_taxes_brl_kwh=Decimal("-0.1"))
    with pytest.raises(ValueError, match="negative"):
        invalid.validate()


def test_bill_rejects_negative_tariff_without_taxes() -> None:
    invalid = replace(make_bill(), tariff_without_taxes_brl_kwh=Decimal("-0.1"))
    with pytest.raises(ValueError, match="negative"):
        invalid.validate()


def test_bill_rejects_negative_wire_b_tariff() -> None:
    invalid = replace(make_bill(), wire_b_tariff_brl_kwh=Decimal("-0.1"))
    with pytest.raises(ValueError, match="negative"):
        invalid.validate()


def test_bill_accepts_absent_tariff_fields() -> None:
    bill = replace(
        make_bill(),
        tariff_with_taxes_brl_kwh=None,
        tariff_without_taxes_brl_kwh=None,
        wire_b_tariff_brl_kwh=None,
    )
    bill.validate()  # must not raise


def test_bill_accepts_present_tariff_fields() -> None:
    bill = replace(
        make_bill(),
        tariff_with_taxes_brl_kwh=Decimal("0.799059"),
        tariff_without_taxes_brl_kwh=Decimal("0.613030"),
        wire_b_tariff_brl_kwh=Decimal("0.175126"),
    )
    bill.validate()  # must not raise
    assert bill.tariff_with_taxes_brl_kwh == Decimal("0.799059")
    assert bill.tariff_without_taxes_brl_kwh == Decimal("0.613030")
    assert bill.wire_b_tariff_brl_kwh == Decimal("0.175126")


# ---------------------------------------------------------------------------
# Tariff plausibility range guard — fail closed on a mis-anchored capture
# (see ADR-056: tariff extraction is positional, not label-anchored).
# ---------------------------------------------------------------------------


def test_bill_rejects_tariff_that_is_actually_a_monetary_total() -> None:
    """A shifted regex capture (e.g. R$ 48,69 instead of R$/kWh 0,175126) must
    fail closed rather than persist a plausible-looking but wrong value."""
    invalid = replace(make_bill(), wire_b_tariff_brl_kwh=Decimal("48.69"))
    with pytest.raises(ValueError, match="plausible tariff range"):
        invalid.validate()


def test_bill_rejects_zero_tariff() -> None:
    invalid = replace(make_bill(), tariff_with_taxes_brl_kwh=Decimal("0"))
    with pytest.raises(ValueError, match="plausible tariff range"):
        invalid.validate()


def test_bill_rejects_tariff_above_plausible_upper_bound() -> None:
    invalid = replace(make_bill(), tariff_without_taxes_brl_kwh=Decimal("5.01"))
    with pytest.raises(ValueError, match="plausible tariff range"):
        invalid.validate()


def test_bill_accepts_tariff_at_plausible_upper_bound() -> None:
    bill = replace(make_bill(), tariff_without_taxes_brl_kwh=Decimal("5"))
    bill.validate()  # must not raise


@pytest.mark.parametrize(
    "with_taxes",
    [Decimal("0.774023"), Decimal("0.799059"), Decimal("0.814841")],
)
def test_bill_accepts_all_three_real_production_tariffs(with_taxes: Decimal) -> None:
    bill = replace(
        make_bill(),
        tariff_with_taxes_brl_kwh=with_taxes,
        tariff_without_taxes_brl_kwh=Decimal("0.613030"),
        wire_b_tariff_brl_kwh=Decimal("0.175126"),
    )
    bill.validate()  # must not raise
