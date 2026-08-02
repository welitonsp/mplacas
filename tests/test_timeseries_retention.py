from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.db.base import Base
from mplacas.db.models import DataStatus, Device, DailyEnergy, DailyEnergyVersion, Plant
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord
from mplacas.photovoltaic.db_models import (
    DailyPvLossAssessmentRecord,
    DailyPvPerformanceRecord,
    DailySolarModelResultRecord,
    SeasonalPvBaselineRecord,
)
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


async def _ensure_default_organization(session: AsyncSession) -> uuid.UUID:
    record = await session.get(OrganizationRecord, DEFAULT_ORGANIZATION_ID)
    if record is None:
        record = OrganizationRecord(
            id=DEFAULT_ORGANIZATION_ID,
            name="Default",
            slug="default",
            active=True,
        )
        session.add(record)
        await session.flush()
    return record.id


async def _make_plant(session: AsyncSession) -> uuid.UUID:
    organization_id = await _ensure_default_organization(session)
    plant = Plant(name="Test Plant", organization_id=organization_id)
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


async def _make_solar_result(
    session: AsyncSession,
    plant_id: uuid.UUID,
    observation_date: date,
) -> DailySolarModelResultRecord:
    record = DailySolarModelResultRecord(
        plant_id=plant_id,
        observation_date=observation_date,
        climate_source="OPEN_METEO",
        model_version="TEST_V1",
        latitude_degrees=-17.744,
        array_tilt_degrees=20,
        array_azimuth_degrees=0,
        module_technology="MONOCRYSTALLINE_SILICON",
        ghi_kwh_m2=5,
        poa_irradiation_kwh_m2=6,
        beam_horizontal_kwh_m2=3,
        diffuse_horizontal_kwh_m2=2,
        extraterrestrial_horizontal_kwh_m2=8,
        ambient_temperature_c=25,
        cell_temperature_c=40,
        temperature_coefficient_per_c=-0.004,
        temperature_factor=0.94,
        temperature_adjusted_poa_equivalent_kwh_m2=5.64,
        quality_flags=["TEST"],
        assumptions_json={"test": "true"},
    )
    session.add(record)
    await session.flush()
    return record


async def _make_performance_result(
    session: AsyncSession,
    plant_id: uuid.UUID,
    observation_date: date,
) -> DailyPvPerformanceRecord:
    record = DailyPvPerformanceRecord(
        plant_id=plant_id,
        observation_date=observation_date,
        solar_model_version="TEST_SOLAR_V1",
        performance_model_version="TEST_PR_V1",
        climate_source="OPEN_METEO",
        performance_ratio_nature="TEST_PR",
        availability_nature="TEST_PROXY",
        uncertainty_percent=None,
        uncertainty_nature="NOT_QUANTIFIED",
        measured_energy_kwh=4,
        dc_capacity_kwp=1,
        poa_irradiation_kwh_m2=5,
        final_yield_kwh_per_kwp=4,
        reference_yield_hours=5,
        performance_ratio=0.8,
        temperature_corrected_performance_ratio=None,
        reporting_availability_ratio=1,
        reporting_device_count=1,
        configured_device_count=1,
        reporting_capacity_kwp=1,
        configured_device_capacity_kwp=1,
        data_quality_status="FINAL",
        quality_flags=["TEST"],
        units_json={"performance_ratio": "ratio"},
        assumptions_json={"test": "true"},
    )
    session.add(record)
    await session.flush()
    return record


async def _make_baseline_result(
    session: AsyncSession,
    plant_id: uuid.UUID,
    observation_date: date,
) -> SeasonalPvBaselineRecord:
    record = SeasonalPvBaselineRecord(
        plant_id=plant_id,
        observation_date=observation_date,
        baseline_model_version="TEST_BASELINE_V1",
        performance_model_version="TEST_PR_V1",
        metric_nature="TEST_PR",
        clear_sky_index_nature="TEST_P90",
        season_key=f"MONTH_{observation_date.month:02d}",
        reference_start_date=observation_date - timedelta(days=500),
        reference_end_date=observation_date - timedelta(days=135),
        baseline_sample_count=12,
        baseline_excluded_count=1,
        comparison_start_date=observation_date - timedelta(days=7),
        comparison_sample_count=7,
        clear_sky_poa_p90_kwh_m2=6,
        target_clear_sky_index=0.9,
        baseline_median_performance_ratio=0.8,
        baseline_mad=0.01,
        baseline_q10=0.78,
        baseline_q90=0.82,
        comparison_median_performance_ratio=0.76,
        degradation_percent=-5,
        annualized_degradation_percent=-4,
        degradation_status="DEGRADED",
        quality_flags=["TEST"],
        assumptions_json={"test": "true"},
    )
    session.add(record)
    await session.flush()
    return record


async def _make_loss_assessment(
    session: AsyncSession,
    plant_id: uuid.UUID,
    observation_date: date,
) -> DailyPvLossAssessmentRecord:
    record = DailyPvLossAssessmentRecord(
        plant_id=plant_id,
        observation_date=observation_date,
        category="COMMUNICATION",
        evidence_level="NOT_DETECTED",
        taxonomy_model_version="TEST_LOSS_V1",
        performance_model_version="TEST_PR_V1",
        baseline_model_version=None,
        estimated_loss_percent=None,
        evidence_codes=["TEST"],
        limitation=None,
        assumptions_json={"test": "true"},
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
    await _make_solar_result(session, plant_id, old_date)
    await _make_solar_result(session, plant_id, recent_date)
    await _make_performance_result(session, plant_id, old_date)
    await _make_performance_result(session, plant_id, recent_date)
    await _make_baseline_result(session, plant_id, old_date)
    await _make_baseline_result(session, plant_id, recent_date)
    await _make_loss_assessment(session, plant_id, old_date)
    await _make_loss_assessment(session, plant_id, recent_date)

    svc = TimeSeriesRetentionService(session)
    energy_deleted, climate_deleted = await svc.purge(windows=windows, today=today)

    assert energy_deleted == 0
    assert climate_deleted == 1

    remaining = (await session.execute(select(DailyClimateObservationRecord))).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].observation_date == recent_date
    solar_remaining = (
        await session.execute(select(DailySolarModelResultRecord))
    ).scalars().all()
    assert len(solar_remaining) == 1
    assert solar_remaining[0].observation_date == recent_date
    performance_remaining = (
        await session.execute(select(DailyPvPerformanceRecord))
    ).scalars().all()
    assert len(performance_remaining) == 1
    assert performance_remaining[0].observation_date == recent_date
    baseline_remaining = (
        await session.execute(select(SeasonalPvBaselineRecord))
    ).scalars().all()
    assert len(baseline_remaining) == 1
    assert baseline_remaining[0].observation_date == recent_date
    loss_remaining = (
        await session.execute(select(DailyPvLossAssessmentRecord))
    ).scalars().all()
    assert len(loss_remaining) == 1
    assert loss_remaining[0].observation_date == recent_date


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
