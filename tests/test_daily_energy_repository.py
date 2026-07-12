from datetime import date
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.db.base import Base
from mplacas.db.models import DailyEnergyVersion, DataStatus, Device, Plant
from mplacas.db.repositories.daily_energy import DailyEnergyRepository


@pytest.mark.asyncio
async def test_daily_energy_upsert_is_idempotent_and_versions_changes() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        plant = Plant(name="Usina de teste", installed_power_kwp=Decimal("4.700"))
        device = Device(
            id=uuid.uuid4(),
            plant=plant,
            serial_number="TEST-SN-001",
            model_name="BDM",
        )
        session.add(plant)
        await session.flush()

        repository = DailyEnergyRepository(session)
        first, created = await repository.upsert(
            device_id=device.id,
            production_date=date(2026, 7, 12),
            energy_kwh=Decimal("21.450"),
            status=DataStatus.PROVISIONAL,
        )
        assert created is True

        same, changed = await repository.upsert(
            device_id=device.id,
            production_date=date(2026, 7, 12),
            energy_kwh=Decimal("21.450"),
            status=DataStatus.PROVISIONAL,
        )
        assert changed is False
        assert same.id == first.id

        corrected, changed = await repository.upsert(
            device_id=device.id,
            production_date=date(2026, 7, 12),
            energy_kwh=Decimal("21.630"),
            status=DataStatus.CONSOLIDATED,
        )
        assert changed is True
        assert corrected.energy_kwh == Decimal("21.630")
        assert corrected.status is DataStatus.CONSOLIDATED

        versions = (await session.execute(select(DailyEnergyVersion))).scalars().all()
        assert len(versions) == 1
        assert versions[0].energy_kwh == Decimal("21.450")
        assert versions[0].status is DataStatus.PROVISIONAL

    await engine.dispose()
