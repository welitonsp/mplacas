from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy, DataStatus, Device, Plant
from mplacas.intelligence.anomaly_engine import AnomalyLevel
from mplacas.intelligence.anomaly_service import (
    AnomalyDataNotFoundError,
    analyze_recent_persisted_anomalies,
)


@pytest.mark.asyncio
async def test_correlates_persisted_energy_and_climate_and_counts_streak() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Synthetic plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        device = Device(plant_id=plant.id, serial_number="SYNTHETIC-ANOMALY-001")
        session.add(device)
        await session.flush()
        session.add_all(
            [
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 7, 10),
                    energy_kwh=Decimal("9"),
                    status=DataStatus.CONSOLIDATED,
                ),
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 7, 11),
                    energy_kwh=Decimal("4"),
                    status=DataStatus.CONSOLIDATED,
                ),
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 7, 12),
                    energy_kwh=Decimal("3"),
                    status=DataStatus.CONSOLIDATED,
                ),
                DailyClimateObservationRecord(
                    plant_id=plant.id,
                    observation_date=date(2026, 7, 10),
                    irradiation_kwh_m2=Decimal("5.5"),
                    source="SYNTHETIC",
                ),
                DailyClimateObservationRecord(
                    plant_id=plant.id,
                    observation_date=date(2026, 7, 11),
                    irradiation_kwh_m2=Decimal("5.0"),
                    source="SYNTHETIC",
                ),
                DailyClimateObservationRecord(
                    plant_id=plant.id,
                    observation_date=date(2026, 7, 12),
                    irradiation_kwh_m2=Decimal("5.2"),
                    source="SYNTHETIC",
                ),
            ]
        )
        await session.commit()

        result = await analyze_recent_persisted_anomalies(
            session,
            plant_id=plant.id,
            expected_daily_production_kwh=Decimal("10"),
            days=3,
            end_date=date(2026, 7, 12),
        )

        assert result.days_analyzed == 3
        assert result.current_streak_days == 2
        assert result.worst_level is AnomalyLevel.CRITICAL
        assert result.daily[0].assessment.level is AnomalyLevel.NORMAL
        assert result.daily[1].assessment.level is AnomalyLevel.CRITICAL
        assert result.daily[2].assessment.level is AnomalyLevel.CRITICAL

    await engine.dispose()


@pytest.mark.asyncio
async def test_rejects_period_without_persisted_production() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Empty synthetic plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.commit()

        with pytest.raises(AnomalyDataNotFoundError, match="daily production"):
            await analyze_recent_persisted_anomalies(
                session,
                plant_id=plant.id,
                expected_daily_production_kwh=Decimal("10"),
                days=7,
                end_date=date(2026, 7, 12),
            )

    await engine.dispose()
