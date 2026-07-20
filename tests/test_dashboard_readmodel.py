from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.billing.db_models import BillStatus, UtilityBillRecord
from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy, DataStatus, Device, Plant
from mplacas.intelligence.dashboard_readmodel import ExecutiveDashboardReadModel


async def _setup() -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed(factory) -> tuple:
    async with factory() as session:
        plant = Plant(name="Cache plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        device = Device(plant_id=plant.id, serial_number="CACHE-EXEC-001")
        session.add(device)
        await session.flush()
        bill = UtilityBillRecord(
            plant_id=plant.id,
            distributor="EQUATORIAL_GO",
            reference_month="2026-06",
            cycle_start=date(2026, 6, 1),
            cycle_end=date(2026, 6, 2),
            billed_days=2,
            imported_kwh=Decimal("4"),
            injected_kwh=Decimal("6"),
            compensated_kwh=Decimal("4"),
            credit_balance_kwh=Decimal("12"),
            total_amount_brl=Decimal("45"),
            public_lighting_brl=Decimal("30"),
            status=BillStatus.CONFIRMED,
            source_hash="c" * 64,
        )
        session.add(bill)
        session.add_all(
            [
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 6, 1),
                    energy_kwh=Decimal("5"),
                    status=DataStatus.CONSOLIDATED,
                ),
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 6, 2),
                    energy_kwh=Decimal("5"),
                    status=DataStatus.CONSOLIDATED,
                ),
            ]
        )
        await session.commit()
        return plant.id, device.id


@pytest.mark.asyncio
async def test_second_read_is_a_cache_hit() -> None:
    factory = await _setup()
    plant_id, _ = await _seed(factory)
    read_model = ExecutiveDashboardReadModel()

    async with factory() as session:
        first = await read_model.get(session, plant_id=plant_id)
    async with factory() as session:
        second = await read_model.get(session, plant_id=plant_id)

    assert read_model.hits == 1
    assert read_model.misses == 1
    assert first == second


@pytest.mark.asyncio
async def test_changing_energy_data_invalidates_cache() -> None:
    factory = await _setup()
    plant_id, device_id = await _seed(factory)
    read_model = ExecutiveDashboardReadModel()

    async with factory() as session:
        await read_model.get(session, plant_id=plant_id)

    # dado de energia muda: consolidacao de uma leitura provisoria do ciclo
    async with factory() as session:
        row = (
            await session.scalars(
                select(DailyEnergy).where(
                    DailyEnergy.device_id == device_id,
                    DailyEnergy.production_date == date(2026, 6, 2),
                )
            )
        ).one()
        row.energy_kwh = Decimal("6")
        row.status = DataStatus.CONSOLIDATED
        await session.commit()

    async with factory() as session:
        await read_model.get(session, plant_id=plant_id)

    # ambos foram miss: o cache nao serviu dashboard obsoleto
    assert read_model.hits == 0
    assert read_model.misses == 2


@pytest.mark.asyncio
async def test_updating_existing_reading_invalidates_cache() -> None:
    factory = await _setup()
    plant_id, device_id = await _seed(factory)
    read_model = ExecutiveDashboardReadModel()

    async with factory() as session:
        await read_model.get(session, plant_id=plant_id)

    # correcao de uma leitura existente (muda soma e updated_at)
    async with factory() as session:
        row = (
            await session.scalars(
                select(DailyEnergy).where(
                    DailyEnergy.device_id == device_id,
                    DailyEnergy.production_date == date(2026, 6, 1),
                )
            )
        ).one()
        row.energy_kwh = Decimal("7")
        await session.commit()

    async with factory() as session:
        await read_model.get(session, plant_id=plant_id)

    assert read_model.hits == 0
    assert read_model.misses == 2


@pytest.mark.asyncio
async def test_different_expected_production_is_a_separate_entry() -> None:
    factory = await _setup()
    plant_id, _ = await _seed(factory)
    read_model = ExecutiveDashboardReadModel()

    async with factory() as session:
        await read_model.get(session, plant_id=plant_id, expected_production_kwh=Decimal("10"))
    async with factory() as session:
        await read_model.get(session, plant_id=plant_id, expected_production_kwh=Decimal("20"))
    async with factory() as session:
        await read_model.get(session, plant_id=plant_id, expected_production_kwh=Decimal("10"))

    # dois parametros distintos -> dois miss; repeticao do primeiro -> hit
    assert read_model.misses == 2
    assert read_model.hits == 1


def test_lru_eviction_respects_max_entries() -> None:
    read_model = ExecutiveDashboardReadModel(max_entries=1)
    assert read_model._max_entries == 1
    with pytest.raises(ValueError, match="max_entries"):
        ExecutiveDashboardReadModel(max_entries=0)
