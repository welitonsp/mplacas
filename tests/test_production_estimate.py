"""Produção estimada para dias sem leitura do inversor (ADR-082)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.climate.history_job import climate_chunks
from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy, DataStatus, Device, Plant
from mplacas.intelligence import cycle_service as _cycle_service  # noqa: F401  (registra tabelas)
from mplacas.intelligence.production_estimate import (
    MINIMUM_REFERENCE_DAYS,
    estimate_cycle_production,
    reference_yield,
)

D0 = date(2025, 9, 1)


def _days(n: int, start: date = D0) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def test_missing_days_are_estimated_from_sun_and_the_plants_own_yield() -> None:
    cycle = _days(10)
    measured = {day: Decimal("20") for day in cycle[:7]}  # 3 dias sem leitura
    sun = {day: Decimal("5") for day in cycle}  # rendimento 4 kWh por kWh/m²
    sun[cycle[9]] = Decimal("6")

    estimate = estimate_cycle_production(
        cycle_days=cycle,
        measured=measured,
        irradiation=sun,
        reference_measured=measured,
        meter_generation_kwh=None,
    )

    assert estimate.yield_kwh_per_kwh_m2 == Decimal("4.0000")
    assert estimate.measured_kwh == Decimal("140")
    assert estimate.estimated_days == 3
    assert estimate.estimated_kwh == Decimal("64.000")  # 5×4 + 5×4 + 6×4
    assert estimate.total_kwh == Decimal("204.000")
    assert estimate.is_estimated


def test_yield_needs_enough_reference_days() -> None:
    few = {day: Decimal("20") for day in _days(MINIMUM_REFERENCE_DAYS - 1)}
    sun = {day: Decimal("5") for day in _days(30)}
    assert reference_yield(few, sun) is None

    estimate = estimate_cycle_production(
        cycle_days=_days(30),
        measured=few,
        irradiation=sun,
        reference_measured=few,
        meter_generation_kwh=None,
    )
    assert estimate.estimated_days == 0
    assert estimate.unestimated_days == 30 - (MINIMUM_REFERENCE_DAYS - 1)
    assert not estimate.is_estimated


def test_day_without_known_sun_is_not_estimated() -> None:
    cycle = _days(8)
    measured = {day: Decimal("20") for day in cycle[:6]}
    sun = {day: Decimal("5") for day in cycle[:7]}  # último dia sem clima

    estimate = estimate_cycle_production(
        cycle_days=cycle,
        measured=measured,
        irradiation=sun,
        reference_measured=measured,
        meter_generation_kwh=None,
    )
    assert estimate.estimated_days == 1
    assert estimate.unestimated_days == 1


def test_production_never_below_what_the_meter_saw_leaving_to_the_grid() -> None:
    # Set/2025 real: inversor registrou 129 kWh, medidor viu 429 kWh injetados.
    cycle = _days(31)
    measured = {day: Decimal("25.8") for day in cycle[:5]}

    estimate = estimate_cycle_production(
        cycle_days=cycle,
        measured=measured,
        irradiation={},
        reference_measured=measured,
        meter_generation_kwh=Decimal("429"),
    )
    assert estimate.measured_kwh == Decimal("129.0")
    assert estimate.meter_floor_kwh == Decimal("300.000")
    assert estimate.total_kwh == Decimal("429.000")
    assert estimate.estimated_days == 0  # o piso não conta como dia estimado


def test_complete_cycle_is_left_untouched() -> None:
    cycle = _days(5)
    measured = {day: Decimal("20") for day in cycle}
    estimate = estimate_cycle_production(
        cycle_days=cycle,
        measured=measured,
        irradiation={day: Decimal("5") for day in cycle},
        reference_measured=measured,
        meter_generation_kwh=Decimal("50"),
    )
    assert estimate.total_kwh == Decimal("100")
    assert not estimate.is_estimated


def test_climate_history_is_split_in_blocks() -> None:
    assert climate_chunks(date(2024, 8, 15), date(2026, 5, 17), 366) == [
        (date(2024, 8, 15), date(2025, 8, 15)),
        (date(2025, 8, 16), date(2026, 5, 17)),
    ]
    with pytest.raises(ValueError):
        climate_chunks(date(2026, 1, 2), date(2026, 1, 1), 366)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


async def test_confirmed_cycle_uses_estimated_production(session: AsyncSession) -> None:
    import uuid

    from mplacas.billing.models import UtilityBill
    from mplacas.billing.read_repository import ConfirmedBill
    from mplacas.intelligence.cycle_service import analyze_confirmed_cycle

    plant = Plant(name="Usina sem internet")
    session.add(plant)
    await session.flush()
    device = Device(plant_id=plant.id, serial_number="SEM-NET-1")
    session.add(device)
    await session.flush()
    cycle = _days(10, date(2025, 9, 10))
    # Vizinhos medidos antes do ciclo + 4 dias medidos no ciclo; 6 sem leitura.
    for day in _days(10, date(2025, 8, 31)) + cycle[:4]:
        session.add(
            DailyEnergy(
                device_id=device.id,
                production_date=day,
                energy_kwh=Decimal("20"),
                status=DataStatus.CONSOLIDATED,
            )
        )
    for day in _days(20, date(2025, 8, 31)):
        session.add(
            DailyClimateObservationRecord(
                plant_id=plant.id,
                observation_date=day,
                irradiation_kwh_m2=Decimal("5"),
                source="OPEN_METEO",
            )
        )
    await session.flush()
    bill = UtilityBill(
        distributor="EQUATORIAL_GO",
        reference_month="2025-09",
        cycle_start=cycle[0],
        cycle_end=cycle[-1],
        billed_days=10,
        imported_kwh=Decimal("30"),
        injected_kwh=Decimal("30"),
        compensated_kwh=Decimal("30"),
        credit_balance_kwh=Decimal("0"),
        total_amount_brl=Decimal("40"),
        public_lighting_brl=Decimal("30"),
        generation_cycle_kwh=Decimal("100"),
        tariff_with_taxes_brl_kwh=Decimal("0.643844"),
        tariff_without_taxes_brl_kwh=Decimal("0.498120"),
    )

    result = await analyze_confirmed_cycle(
        session, confirmed_bill=ConfirmedBill(id=uuid.uuid4(), plant_id=plant.id, bill=bill)
    )

    assert result.quality.missing_days == 6
    assert result.quality.estimated_days == 6
    assert result.quality.estimated_production_kwh == Decimal("120.000")
    # 4×20 medidos + 6×(5×4) estimados = 200 kWh; autoconsumo = 200 − 100 injetados.
    assert result.intelligence.reconciliation.cycle_production_kwh == Decimal("200.000")
    assert result.intelligence.reconciliation.estimated_self_consumption_kwh == Decimal("100.000")
    assert result.intelligence.estimated_savings_brl is not None


def test_complete_cycle_below_meter_is_shown_not_hidden_by_the_floor() -> None:
    # Ciclo sem buraco com inversor abaixo do medidor: divergência, sem piso.
    cycle = _days(5)
    measured = {day: Decimal("10") for day in cycle}
    estimate = estimate_cycle_production(
        cycle_days=cycle,
        measured=measured,
        irradiation={},
        reference_measured=measured,
        meter_generation_kwh=Decimal("80"),
    )
    assert estimate.meter_floor_kwh == Decimal("0")
    assert estimate.total_kwh == Decimal("50")


def test_zero_sun_day_is_not_counted_as_estimated() -> None:
    cycle = _days(8)
    measured = {day: Decimal("20") for day in cycle[:6]}
    sun = {day: Decimal("5") for day in cycle[:6]}
    sun |= {cycle[6]: Decimal("0"), cycle[7]: Decimal("4")}
    estimate = estimate_cycle_production(
        cycle_days=cycle,
        measured=measured,
        irradiation=sun,
        reference_measured=measured,
        meter_generation_kwh=None,
    )
    assert estimate.estimated_days == 1
    assert estimate.unestimated_days == 1
