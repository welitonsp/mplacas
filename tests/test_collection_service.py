from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy, DataStatus, Device, Plant
from mplacas.providers.base import DailyEnergy as ProviderDailyEnergy
from mplacas.providers.base import DeviceOverview, SolarDevice, SolarProvider
from mplacas.services.collection import SolarCollectionService


class FakeProvider(SolarProvider):
    async def list_devices(self) -> list[SolarDevice]:
        return [
            SolarDevice(
                serial_number="SN-001",
                model_name="BDM-800",
                city="Goiânia",
                last_update=datetime(2026, 7, 12, 18, 0),
            )
        ]

    async def get_overview(self, serial_number: str) -> DeviceOverview:
        return DeviceOverview(
            serial_number=serial_number,
            current_power_w=Decimal("0"),
            today_energy_kwh=Decimal("21.630"),
            last_update=None,
            status="Normal",
        )

    async def get_daily_energy(
        self,
        serial_number: str,
        start: date,
        end: date,
        *,
        expect_complete: bool = False,
    ) -> list[ProviderDailyEnergy]:
        assert serial_number == "SN-001"
        return [
            ProviderDailyEnergy(date(2026, 7, 11), Decimal("20.100")),
            ProviderDailyEnergy(date(2026, 7, 12), Decimal("21.630")),
        ]


@pytest.mark.asyncio
async def test_collection_is_transactional_and_idempotent() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        service = SolarCollectionService(session, FakeProvider())
        first = await service.collect(
            plant_name="Usina residencial",
            start=date(2026, 7, 11),
            end=date(2026, 7, 12),
            consolidate_through=date(2026, 7, 11),
        )
        second = await service.collect(
            plant_name="Usina residencial",
            start=date(2026, 7, 11),
            end=date(2026, 7, 12),
            consolidate_through=date(2026, 7, 11),
        )

        assert first.devices_seen == 1
        assert first.records_received == 2
        assert first.records_changed == 2
        assert second.records_changed == 0

        plant_count = await session.scalar(select(func.count()).select_from(Plant))
        device_count = await session.scalar(select(func.count()).select_from(Device))
        energy_rows = (await session.execute(select(DailyEnergy))).scalars().all()

        assert plant_count == 1
        assert device_count == 1
        assert len(energy_rows) == 2
        statuses = {row.production_date: row.status for row in energy_rows}
        assert statuses[date(2026, 7, 11)] is DataStatus.CONSOLIDATED
        assert statuses[date(2026, 7, 12)] is DataStatus.PROVISIONAL

    await engine.dispose()
