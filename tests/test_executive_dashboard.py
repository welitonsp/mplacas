from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.billing.db_models import BillStatus, UtilityBillRecord
from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy, DataStatus, Device, Plant
from mplacas.intelligence.executive_service import (
    ExecutiveStatus,
    build_executive_dashboard,
)


async def _setup() -> tuple[object, async_sessionmaker]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_builds_dashboard_with_current_cycle_and_no_trend() -> None:
    engine, factory = await _setup()
    async with factory() as session:
        plant = Plant(name="Synthetic plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        device = Device(plant_id=plant.id, serial_number="SYNTHETIC-EXEC-001")
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

        result = await build_executive_dashboard(session, plant_id=plant.id)

        assert result.status is ExecutiveStatus.HEALTHY
        assert result.current_cycle.reference_month == "2026-06"
        assert result.current_cycle.intelligence.health_score == 100
        assert result.trend is None
        assert "100/100" in result.headline
        assert result.priority_actions == ("Manter o acompanhamento periódico.",)

    await engine.dispose()


@pytest.mark.asyncio
async def test_prioritizes_critical_cycle_and_includes_historical_actions() -> None:
    engine, factory = await _setup()
    async with factory() as session:
        plant = Plant(name="Synthetic plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        device = Device(plant_id=plant.id, serial_number="SYNTHETIC-EXEC-002")
        session.add(device)
        await session.flush()

        previous = UtilityBillRecord(
            plant_id=plant.id,
            distributor="EQUATORIAL_GO",
            reference_month="2026-05",
            cycle_start=date(2026, 5, 1),
            cycle_end=date(2026, 5, 2),
            billed_days=2,
            imported_kwh=Decimal("2"),
            injected_kwh=Decimal("8"),
            compensated_kwh=Decimal("2"),
            credit_balance_kwh=Decimal("10"),
            total_amount_brl=Decimal("40"),
            public_lighting_brl=Decimal("30"),
            status=BillStatus.CONFIRMED,
            source_hash="d" * 64,
        )
        current = UtilityBillRecord(
            plant_id=plant.id,
            distributor="EQUATORIAL_GO",
            reference_month="2026-06",
            cycle_start=date(2026, 6, 1),
            cycle_end=date(2026, 6, 2),
            billed_days=2,
            imported_kwh=Decimal("8"),
            injected_kwh=Decimal("0"),
            compensated_kwh=Decimal("1"),
            credit_balance_kwh=Decimal("1"),
            total_amount_brl=Decimal("80"),
            public_lighting_brl=Decimal("30"),
            status=BillStatus.CONFIRMED,
            source_hash="e" * 64,
        )
        session.add_all([previous, current])
        session.add_all(
            [
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 5, 1),
                    energy_kwh=Decimal("5"),
                    status=DataStatus.CONSOLIDATED,
                ),
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 5, 2),
                    energy_kwh=Decimal("5"),
                    status=DataStatus.CONSOLIDATED,
                ),
            ]
        )
        await session.commit()

        result = await build_executive_dashboard(
            session,
            plant_id=plant.id,
            expected_production_kwh=Decimal("10"),
        )

        assert result.status is ExecutiveStatus.CRITICAL
        assert result.trend is not None
        assert result.current_cycle.reference_month == "2026-06"
        assert result.current_cycle.intelligence.health_score < 60
        assert "atuação prioritária" in result.headline
        assert 1 <= len(result.priority_actions) <= 5
        assert any("backfill" in action.casefold() for action in result.priority_actions)

    await engine.dispose()
