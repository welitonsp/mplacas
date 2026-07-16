from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.billing.db_models import BillStatus, UtilityBillRecord
from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy, DataStatus, Device, Plant
from mplacas.intelligence.history_service import (
    EnergyHistoryNotFoundError,
    compare_latest_confirmed_cycles,
)
from mplacas.intelligence.trends import TrendDirection


@pytest.mark.asyncio
async def test_compares_two_latest_confirmed_cycles_from_persisted_data() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Synthetic plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        device = Device(plant_id=plant.id, serial_number="TREND-001")
        session.add(device)
        await session.flush()

        previous = UtilityBillRecord(
            plant_id=plant.id,
            distributor="EQUATORIAL_GO",
            reference_month="2026-05",
            cycle_start=date(2026, 5, 1),
            cycle_end=date(2026, 5, 1),
            billed_days=1,
            imported_kwh=Decimal("10"),
            injected_kwh=Decimal("5"),
            compensated_kwh=Decimal("10"),
            credit_balance_kwh=Decimal("20"),
            total_amount_brl=Decimal("60"),
            public_lighting_brl=Decimal("30"),
            status=BillStatus.CONFIRMED,
            source_hash="c" * 64,
        )
        current = UtilityBillRecord(
            plant_id=plant.id,
            distributor="EQUATORIAL_GO",
            reference_month="2026-06",
            cycle_start=date(2026, 6, 1),
            cycle_end=date(2026, 6, 1),
            billed_days=1,
            imported_kwh=Decimal("14"),
            injected_kwh=Decimal("4"),
            compensated_kwh=Decimal("14"),
            credit_balance_kwh=Decimal("18"),
            total_amount_brl=Decimal("66"),
            public_lighting_brl=Decimal("30"),
            status=BillStatus.CONFIRMED,
            source_hash="d" * 64,
        )
        session.add_all([previous, current])
        await session.flush()
        session.add_all(
            [
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 5, 1),
                    energy_kwh=Decimal("20"),
                    status=DataStatus.CONSOLIDATED,
                ),
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 6, 1),
                    energy_kwh=Decimal("15"),
                    status=DataStatus.CONSOLIDATED,
                ),
            ]
        )
        await session.commit()

        result = await compare_latest_confirmed_cycles(session, plant_id=plant.id)

        assert result.comparison.current_reference_month == "2026-06"
        assert result.comparison.previous_reference_month == "2026-05"
        assert result.comparison.production.direction is TrendDirection.DOWN
        assert result.comparison.production.percent_delta == Decimal("-25.0")
        assert result.comparison.imported_energy.direction is TrendDirection.UP
        codes = {item.code for item in result.diagnostics}
        assert "PRODUCTION_TREND_DOWN" in codes
        assert "GRID_IMPORT_TREND_UP" in codes

    await engine.dispose()


@pytest.mark.asyncio
async def test_requires_two_confirmed_cycles() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Synthetic plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.commit()

        with pytest.raises(EnergyHistoryNotFoundError, match="two confirmed"):
            await compare_latest_confirmed_cycles(session, plant_id=plant.id)

    await engine.dispose()
