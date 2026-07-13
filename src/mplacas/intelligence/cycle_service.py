from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.billing.db_models import BillStatus, UtilityBillRecord
from mplacas.billing.models import UtilityBill
from mplacas.db.models import DailyEnergy, DataStatus, Device, Plant
from mplacas.intelligence.energy_engine import EnergyCycleIntelligence, analyze_energy_cycle


class EnergyCycleNotFoundError(LookupError):
    """The requested confirmed bill or plant could not be resolved."""


@dataclass(frozen=True, slots=True)
class CycleDataQuality:
    missing_days: int
    provisional_days: int
    incomplete_days: int
    unavailable_days: int


@dataclass(frozen=True, slots=True)
class PersistedCycleIntelligence:
    bill_id: uuid.UUID
    plant_id: uuid.UUID
    reference_month: str
    quality: CycleDataQuality
    intelligence: EnergyCycleIntelligence


def _to_domain_bill(record: UtilityBillRecord) -> UtilityBill:
    return UtilityBill(
        distributor=record.distributor,
        reference_month=record.reference_month,
        cycle_start=record.cycle_start,
        cycle_end=record.cycle_end,
        billed_days=record.billed_days,
        imported_kwh=record.imported_kwh,
        injected_kwh=record.injected_kwh,
        compensated_kwh=record.compensated_kwh,
        credit_balance_kwh=record.credit_balance_kwh,
        total_amount_brl=record.total_amount_brl,
        public_lighting_brl=record.public_lighting_brl,
    )


async def _legacy_bill_matches_only_plant(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
) -> bool:
    plants = list((await session.execute(select(Plant.id).limit(2))).scalars())
    return plants == [plant_id]


async def analyze_persisted_cycle(
    session: AsyncSession,
    *,
    bill_id: uuid.UUID,
    plant_id: uuid.UUID,
    expected_production_kwh: Decimal | None = None,
) -> PersistedCycleIntelligence:
    bill_record = await session.get(UtilityBillRecord, bill_id)
    if bill_record is None or bill_record.status is not BillStatus.CONFIRMED:
        raise EnergyCycleNotFoundError("confirmed bill not found for plant")
    if bill_record.plant_id is None:
        if not await _legacy_bill_matches_only_plant(session, plant_id=plant_id):
            raise EnergyCycleNotFoundError("legacy bill is not safely scoped to plant")
    elif bill_record.plant_id != plant_id:
        raise EnergyCycleNotFoundError("confirmed bill not found for plant")

    rows = (
        await session.execute(
            select(DailyEnergy).join(Device).where(
                Device.plant_id == plant_id,
                DailyEnergy.production_date >= bill_record.cycle_start,
                DailyEnergy.production_date <= bill_record.cycle_end,
            )
        )
    ).scalars().all()

    by_date: dict[object, list[DailyEnergy]] = {}
    for row in rows:
        by_date.setdefault(row.production_date, []).append(row)

    cycle_days = {
        bill_record.cycle_start + timedelta(days=offset)
        for offset in range(bill_record.billed_days)
    }
    missing_days = len(cycle_days.difference(by_date))
    provisional_days = 0
    incomplete_days = 0
    unavailable_days = 0
    production = Decimal("0")

    for day_rows in by_date.values():
        statuses = {row.status for row in day_rows}
        if DataStatus.PROVISIONAL in statuses:
            provisional_days += 1
        if DataStatus.INCOMPLETE in statuses:
            incomplete_days += 1
        if DataStatus.UNAVAILABLE in statuses:
            unavailable_days += 1
        production += sum((row.energy_kwh for row in day_rows), Decimal("0"))

    quality = CycleDataQuality(
        missing_days=missing_days,
        provisional_days=provisional_days,
        incomplete_days=incomplete_days,
        unavailable_days=unavailable_days,
    )
    intelligence = analyze_energy_cycle(
        bill=_to_domain_bill(bill_record),
        cycle_production_kwh=production,
        expected_production_kwh=expected_production_kwh,
        missing_days=missing_days + incomplete_days + unavailable_days,
        provisional_days=provisional_days,
    )
    return PersistedCycleIntelligence(
        bill_id=bill_record.id,
        plant_id=plant_id,
        reference_month=bill_record.reference_month,
        quality=quality,
        intelligence=intelligence,
    )
