from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from mplacas.billing.models import UtilityBill
from mplacas.intelligence.energy_engine import DiagnosticSeverity, analyze_energy_cycle


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


def test_rejects_invalid_quality_counters() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        analyze_energy_cycle(
            bill=_bill(),
            cycle_production_kwh=Decimal("300"),
            missing_days=-1,
        )
