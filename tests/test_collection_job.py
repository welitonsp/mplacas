from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.collection.job as job_module
from mplacas.collection.db_models import CollectionTaskStatus
from mplacas.collection.job import COLLECTION_TASK_TYPE, run_solar_collection
from mplacas.collection.queue import CollectionQueueRepository
from mplacas.db import models as _db_models  # noqa: F401  (registra tabela plants)
from mplacas.db.base import Base
from mplacas.providers.accounts import ProviderLogin
from mplacas.providers.base import (
    DailyEnergy,
    DeviceOverview,
    ProviderUnavailableError,
    SolarDevice,
    SolarProvider,
)

PLANT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000cc")
PLANT_NAME = "Usina Caldas"
CREDENTIALS = ProviderLogin(login="operador", password="segredo-da-usina")
_TEST_ENGINES = []


@pytest.fixture(autouse=True)
async def _dispose_test_engines():
    yield
    while _TEST_ENGINES:
        await _TEST_ENGINES.pop().dispose()


class StubProvider(SolarProvider):
    def __init__(self, *, fail: bool) -> None:
        self._fail = fail

    async def list_devices(self) -> list[SolarDevice]:
        if self._fail:
            raise ProviderUnavailableError("nepviewer down")
        return [
            SolarDevice(
                serial_number="SN-1",
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
        return [DailyEnergy(production_date=start, energy_kwh=Decimal("21.7"))]


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _TEST_ENGINES.append(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_plant(factory) -> None:
    from mplacas.db.models import Plant

    async with factory() as session:
        await session.execute(
            insert(Plant).values(id=PLANT_ID, name=PLANT_NAME, timezone="America/Sao_Paulo")
        )
        await session.commit()


def _patch(monkeypatch, factory, provider: SolarProvider) -> None:
    monkeypatch.setattr(job_module, "SessionFactory", factory)

    def _build(_provider, **_kwargs):
        class _NoopClient:
            async def aclose(self) -> None:
                return None

        return _NoopClient(), provider

    monkeypatch.setattr(job_module, "build_resilient_provider", _build)
    from mplacas.core.config import get_settings

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_collection_job_persists_production_on_success(monkeypatch) -> None:
    factory = await _factory()
    await _seed_plant(factory)
    _patch(monkeypatch, factory, StubProvider(fail=False))

    result = await run_solar_collection(
        target_date=date(2026, 7, 19),
        plant_id=PLANT_ID,
        credentials=CREDENTIALS,
        provider="NEPVIEWER",
    )

    assert result is not None
    assert result.records_received == 1

    async with factory() as session:
        due = await CollectionQueueRepository(session).due_ids(task_type=COLLECTION_TASK_TYPE)
    assert due == ()  # sucesso não enfileira retry

    from mplacas.core.config import get_settings

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_collection_job_defers_to_queue_on_provider_failure(monkeypatch) -> None:
    factory = await _factory()
    await _seed_plant(factory)
    _patch(monkeypatch, factory, StubProvider(fail=True))

    result = await run_solar_collection(
        target_date=date(2026, 7, 19),
        plant_id=PLANT_ID,
        credentials=CREDENTIALS,
        provider="NEPVIEWER",
    )

    assert result is None  # falha não explode; defere

    async with factory() as session:
        repository = CollectionQueueRepository(session)
        due = await repository.due_ids(task_type=COLLECTION_TASK_TYPE)
        assert len(due) == 1
        task = await repository.by_id(due[0])
    assert task is not None
    assert task.plant_id == PLANT_ID
    assert task.target_date == "2026-07-19"
    assert task.status is CollectionTaskStatus.PENDING

    from mplacas.core.config import get_settings

    get_settings.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", ["rate", "auth"])
async def test_blocked_or_refused_login_is_queued_for_later_and_reported(
    monkeypatch, error
) -> None:
    """ADR-092: depois de bloqueio (Growatt 507) ou senha recusada, o dia só
    volta à fila daqui a 1 h — nunca na drenagem logo em seguida — e a falha
    sobe para a conexão aparecer como falha."""
    from datetime import UTC, datetime, timedelta

    from mplacas.providers.base import ProviderAuthError, ProviderRateLimitedError

    exc = ProviderRateLimitedError("507") if error == "rate" else ProviderAuthError("recusado")

    class BlockedProvider(StubProvider):
        async def list_devices(self):
            raise exc

    factory = await _factory()
    await _seed_plant(factory)
    _patch(monkeypatch, factory, BlockedProvider(fail=False))

    with pytest.raises(type(exc)):
        await run_solar_collection(
            target_date=date(2026, 7, 19),
            plant_id=PLANT_ID,
            credentials=CREDENTIALS,
            provider="GROWATT",
        )

    async with factory() as session:
        repository = CollectionQueueRepository(session)
        assert await repository.due_ids(task_type=COLLECTION_TASK_TYPE) == ()
        later = datetime.now(UTC) + timedelta(minutes=61)
        due_later = await repository.due_ids(task_type=COLLECTION_TASK_TYPE, now=later)
    assert len(due_later) == 1
