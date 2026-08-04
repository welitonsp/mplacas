from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.db.base import Base
from mplacas.db.models import Plant


@pytest.mark.asyncio
async def test_investment_amount_check_constraint_rejects_zero_and_negative() -> None:
    """ADR-067, Etapa B: ``ck_plants_investment_amount_positive`` allows NULL and
    strictly positive values, and rejects zero and negative CAPEX -- mirroring the
    same nullable-or-positive convention already used by ``installed_power_kwp`` and
    ``ac_capacity_kw`` on ``Plant``."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Zero investment plant", investment_amount_brl=Decimal("0"))
        session.add(plant)
        with pytest.raises(IntegrityError, match="ck_plants_investment_amount_positive"):
            await session.flush()
        await session.rollback()

    async with factory() as session:
        plant = Plant(
            name="Negative investment plant", investment_amount_brl=Decimal("-1000.00")
        )
        session.add(plant)
        with pytest.raises(IntegrityError, match="ck_plants_investment_amount_positive"):
            await session.flush()
        await session.rollback()

    await engine.dispose()


@pytest.mark.asyncio
async def test_investment_amount_check_constraint_accepts_null_and_positive() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        unset_plant = Plant(name="Unregistered investment plant")
        registered_plant = Plant(
            name="Registered investment plant",
            investment_amount_brl=Decimal("48000.00"),
        )
        session.add_all([unset_plant, registered_plant])
        await session.commit()

        assert unset_plant.investment_amount_brl is None
        assert registered_plant.investment_amount_brl == Decimal("48000.00")

    await engine.dispose()
