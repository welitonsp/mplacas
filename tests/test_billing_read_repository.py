import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.billing.db_models import BillStatus, UtilityBillRecord
from mplacas.billing.read_repository import ConfirmedBillReadRepository
from mplacas.core.authorization import PlantScope
from mplacas.db.base import Base
from mplacas.db.models import Plant


def _bill(
    *,
    plant_id: uuid.UUID,
    reference_month: str,
    cycle_end: date,
    status: BillStatus,
    source_hash: str,
    created_at: datetime,
) -> UtilityBillRecord:
    return UtilityBillRecord(
        plant_id=plant_id,
        distributor="EQUATORIAL_GO",
        reference_month=reference_month,
        cycle_start=cycle_end,
        cycle_end=cycle_end,
        billed_days=1,
        imported_kwh=Decimal("10"),
        injected_kwh=Decimal("5"),
        compensated_kwh=Decimal("10"),
        credit_balance_kwh=Decimal("20"),
        total_amount_brl=Decimal("60"),
        public_lighting_brl=Decimal("30"),
        status=status,
        source_hash=source_hash,
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_reads_only_confirmed_bills_in_latest_cycle_order() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Target plant")
        other_plant = Plant(name="Other plant")
        session.add_all([plant, other_plant])
        await session.flush()
        previous = _bill(
            plant_id=plant.id,
            reference_month="2026-05",
            cycle_end=date(2026, 5, 31),
            status=BillStatus.CONFIRMED,
            source_hash="a" * 64,
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
        current = _bill(
            plant_id=plant.id,
            reference_month="2026-06",
            cycle_end=date(2026, 6, 30),
            status=BillStatus.CONFIRMED,
            source_hash="b" * 64,
            created_at=datetime(2026, 7, 1, tzinfo=UTC),
        )
        pending = _bill(
            plant_id=plant.id,
            reference_month="2026-07",
            cycle_end=date(2026, 7, 31),
            status=BillStatus.PENDING_REVIEW,
            source_hash="c" * 64,
            created_at=datetime(2026, 8, 1, tzinfo=UTC),
        )
        other = _bill(
            plant_id=other_plant.id,
            reference_month="2026-08",
            cycle_end=date(2026, 8, 31),
            status=BillStatus.CONFIRMED,
            source_hash="d" * 64,
            created_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
        session.add_all([previous, current, pending, other])
        await session.commit()

        repository = ConfirmedBillReadRepository(session)
        latest = await repository.latest(plant_id=plant.id)
        two_latest = await repository.two_latest(plant_id=plant.id)

        assert latest is not None
        assert latest.id == current.id
        assert latest.plant_id == plant.id
        assert latest.bill.reference_month == "2026-06"
        assert latest.bill.imported_kwh == Decimal("10.000")
        assert tuple(item.id for item in two_latest) == (current.id, previous.id)

    await engine.dispose()


@pytest.mark.asyncio
async def test_reads_confirmed_bill_by_id_with_mandatory_plant_scope() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Target plant")
        other_plant = Plant(name="Other plant")
        session.add_all([plant, other_plant])
        await session.flush()
        confirmed = _bill(
            plant_id=plant.id,
            reference_month="2026-06",
            cycle_end=date(2026, 6, 30),
            status=BillStatus.CONFIRMED,
            source_hash="e" * 64,
            created_at=datetime(2026, 7, 1, tzinfo=UTC),
        )
        session.add(confirmed)
        await session.commit()

        repository = ConfirmedBillReadRepository(session)

        assert await repository.by_id(confirmed.id, plant_id=other_plant.id) is None
        result = await repository.by_id(confirmed.id, plant_id=plant.id)
        assert result is not None
        assert result.id == confirmed.id
        assert result.bill.reference_month == "2026-06"

    await engine.dispose()


@pytest.mark.asyncio
async def test_read_repository_fails_closed_for_principal_outside_plant_scope() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        allowed_plant = Plant(name="Allowed plant")
        denied_plant = Plant(name="Denied plant")
        session.add_all([allowed_plant, denied_plant])
        await session.flush()
        confirmed = _bill(
            plant_id=denied_plant.id,
            reference_month="2026-06",
            cycle_end=date(2026, 6, 30),
            status=BillStatus.CONFIRMED,
            source_hash="f" * 64,
            created_at=datetime(2026, 7, 1, tzinfo=UTC),
        )
        session.add(confirmed)
        await session.commit()

        repository = ConfirmedBillReadRepository(
            session,
            plant_scope=PlantScope.restricted({allowed_plant.id}),
        )

        assert await repository.by_id(confirmed.id, plant_id=denied_plant.id) is None
        assert await repository.latest(plant_id=denied_plant.id) is None
        assert await repository.two_latest(plant_id=denied_plant.id) == ()

    await engine.dispose()
