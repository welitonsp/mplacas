from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.billing.db_models import BillStatus, UtilityBillRecord
from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy, DataStatus, Device, Plant
from mplacas.intelligence.cycle_service import EnergyCycleNotFoundError, analyze_persisted_cycle


@pytest.mark.asyncio
async def test_analyzes_confirmed_bill_with_persisted_daily_energy() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Synthetic plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        device = Device(plant_id=plant.id, serial_number="SYNTHETIC-001")
        session.add(device)
        await session.flush()
        bill = UtilityBillRecord(
            distributor="EQUATORIAL_GO",
            reference_month="2026-06",
            cycle_start=date(2026, 6, 1),
            cycle_end=date(2026, 6, 3),
            billed_days=3,
            imported_kwh=Decimal("8"),
            injected_kwh=Decimal("12"),
            compensated_kwh=Decimal("8"),
            credit_balance_kwh=Decimal("20"),
            total_amount_brl=Decimal("50"),
            public_lighting_brl=Decimal("30"),
            status=BillStatus.CONFIRMED,
            source_hash="a" * 64,
        )
        session.add(bill)
        session.add_all(
            [
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 6, 1),
                    energy_kwh=Decimal("10"),
                    status=DataStatus.CONSOLIDATED,
                ),
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 6, 2),
                    energy_kwh=Decimal("8"),
                    status=DataStatus.PROVISIONAL,
                ),
            ]
        )
        await session.commit()

        result = await analyze_persisted_cycle(
            session,
            bill_id=bill.id,
            plant_id=plant.id,
            expected_production_kwh=Decimal("20"),
        )

        assert result.intelligence.reconciliation.cycle_production_kwh == Decimal("18.000")
        assert result.quality.missing_days == 1
        assert result.quality.provisional_days == 1
        assert result.intelligence.health_score == 89
        codes = {item.code for item in result.intelligence.diagnostics}
        assert codes == {"MISSING_DAILY_DATA", "PROVISIONAL_DAILY_DATA"}

    await engine.dispose()


@pytest.mark.asyncio
async def test_rejects_unconfirmed_bill() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        bill = UtilityBillRecord(
            distributor="EQUATORIAL_GO",
            reference_month="2026-06",
            cycle_start=date(2026, 6, 1),
            cycle_end=date(2026, 6, 1),
            billed_days=1,
            imported_kwh=Decimal("1"),
            injected_kwh=Decimal("0"),
            compensated_kwh=Decimal("0"),
            credit_balance_kwh=Decimal("0"),
            total_amount_brl=Decimal("1"),
            public_lighting_brl=Decimal("0"),
            status=BillStatus.PENDING_REVIEW,
            source_hash="b" * 64,
        )
        session.add(bill)
        await session.commit()

        with pytest.raises(EnergyCycleNotFoundError, match="confirmed bill"):
            await analyze_persisted_cycle(session, bill_id=bill.id, plant_id=bill.id)

    await engine.dispose()
