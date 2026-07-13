from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.climate.collection_service import (
    ClimateCollectionError,
    collect_and_persist_daily_climate,
)
from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.climate.models import DailyClimateObservation
from mplacas.db.base import Base
from mplacas.db.models import Plant


class FakeClimateProvider:
    def __init__(self, observations: tuple[DailyClimateObservation, ...]) -> None:
        self.observations = observations
        self.calls = 0

    async def daily_observations(
        self,
        *,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
    ) -> tuple[DailyClimateObservation, ...]:
        self.calls += 1
        assert latitude == pytest.approx(-17.744)
        assert longitude == pytest.approx(-48.625)
        return self.observations


def _observations(irradiation: str = "5.100") -> tuple[DailyClimateObservation, ...]:
    return (
        DailyClimateObservation(
            observation_date=date(2026, 7, 12),
            irradiation_kwh_m2=Decimal(irradiation),
            cloud_cover_percent=Decimal("35.0"),
            precipitation_mm=Decimal("0.0"),
            source="SYNTHETIC_WEATHER",
        ),
        DailyClimateObservation(
            observation_date=date(2026, 7, 13),
            irradiation_kwh_m2=Decimal("4.200"),
            cloud_cover_percent=Decimal("55.0"),
            precipitation_mm=Decimal("1.2"),
            source="SYNTHETIC_WEATHER",
        ),
    )


@pytest.mark.asyncio
async def test_collects_and_upserts_climate_observations_idempotently() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(
            name="Synthetic plant",
            latitude=Decimal("-17.744000"),
            longitude=Decimal("-48.625000"),
        )
        session.add(plant)
        await session.commit()

        first_provider = FakeClimateProvider(_observations())
        first = await collect_and_persist_daily_climate(
            session,
            plant_id=plant.id,
            provider=first_provider,
            start_date=date(2026, 7, 12),
            end_date=date(2026, 7, 13),
        )
        await session.commit()

        assert first.received == 2
        assert first.persistence.inserted == 2
        assert first.persistence.updated == 0

        second = await collect_and_persist_daily_climate(
            session,
            plant_id=plant.id,
            provider=FakeClimateProvider(_observations()),
            start_date=date(2026, 7, 12),
            end_date=date(2026, 7, 13),
        )
        assert second.persistence.unchanged == 2

        third = await collect_and_persist_daily_climate(
            session,
            plant_id=plant.id,
            provider=FakeClimateProvider(_observations("5.900")),
            start_date=date(2026, 7, 12),
            end_date=date(2026, 7, 13),
        )
        await session.commit()
        assert third.persistence.updated == 1

        count = await session.scalar(
            select(func.count()).select_from(DailyClimateObservationRecord)
        )
        assert count == 2

    await engine.dispose()


@pytest.mark.asyncio
async def test_requires_plant_coordinates_before_collection() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Plant without location")
        session.add(plant)
        await session.commit()

        with pytest.raises(ClimateCollectionError, match="coordinates"):
            await collect_and_persist_daily_climate(
                session,
                plant_id=plant.id,
                provider=FakeClimateProvider(tuple()),
                start_date=date(2026, 7, 13),
                end_date=date(2026, 7, 13),
            )

    await engine.dispose()
