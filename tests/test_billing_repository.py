from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.billing.db_models import BillStatus
from mplacas.billing.models import UtilityBill
from mplacas.billing.repository import UtilityBillRepository
from mplacas.db.base import Base
from mplacas.db.models import Plant


@pytest.mark.asyncio
async def test_bill_requires_human_confirmation_and_is_idempotent() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    bill = UtilityBill(
        distributor="EQUATORIAL_GO",
        reference_month="2026-06",
        cycle_start=date(2026, 5, 18),
        cycle_end=date(2026, 6, 16),
        billed_days=30,
        imported_kwh=Decimal("278"),
        injected_kwh=Decimal("182"),
        compensated_kwh=Decimal("278"),
        credit_balance_kwh=Decimal("63.98"),
        total_amount_brl=Decimal("80.21"),
        public_lighting_brl=Decimal("30.21"),
    )
    async with factory() as session:
        plant = Plant(name="Synthetic plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        repository = UtilityBillRepository(session)
        first = await repository.create_pending(
            bill,
            plant_id=plant.id,
            source_text="synthetic bill text",
        )
        second = await repository.create_pending(
            bill,
            plant_id=plant.id,
            source_text="synthetic bill text",
        )
        assert first.id == second.id
        assert first.plant_id == plant.id
        assert first.status is BillStatus.PENDING_REVIEW
        await repository.confirm(first)
        assert first.status is BillStatus.CONFIRMED
        assert first.reviewed_at is not None
        with pytest.raises(ValueError, match="only pending"):
            await repository.reject(first)
        await session.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_pending_persists_tariff_fields() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    bill = UtilityBill(
        distributor="EQUATORIAL_GO",
        reference_month="2026-06",
        cycle_start=date(2026, 5, 18),
        cycle_end=date(2026, 6, 16),
        billed_days=30,
        imported_kwh=Decimal("278"),
        injected_kwh=Decimal("182"),
        compensated_kwh=Decimal("278"),
        credit_balance_kwh=Decimal("63.98"),
        total_amount_brl=Decimal("80.21"),
        public_lighting_brl=Decimal("30.21"),
        tariff_with_taxes_brl_kwh=Decimal("0.799059"),
        tariff_without_taxes_brl_kwh=Decimal("0.613030"),
        wire_b_tariff_brl_kwh=Decimal("0.175126"),
    )
    async with factory() as session:
        plant = Plant(name="Synthetic plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        repository = UtilityBillRepository(session)
        record = await repository.create_pending(
            bill,
            plant_id=plant.id,
            source_text="synthetic bill text with tariff",
        )
        assert record.tariff_with_taxes_brl_kwh == Decimal("0.799059")
        assert record.tariff_without_taxes_brl_kwh == Decimal("0.613030")
        assert record.wire_b_tariff_brl_kwh == Decimal("0.175126")
        await session.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_pending_persists_absent_tariff_fields_as_none() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    bill = UtilityBill(
        distributor="EQUATORIAL_GO",
        reference_month="2026-06",
        cycle_start=date(2026, 5, 18),
        cycle_end=date(2026, 6, 16),
        billed_days=30,
        imported_kwh=Decimal("278"),
        injected_kwh=Decimal("182"),
        compensated_kwh=Decimal("278"),
        credit_balance_kwh=Decimal("63.98"),
        total_amount_brl=Decimal("80.21"),
        public_lighting_brl=Decimal("30.21"),
    )
    async with factory() as session:
        plant = Plant(name="Synthetic plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        repository = UtilityBillRepository(session)
        record = await repository.create_pending(
            bill,
            plant_id=plant.id,
            source_text="synthetic bill text without tariff",
        )
        assert record.tariff_with_taxes_brl_kwh is None
        assert record.tariff_without_taxes_brl_kwh is None
        assert record.wire_b_tariff_brl_kwh is None
        await session.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_same_source_is_idempotent_per_plant_not_globally() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    bill = UtilityBill(
        distributor="EQUATORIAL_GO",
        reference_month="2026-06",
        cycle_start=date(2026, 5, 18),
        cycle_end=date(2026, 6, 16),
        billed_days=30,
        imported_kwh=Decimal("278"),
        injected_kwh=Decimal("182"),
        compensated_kwh=Decimal("278"),
        credit_balance_kwh=Decimal("63.98"),
        total_amount_brl=Decimal("80.21"),
        public_lighting_brl=Decimal("30.21"),
    )
    async with factory() as session:
        first_plant = Plant(name="First source owner")
        second_plant = Plant(name="Second source owner")
        session.add_all([first_plant, second_plant])
        await session.flush()
        repository = UtilityBillRepository(session)

        first = await repository.create_pending(
            bill, source_text="shared source", plant_id=first_plant.id
        )
        repeated = await repository.create_pending(
            bill, source_text="shared source", plant_id=first_plant.id
        )
        second = await repository.create_pending(
            bill, source_text="shared source", plant_id=second_plant.id
        )

        assert repeated.id == first.id
        assert second.id != first.id
        assert second.source_hash == first.source_hash
        await session.commit()
    await engine.dispose()
