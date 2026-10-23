from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.billing.read_repository import ConfirmedBill, ConfirmedBillReadRepository
from mplacas.core.authorization import PlantScope, UNRESTRICTED_PLANT_SCOPE
from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.db.models import DailyEnergy, DataStatus, Device
from mplacas.intelligence.production_estimate import estimate_cycle_production
from mplacas.tariffs.service import full_tariff_without_taxes
from mplacas.intelligence.energy_engine import EnergyCycleIntelligence, analyze_energy_cycle


_REFERENCE_WINDOW_DAYS = 30


def _usable_energy_by_day(rows: Sequence[DailyEnergy]) -> dict[date, Decimal]:
    """kWh por dia somando os dispositivos, só nos dias com leitura utilizável.

    Dia em que todos os dispositivos estão UNAVAILABLE conta como sem leitura.
    """
    by_day: dict[date, list[DailyEnergy]] = {}
    for row in rows:
        by_day.setdefault(row.production_date, []).append(row)
    return {
        day: sum((r.energy_kwh for r in day_rows), Decimal("0"))
        for day, day_rows in by_day.items()
        if {r.status for r in day_rows} - {DataStatus.UNAVAILABLE}
    }


def _consolidated_energy_by_day(rows: Sequence[DailyEnergy]) -> dict[date, Decimal]:
    """Só dias inteiramente CONSOLIDATED: referência do rendimento (ADR-082).

    Dias provisórios ou incompletos (parciais) puxariam o rendimento para baixo.
    """
    by_day: dict[date, list[DailyEnergy]] = {}
    for row in rows:
        by_day.setdefault(row.production_date, []).append(row)
    return {
        day: sum((r.energy_kwh for r in day_rows), Decimal("0"))
        for day, day_rows in by_day.items()
        if {r.status for r in day_rows} == {DataStatus.CONSOLIDATED}
    }


async def _irradiation_by_day(
    session: AsyncSession, *, plant_id: uuid.UUID, start: date, end: date
) -> dict[date, Decimal]:
    records = (
        await session.scalars(
            select(DailyClimateObservationRecord).where(
                DailyClimateObservationRecord.plant_id == plant_id,
                DailyClimateObservationRecord.observation_date >= start,
                DailyClimateObservationRecord.observation_date <= end,
                DailyClimateObservationRecord.irradiation_kwh_m2.is_not(None),
            )
        )
    ).all()
    result: dict[date, Decimal] = {}
    for record in records:
        if record.irradiation_kwh_m2 is not None:
            # Mais de uma fonte no mesmo dia: fica a maior (nenhuma é inventada).
            current = result.get(record.observation_date)
            value = Decimal(record.irradiation_kwh_m2)
            result[record.observation_date] = value if current is None else max(current, value)
    return result


class EnergyCycleNotFoundError(LookupError):
    """The requested confirmed bill or plant could not be resolved."""


@dataclass(frozen=True, slots=True)
class CycleDataQuality:
    missing_days: int
    provisional_days: int
    incomplete_days: int
    unavailable_days: int
    # Produção estimada para dias sem leitura (ADR-082). Zero = tudo medido.
    estimated_days: int = 0
    estimated_production_kwh: Decimal = Decimal("0")
    meter_floor_kwh: Decimal = Decimal("0")


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

    # Janela de referência (ADR-082): o ciclo e 30 dias de cada lado, para
    # medir o rendimento da própria usina e estimar os dias sem leitura.
    window_start = bill.cycle_start - timedelta(days=_REFERENCE_WINDOW_DAYS)
    window_end = bill.cycle_end + timedelta(days=_REFERENCE_WINDOW_DAYS)
    window_rows = (
        await session.execute(
            select(DailyEnergy).join(Device).where(
                Device.plant_id == confirmed_bill.plant_id,
                DailyEnergy.production_date >= window_start,
                DailyEnergy.production_date <= window_end,
            )
        )
    ).scalars().all()
    rows = [r for r in window_rows if bill.cycle_start <= r.production_date <= bill.cycle_end]

    by_date: dict[date, list[DailyEnergy]] = {}
    for row in rows:
        by_date.setdefault(row.production_date, []).append(row)

    cycle_days = {
        bill.cycle_start + timedelta(days=offset)
        for offset in range((bill.cycle_end - bill.cycle_start).days + 1)
    }
    missing_days = len(cycle_days.difference(by_date))
    provisional_days = 0
    incomplete_days = 0
    unavailable_days = 0
    production = Decimal("0")
    # Dias com ao menos uma leitura utilizável (não UNAVAILABLE). Contado por
    # dia, sem somar status de dispositivos diferentes duas vezes.
    production_days = 0

    for day_rows in by_date.values():
        statuses = {row.status for row in day_rows}
        if DataStatus.PROVISIONAL in statuses:
            provisional_days += 1
        if DataStatus.INCOMPLETE in statuses:
            incomplete_days += 1
        if DataStatus.UNAVAILABLE in statuses:
            unavailable_days += 1
        if statuses - {DataStatus.UNAVAILABLE}:
            production_days += 1

    estimate = estimate_cycle_production(
        cycle_days=sorted(cycle_days),
        measured=_usable_energy_by_day(rows),
        irradiation=await _irradiation_by_day(
            session, plant_id=confirmed_bill.plant_id, start=window_start, end=window_end
        ),
        reference_measured=_consolidated_energy_by_day(window_rows),
        meter_generation_kwh=bill.generation_cycle_kwh,
    )
    production = estimate.total_kwh
    quality = CycleDataQuality(
        missing_days=missing_days,
        provisional_days=provisional_days,
        incomplete_days=incomplete_days,
        unavailable_days=unavailable_days,
        estimated_days=estimate.estimated_days,
        estimated_production_kwh=estimate.estimated_kwh,
        meter_floor_kwh=estimate.meter_floor_kwh,
    )
    intelligence = analyze_energy_cycle(
        bill=bill,
        cycle_production_kwh=production,
        expected_production_kwh=expected_production_kwh,
        missing_days=missing_days + incomplete_days + unavailable_days,
        provisional_days=provisional_days,
        # Dia estimado pelo sol conta como dia com produção; o piso do medidor
        # sozinho não (sem produção diária, a economia ficaria subestimada).
        production_days=production_days + estimate.estimated_days,
        full_tariff_without_taxes=await full_tariff_without_taxes(
            session,
            distributor=bill.distributor,
            cycle_start=bill.cycle_start,
            cycle_end=bill.cycle_end,
        ),
    )
    return PersistedCycleIntelligence(
        bill_id=confirmed_bill.id,
        plant_id=confirmed_bill.plant_id,
        reference_month=bill.reference_month,
        quality=quality,
        intelligence=intelligence,
    )
