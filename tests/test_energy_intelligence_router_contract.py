from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from mplacas.billing.models import UtilityBill
from mplacas.intelligence.cycle_service import CycleDataQuality, PersistedCycleIntelligence
from mplacas.intelligence.energy_engine import analyze_energy_cycle
from mplacas.intelligence.router import _serialize


def _bill(*, with_tariff: bool) -> UtilityBill:
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
        tariff_with_taxes_brl_kwh=Decimal("0.85") if with_tariff else None,
        tariff_without_taxes_brl_kwh=Decimal("0.60") if with_tariff else None,
    )


def _persisted_cycle(*, with_tariff: bool) -> PersistedCycleIntelligence:
    intelligence = analyze_energy_cycle(
        bill=_bill(with_tariff=with_tariff),
        cycle_production_kwh=Decimal("300"),
        expected_production_kwh=Decimal("320"),
    )
    return PersistedCycleIntelligence(
        bill_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        plant_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        reference_month="2026-06",
        quality=CycleDataQuality(
            missing_days=0,
            provisional_days=0,
            incomplete_days=0,
            unavailable_days=0,
        ),
        intelligence=intelligence,
    )


def test_serialize_includes_full_financial_shape_when_tariff_registered() -> None:
    payload = _serialize(_persisted_cycle(with_tariff=True))

    indicators = payload["indicators"]
    assert indicators["total_amount_brl"] == "80.21"
    assert indicators["public_lighting_brl"] == "30.21"
    assert indicators["tariff_with_taxes_brl_kwh"] == "0.85"
    assert indicators["tariff_without_taxes_brl_kwh"] == "0.60"
    assert indicators["credit_balance_kwh"] == "63.98"
    # Fórmula: (consumo total estimado * tarifa com impostos) - componente de
    # energia da fatura. Consumo total estimado = 396.000 kWh (ver
    # test_energy_intelligence.py::test_builds_auditable_cycle_indicators),
    # componente de energia = 50.00 BRL.
    # 396.000 * 0.85 - 50.00 = 336.60 - 50.00 = 286.60
    assert indicators["estimated_savings_brl"] == "286.60"
    assert indicators["savings_unavailable_reason"] is None


def test_serialize_omits_savings_without_fabricating_zero_when_tariff_missing() -> None:
    payload = _serialize(_persisted_cycle(with_tariff=False))

    indicators = payload["indicators"]
    assert indicators["tariff_with_taxes_brl_kwh"] is None
    assert indicators["tariff_without_taxes_brl_kwh"] is None
    assert indicators["estimated_savings_brl"] is None
    assert indicators["estimated_savings_brl"] != "0.00"
    assert indicators["savings_unavailable_reason"] == "TARIFF_NOT_AVAILABLE"
