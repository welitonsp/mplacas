from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

# Plausible upper bound for a R$/kWh tariff field. The parser anchors these
# fields by ordinal column position on the bill line (see ADR-056), which is
# structurally fragile to a distributor layout shift — a shifted column can
# silently capture an unrelated monetary total (e.g. R$ 48,69) instead of the
# R$/kWh rate (e.g. R$ 0,175126). 5 R$/kWh is generous headroom over today's
# real Brazilian residential tariff with taxes (~R$ 0.80/kWh) while still
# catching any order-of-magnitude column mismatch.
_MAX_PLAUSIBLE_TARIFF_BRL_KWH = Decimal("5")


@dataclass(frozen=True, slots=True)
class UtilityBill:
    distributor: str
    reference_month: str
    cycle_start: date
    cycle_end: date
    billed_days: int
    imported_kwh: Decimal
    injected_kwh: Decimal
    compensated_kwh: Decimal
    credit_balance_kwh: Decimal
    total_amount_brl: Decimal
    public_lighting_brl: Decimal = Decimal("0")
    generation_cycle_kwh: Decimal | None = None
    tariff_with_taxes_brl_kwh: Decimal | None = None
    tariff_without_taxes_brl_kwh: Decimal | None = None
    wire_b_tariff_brl_kwh: Decimal | None = None

    def validate(self) -> None:
        if self.cycle_end < self.cycle_start:
            raise ValueError("billing cycle end cannot precede start")
        expected_days = (self.cycle_end - self.cycle_start).days + 1
        if self.billed_days != expected_days:
            raise ValueError("billed days do not match inclusive billing cycle")
        numeric_values = (
            self.imported_kwh,
            self.injected_kwh,
            self.compensated_kwh,
            self.credit_balance_kwh,
            self.total_amount_brl,
            self.public_lighting_brl,
        )
        if any(value < 0 for value in numeric_values):
            raise ValueError("bill values cannot be negative")
        if self.generation_cycle_kwh is not None and self.generation_cycle_kwh < 0:
            raise ValueError("bill values cannot be negative")
        optional_tariff_fields = (
            ("tariff_with_taxes_brl_kwh", self.tariff_with_taxes_brl_kwh),
            ("tariff_without_taxes_brl_kwh", self.tariff_without_taxes_brl_kwh),
            ("wire_b_tariff_brl_kwh", self.wire_b_tariff_brl_kwh),
        )
        if any(value is not None and value < 0 for _, value in optional_tariff_fields):
            raise ValueError("bill values cannot be negative")
        # Fail closed on an implausible tariff rather than persist a value that
        # would silently become a fabricated savings figure downstream — see
        # ADR-056. A shifted regex capture (e.g. a total in R$ instead of a
        # R$/kWh rate) lands well outside this range, so it is rejected here
        # instead of being written to the database as a plausible-looking number.
        for name, value in optional_tariff_fields:
            if value is not None and not (0 < value <= _MAX_PLAUSIBLE_TARIFF_BRL_KWH):
                raise ValueError(
                    f"{name} is outside the plausible tariff range "
                    f"(0, {_MAX_PLAUSIBLE_TARIFF_BRL_KWH}] BRL/kWh: {value}"
                )


@dataclass(frozen=True, slots=True)
class BillingReconciliation:
    cycle_production_kwh: Decimal
    imported_kwh: Decimal
    injected_kwh: Decimal
    estimated_self_consumption_kwh: Decimal
    estimated_total_consumption_kwh: Decimal
    self_consumption_rate_percent: Decimal
    self_sufficiency_rate_percent: Decimal
    # Three-way reconciliation fields — present only when the bill includes
    # generation_cycle_kwh (the concessionária's generation meter reading).
    generation_cycle_kwh: Decimal | None = None
    meter_vs_injection_delta_kwh: Decimal | None = None
    origin_vs_meter_delta_kwh: Decimal | None = None


def reconcile_bill(*, bill: UtilityBill, cycle_production_kwh: Decimal) -> BillingReconciliation:
    bill.validate()
    if cycle_production_kwh < 0:
        raise ValueError("cycle production cannot be negative")
    self_consumption = max(Decimal("0"), cycle_production_kwh - bill.injected_kwh)
    total_consumption = bill.imported_kwh + self_consumption
    self_consumption_rate = (
        self_consumption / cycle_production_kwh * Decimal("100")
        if cycle_production_kwh
        else Decimal("0")
    )
    self_sufficiency_rate = (
        self_consumption / total_consumption * Decimal("100")
        if total_consumption
        else Decimal("0")
    )

    generation_cycle_kwh = bill.generation_cycle_kwh
    if generation_cycle_kwh is not None:
        meter_vs_injection = (generation_cycle_kwh - bill.injected_kwh).quantize(Decimal("0.001"))
        origin_vs_meter = (cycle_production_kwh - generation_cycle_kwh).quantize(Decimal("0.001"))
    else:
        meter_vs_injection = None
        origin_vs_meter = None

    return BillingReconciliation(
        cycle_production_kwh=cycle_production_kwh.quantize(Decimal("0.001")),
        imported_kwh=bill.imported_kwh,
        injected_kwh=bill.injected_kwh,
        estimated_self_consumption_kwh=self_consumption.quantize(Decimal("0.001")),
        estimated_total_consumption_kwh=total_consumption.quantize(Decimal("0.001")),
        self_consumption_rate_percent=self_consumption_rate.quantize(Decimal("0.1")),
        self_sufficiency_rate_percent=self_sufficiency_rate.quantize(Decimal("0.1")),
        generation_cycle_kwh=generation_cycle_kwh,
        meter_vs_injection_delta_kwh=meter_vs_injection,
        origin_vs_meter_delta_kwh=origin_vs_meter,
    )
