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
