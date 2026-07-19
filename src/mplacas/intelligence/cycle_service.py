from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.billing.read_repository import ConfirmedBill, ConfirmedBillReadRepository
from mplacas.core.authorization import PlantScope, UNRESTRICTED_PLANT_SCOPE
from mplacas.db.models import DailyEnergy, DataStatus, Device
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


async def analyze_persisted_cycle(
    session: AsyncSession,
    *,
    bill_id: uuid.UUID,
    plant_id: uuid.UUID,
    expected_production_kwh: Decimal | None = None,
    plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
) -> PersistedCycleIntelligence:
    confirmed_bill = await ConfirmedBillReadRepository(
        session,
        plant_scope=plant_scope,
    ).by_id(
        bill_id,
        plant_id=plant_id,
    )
    if confirmed_bill is None:
        raise EnergyCycleNotFoundError("confirmed bill not found for plant")
    return await analyze_confirmed_cycle(
        session,
        confirmed_bill=confirmed_bill,
        expected_production_kwh=expected_production_kwh,
    )


async def analyze_confirmed_cycle(
    session: AsyncSession,
    *,
    confirmed_bill: ConfirmedBill,
    expected_production_kwh: Decimal | None = None,
) -> PersistedCycleIntelligence:
    bill = confirmed_bill.bill

    rows = (
        await session.execute(
            select(DailyEnergy).join(Device).where(
                Device.plant_id == confirmed_bill.plant_id,
                DailyEnergy.production_date >= bill.cycle_start,
                DailyEnergy.production_date <= bill.cycle_end,
            )
        )
    ).scalars().all()

    by_date: dict[object, list[DailyEnergy]] = {}
    for row in rows:
        by_date.setdefault(row.production_date, []).append(row)

    cycle_days = {
        bill.cycle_start + timedelta(days=offset)
        for offset in range(bill.billed_days)
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
        bill=bill,
        cycle_production_kwh=production,
        expected_production_kwh=expected_production_kwh,
        missing_days=missing_days + incomplete_days + unavailable_days,
        provisional_days=provisional_days,
    )
    return PersistedCycleIntelligence(
        bill_id=confirmed_bill.id,
        plant_id=confirmed_bill.plant_id,
        reference_month=bill.reference_month,
        quality=quality,
        intelligence=intelligence,
    )
