from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.db.base import Base
from mplacas.db.models import DataStatus, Device, DailyEnergy, DailyEnergyVersion, Plant
from mplacas.retention.timeseries_service import (
    TimeSeriesRetentionService,
    TimeSeriesRetentionWindows,
)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _set_fk_pragma(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _make_plant(session: AsyncSession) -> uuid.UUID:
    plant = Plant(name="Test Plant")
    session.add(plant)
    await session.flush()
    return plant.id


async def _make_device(session: AsyncSession, plant_id: uuid.UUID) -> uuid.UUID:
    device = Device(plant_id=plant_id, serial_number="SN001")
    session.add(device)
    await session.flush()
    return device.id


async def _make_energy(
    session: AsyncSession,
    device_id: uuid.UUID,
    production_date: date,
) -> DailyEnergy:
    record = DailyEnergy(
        device_id=device_id,
        production_date=production_date,
        energy_kwh=100,
        status=DataStatus.CONSOLIDATED,
    )
    session.add(record)
    await session.flush()
    return record


async def _make_climate(
    session: AsyncSession,
    plant_id: uuid.UUID,
    observation_date: date,
) -> DailyClimateObservationRecord:
    record = DailyClimateObservationRecord(
        plant_id=plant_id,
        observation_date=observation_date,
        source="OPEN_METEO",
    )
    session.add(record)
    await session.flush()
    return record


@pytest.mark.asyncio
async def test_windows_validation() -> None:
    with pytest.raises(ValueError, match="daily_energy_days"):
        TimeSeriesRetentionWindows(daily_energy_days=0)
    with pytest.raises(ValueError, match="climate_observations_days"):
        TimeSeriesRetentionWindows(climate_observations_days=-1)


@pytest.mark.asyncio
async def test_purge_deletes_old_energy_records(session: AsyncSession) -> None:
    plant_id = await _make_plant(session)
    device_id = await _make_device(session, plant_id)
    today = date(2026, 7, 20)
    windows = TimeSeriesRetentionWindows(daily_energy_days=365, climate_observations_days=365)

    old_date = today - timedelta(days=400)
    recent_date = today - timedelta(days=100)

    await _make_energy(session, device_id, old_date)
    await _make_energy(session, device_id, recent_date)

    svc = TimeSeriesRetentionService(session)
    energy_deleted, climate_deleted = await svc.purge(windows=windows, today=today)

    assert energy_deleted == 1
    assert climate_deleted == 0

    remaining = (await session.execute(select(DailyEnergy))).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].production_date == recent_date


@pytest.mark.asyncio
async def test_purge_deletes_old_climate_records(session: AsyncSession) -> None:
    plant_id = await _make_plant(session)
    today = date(2026, 7, 20)
    windows = TimeSeriesRetentionWindows(daily_energy_days=365, climate_observations_days=365)

    old_date = today - timedelta(days=400)
    recent_date = today - timedelta(days=50)

    await _make_climate(session, plant_id, old_date)
    await _make_climate(session, plant_id, recent_date)

    svc = TimeSeriesRetentionService(session)
    energy_deleted, climate_deleted = await svc.purge(windows=windows, today=today)

    assert energy_deleted == 0
    assert climate_deleted == 1

    remaining = (await session.execute(select(DailyClimateObservationRecord))).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].observation_date == recent_date


@pytest.mark.asyncio
async def test_purge_cascades_energy_versions(session: AsyncSession) -> None:
    plant_id = await _make_plant(session)
    device_id = await _make_device(session, plant_id)
    today = date(2026, 7, 20)
    windows = TimeSeriesRetentionWindows(daily_energy_days=365, climate_observations_days=365)

    old_date = today - timedelta(days=500)
    record = await _make_energy(session, device_id, old_date)

    version = DailyEnergyVersion(
        daily_energy_id=record.id,
        energy_kwh=90,
        status=DataStatus.PROVISIONAL,
    )
    session.add(version)
    await session.flush()

    svc = TimeSeriesRetentionService(session)
    energy_deleted, _ = await svc.purge(windows=windows, today=today)

    assert energy_deleted == 1
    versions_left = (await session.execute(select(DailyEnergyVersion))).scalars().all()
    assert len(versions_left) == 0


@pytest.mark.asyncio
async def test_purge_preserves_records_within_window(session: AsyncSession) -> None:
    plant_id = await _make_plant(session)
    device_id = await _make_device(session, plant_id)
    today = date(2026, 7, 20)
    windows = TimeSeriesRetentionWindows(daily_energy_days=1825, climate_observations_days=1825)

    inside_window_date = today - timedelta(days=1000)
    await _make_energy(session, device_id, inside_window_date)
    await _make_climate(session, plant_id, inside_window_date)

    svc = TimeSeriesRetentionService(session)
    energy_deleted, climate_deleted = await svc.purge(windows=windows, today=today)

    assert energy_deleted == 0
    assert climate_deleted == 0


@pytest.mark.asyncio
async def test_purge_empty_tables_returns_zeros(session: AsyncSession) -> None:
    svc = TimeSeriesRetentionService(session)
    energy_deleted, climate_deleted = await svc.purge(today=date(2026, 7, 20))
    assert energy_deleted == 0
    assert climate_deleted == 0
