"""Reserva de usina do fabricante: o UNIQUE recusa a segunda usina."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord
from mplacas.providers.db_models import ProviderPlantClaimRecord

PLANT_A = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
PLANT_B = uuid.UUID("00000000-0000-0000-0000-0000000000b2")


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _set_fk_pragma(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add(OrganizationRecord(id=DEFAULT_ORGANIZATION_ID, name="D", slug="d", active=True))
        await db.flush()
        db.add(Plant(id=PLANT_A, organization_id=DEFAULT_ORGANIZATION_ID, name="A"))
        db.add(Plant(id=PLANT_B, organization_id=DEFAULT_ORGANIZATION_ID, name="B"))
        await db.commit()
        yield db
    await engine.dispose()


def _claim(plant_id: uuid.UUID, family: str, serial: str) -> ProviderPlantClaimRecord:
    return ProviderPlantClaimRecord(plant_id=plant_id, provider_family=family, serial_number=serial)


async def test_same_family_and_serial_for_two_plants_is_refused(session: AsyncSession) -> None:
    session.add(_claim(PLANT_A, "GROWATT", "SN-1"))
    await session.commit()

    session.add(_claim(PLANT_B, "GROWATT", "SN-1"))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_same_serial_under_different_families_is_allowed(session: AsyncSession) -> None:
    session.add(_claim(PLANT_A, "GROWATT", "SN-1"))
    session.add(_claim(PLANT_B, "NEPVIEWER", "SN-1"))
    await session.commit()

    rows = (await session.execute(select(ProviderPlantClaimRecord))).scalars().all()
    assert len(rows) == 2


async def test_deleting_the_plant_removes_its_claims(session: AsyncSession) -> None:
    session.add(_claim(PLANT_A, "GROWATT", "SN-1"))
    session.add(_claim(PLANT_B, "GROWATT", "SN-2"))
    await session.commit()

    plant = await session.get(Plant, PLANT_A)
    assert plant is not None
    await session.delete(plant)
    await session.commit()

    remaining = (await session.execute(select(ProviderPlantClaimRecord))).scalars().all()
    assert [claim.serial_number for claim in remaining] == ["SN-2"]
