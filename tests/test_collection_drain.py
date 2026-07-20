from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.collection.drain as drain_module
from mplacas.collection.db_models import CollectionTaskRecord, CollectionTaskStatus
from mplacas.collection.drain import drain_collection_queue
from mplacas.collection.job import COLLECTION_TASK_TYPE
from mplacas.collection.queue import CollectionQueueRepository
from mplacas.db import models as _db_models  # noqa: F401  (registra tabela plants)
from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy as DailyEnergyRow
from mplacas.db.models import Device
from mplacas.providers.base import (
    DailyEnergy,
    DeviceOverview,
    ProviderUnavailableError,
    SolarDevice,
    SolarProvider,
)

PLANT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000dd")
PLANT_NAME = "Usina Drain"


class DrainStubProvider(SolarProvider):
    def __init__(self, *, fail: bool) -> None:
        self._fail = fail

    async def list_devices(self) -> list[SolarDevice]:
        return [
            SolarDevice(
                serial_number="SN-D",
                model_name="Micro",
                city="Caldas Novas",
                last_update=None,
            )
        ]

    async def get_overview(self, serial_number: str) -> DeviceOverview:
        raise NotImplementedError

    async def get_daily_energy(
        self,
        serial_number: str,
        start: date,
        end: date,
        *,
        expect_complete: bool = False,
    ) -> list[DailyEnergy]:
        if self._fail:
            raise ProviderUnavailableError("still down")
        return [DailyEnergy(production_date=start, energy_kwh=Decimal("33.3"))]


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_plant_and_task(factory) -> None:
    from mplacas.db.models import Plant

    async with factory() as session:
        await session.execute(
            insert(Plant).values(id=PLANT_ID, name=PLANT_NAME, timezone="America/Sao_Paulo")
        )
        await CollectionQueueRepository(session).enqueue(
            plant_id=PLANT_ID,
            task_type=COLLECTION_TASK_TYPE,
            target_date="2026-07-19",
        )
        await session.commit()


def _patch(monkeypatch, factory, provider: SolarProvider) -> None:
    monkeypatch.setattr(drain_module, "SessionFactory", factory)

    def _build(**_kwargs):
        class _NoopClient:
            async def aclose(self) -> None:
                return None

        return _NoopClient(), provider

    monkeypatch.setattr(drain_module, "build_resilient_nepviewer", _build)
    monkeypatch.setenv("MPLACAS_NEP_ACCOUNT", "operador")
    monkeypatch.setenv("MPLACAS_NEP_PASSWORD", "segredo-de-ambiente")
    from mplacas.core.config import get_settings

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_drain_reprocesses_deferred_day_and_persists(monkeypatch) -> None:
    factory = await _factory()
    await _seed_plant_and_task(factory)
    _patch(monkeypatch, factory, DrainStubProvider(fail=False))

    result = await drain_collection_queue(plant_name=PLANT_NAME)

    assert result.claimed == 1
    assert result.completed == 1
    assert result.failed == 0

    async with factory() as session:
        task_rows = (await session.scalars(select(CollectionTaskRecord))).all()
        assert len(task_rows) == 1
        assert task_rows[0].status is CollectionTaskStatus.COMPLETED

        device = (
            await session.scalars(select(Device).where(Device.serial_number == "SN-D"))
        ).one()
        energy = (
            await session.scalars(
                select(DailyEnergyRow).where(DailyEnergyRow.device_id == device.id)
            )
        ).all()
        assert len(energy) == 1
        assert energy[0].energy_kwh == Decimal("33.3")

    from mplacas.core.config import get_settings

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_drain_reschedules_when_provider_still_failing(monkeypatch) -> None:
    factory = await _factory()
    await _seed_plant_and_task(factory)
    _patch(monkeypatch, factory, DrainStubProvider(fail=True))

    result = await drain_collection_queue(plant_name=PLANT_NAME, max_attempts=3)

    assert result.claimed == 1
    assert result.completed == 0
    assert result.rescheduled == 1

    async with factory() as session:
        task = (await session.scalars(select(CollectionTaskRecord))).one()
        assert task.status is CollectionTaskStatus.PENDING
        assert task.attempt_count == 1
        assert task.last_error_code is not None
        # nada persistido: a transacao da tarefa falhou inteira
        energy = (await session.scalars(select(DailyEnergyRow))).all()
        assert energy == []

    from mplacas.core.config import get_settings

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_drain_marks_failed_after_max_attempts(monkeypatch) -> None:
    factory = await _factory()
    await _seed_plant_and_task(factory)
    _patch(monkeypatch, factory, DrainStubProvider(fail=True))

    from mplacas.core.config import get_settings

    for _ in range(3):
        await drain_collection_queue(plant_name=PLANT_NAME, max_attempts=3)
        # torna a tarefa imediatamente elegivel de novo
        async with factory() as session:
            task = (await session.scalars(select(CollectionTaskRecord))).one()
            if task.status is CollectionTaskStatus.PENDING:
                task.available_at = task.created_at
                await session.commit()

    async with factory() as session:
        task = (await session.scalars(select(CollectionTaskRecord))).one()
        assert task.status is CollectionTaskStatus.FAILED

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_drain_requires_credentials(monkeypatch) -> None:
    factory = await _factory()
    await _seed_plant_and_task(factory)
    monkeypatch.setattr(drain_module, "SessionFactory", factory)
    monkeypatch.delenv("MPLACAS_NEP_ACCOUNT", raising=False)
    monkeypatch.delenv("MPLACAS_NEP_PASSWORD", raising=False)
    from mplacas.core.config import get_settings

    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="NEPViewer credentials"):
        await drain_collection_queue(plant_name=PLANT_NAME)

    get_settings.cache_clear()
