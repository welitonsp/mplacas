"""Coleta por usina com a conexão de cada uma (ADR-091, fase 4)."""

from __future__ import annotations

import base64
import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

import mplacas.collection.drain as drain_module
import mplacas.collection.job as job_module
from mplacas import cloud_jobs
from mplacas.collection.db_models import CollectionTaskStatus
from mplacas.collection.drain import drain_collection_queue
from mplacas.collection.job import COLLECTION_TASK_TYPE
from mplacas.collection.queue import CollectionQueueRepository
from mplacas.core.config import get_settings
from mplacas.core.secret_box import KEY_BYTES, SecretBox
from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy as DailyEnergyRow
from mplacas.db.models import Device, Plant
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord
from mplacas.providers import db_models as _provider_models  # noqa: F401
from mplacas.providers.accounts import NEPVIEWER, ProviderAccountService, ProviderLogin
from mplacas.providers.base import (
    DailyEnergy,
    DeviceOverview,
    ProviderUnavailableError,
    SolarDevice,
    SolarProvider,
)
from mplacas.services.collection import CollectionPlantError, SolarCollectionService

KEY = base64.b64encode(b"\x07" * KEY_BYTES).decode()
PLANT_A = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
PLANT_B = uuid.UUID("00000000-0000-0000-0000-0000000000b2")
PLANT_C = uuid.UUID("00000000-0000-0000-0000-0000000000c3")
DAY = date(2026, 10, 28)
NOW = datetime.fromisoformat("2026-10-29T00:30:00-03:00")
_ENGINES: list[AsyncEngine] = []


@pytest.fixture(autouse=True)
async def _dispose():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    while _ENGINES:
        await _ENGINES.pop().dispose()


class AccountProvider(SolarProvider):
    """Cada conta enxerga só os próprios inversores, como na NEPViewer."""

    def __init__(self, serials: list[str], *, fail: bool = False) -> None:
        self._serials = serials
        self._fail = fail

    async def list_devices(self) -> list[SolarDevice]:
        return [
            SolarDevice(serial_number=s, model_name="Micro", city=None, last_update=None)
            for s in self._serials
        ]

    async def get_overview(self, serial_number: str) -> DeviceOverview:
        raise NotImplementedError

    async def get_daily_energy(
        self, serial_number: str, start: date, end: date, *, expect_complete: bool = False
    ) -> list[DailyEnergy]:
        if self._fail:
            raise ProviderUnavailableError("fora do ar")
        return [DailyEnergy(production_date=start, energy_kwh=Decimal("10.5"))]


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _ENGINES.append(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(OrganizationRecord(id=DEFAULT_ORGANIZATION_ID, name="D", slug="d", active=True))
        await session.flush()
        for plant_id, name in ((PLANT_A, "Casa"), (PLANT_B, "Sítio"), (PLANT_C, "Loja")):
            session.add(Plant(id=plant_id, organization_id=DEFAULT_ORGANIZATION_ID, name=name))
        await session.commit()
    return factory


async def _connect(factory, plant_id: uuid.UUID, login: str, provider: str = NEPVIEWER) -> None:
    async with factory() as session:
        await ProviderAccountService(session, SecretBox.from_keyring(f"1:{KEY}")).save(
            plant_id=plant_id,
            provider=provider,
            credentials=ProviderLogin(login=login, password=f"senha-{login}"),
        )
        await session.commit()


def _patch(
    monkeypatch,
    factory,
    providers: dict[str, AccountProvider],
    seen: list[str],
    brands: dict[str, str] | None = None,
):
    brands = {} if brands is None else brands
    monkeypatch.setenv("MPLACAS_PROVIDER_SECRET_KEYS", f"1:{KEY}")
    get_settings.cache_clear()
    for module in (cloud_jobs, job_module, drain_module):
        monkeypatch.setattr(module, "SessionFactory", factory)

    def _build(provider, *, account: str, password: str, **_kwargs):
        assert password == f"senha-{account}"
        seen.append(account)
        brands[account] = provider

        class _Client:
            async def aclose(self) -> None:
                return None

        return _Client(), providers[account]

    monkeypatch.setattr(job_module, "build_resilient_provider", _build)
    monkeypatch.setattr(drain_module, "build_resilient_provider", _build)


async def _devices_by_plant(factory) -> dict[uuid.UUID, set[str]]:
    async with factory() as session:
        rows = (await session.execute(select(Device.plant_id, Device.serial_number))).all()
    result: dict[uuid.UUID, set[str]] = {}
    for plant_id, serial in rows:
        result.setdefault(plant_id, set()).add(serial)
    return result


async def test_each_plant_collects_only_its_own_inverters(monkeypatch) -> None:
    factory = await _factory()
    await _connect(factory, PLANT_A, "casa@example.com")
    await _connect(factory, PLANT_B, "sitio@example.com")
    seen: list[str] = []
    _patch(
        monkeypatch,
        factory,
        {
            "casa@example.com": AccountProvider(["SN-A1", "SN-A2"]),
            "sitio@example.com": AccountProvider(["SN-B1"]),
        },
        seen,
    )

    await cloud_jobs.run_collection(target_date=DAY.isoformat(), now=NOW)

    assert sorted(seen) == ["casa@example.com", "sitio@example.com"]
    assert await _devices_by_plant(factory) == {
        PLANT_A: {"SN-A1", "SN-A2"},
        PLANT_B: {"SN-B1"},
    }
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(DailyEnergyRow)) == 3
        accounts = await ProviderAccountService(
            session, SecretBox.from_keyring(f"1:{KEY}")
        ).list_active()
    assert all(a.last_success_at is not None for a in accounts)
    assert all(a.last_failure_code is None for a in accounts)


async def test_a_failing_plant_does_not_stop_the_others(monkeypatch) -> None:
    factory = await _factory()
    await _connect(factory, PLANT_A, "casa@example.com")
    await _connect(factory, PLANT_B, "sitio@example.com")
    # SN-A1 já pertence à Loja: a Casa não pode reaproveitá-lo.
    async with factory() as session:
        session.add(Device(plant_id=PLANT_C, provider="NEPVIEWER", serial_number="SN-A1"))
        await session.commit()
    seen: list[str] = []
    _patch(
        monkeypatch,
        factory,
        {
            "casa@example.com": AccountProvider(["SN-A1"]),
            "sitio@example.com": AccountProvider(["SN-B1"]),
        },
        seen,
    )

    with pytest.raises(RuntimeError, match=str(PLANT_A)) as raised:
        await cloud_jobs.run_collection(target_date=DAY.isoformat(), now=NOW)

    assert "senha" not in str(raised.value)
    devices = await _devices_by_plant(factory)
    assert devices[PLANT_B] == {"SN-B1"}
    assert devices[PLANT_C] == {"SN-A1"}
    assert PLANT_A not in devices
    async with factory() as session:
        service = ProviderAccountService(session, SecretBox.from_keyring(f"1:{KEY}"))
        casa = await service.get(PLANT_A)
        sitio = await service.get(PLANT_B)
        # Inversor de outra usina não é falha do fabricante: não vai para a fila.
        due = await CollectionQueueRepository(session).due_ids(task_type=COLLECTION_TASK_TYPE)
    assert casa is not None and casa.last_failure_code == "CollectionPlantError"
    assert sitio is not None and sitio.last_success_at is not None
    assert due == ()


async def test_provider_outage_defers_the_plant_to_the_queue(monkeypatch) -> None:
    factory = await _factory()
    await _connect(factory, PLANT_A, "casa@example.com")
    seen: list[str] = []
    _patch(monkeypatch, factory, {"casa@example.com": AccountProvider(["SN-A1"], fail=True)}, seen)

    await cloud_jobs.run_collection(target_date=DAY.isoformat(), now=NOW)

    async with factory() as session:
        repository = CollectionQueueRepository(session)
        due = await repository.due_ids(task_type=COLLECTION_TASK_TYPE)
        task = await repository.by_id(due[0])
        record = await ProviderAccountService(session, SecretBox.from_keyring(f"1:{KEY}")).get(
            PLANT_A
        )
    assert task is not None and task.plant_id == PLANT_A
    assert record is not None and record.last_failure_code == "ProviderDeferred"


async def test_connected_plants_without_the_keyring_fail_closed(monkeypatch) -> None:
    factory = await _factory()
    await _connect(factory, PLANT_A, "casa@example.com")
    seen: list[str] = []
    _patch(monkeypatch, factory, {}, seen)
    monkeypatch.delenv("MPLACAS_PROVIDER_SECRET_KEYS")
    get_settings.cache_clear()

    with pytest.raises(Exception, match="MPLACAS_PROVIDER_SECRET_KEYS"):
        await cloud_jobs.run_collection(target_date=DAY.isoformat(), now=NOW)
    assert seen == []


async def test_drain_uses_the_connection_of_each_task_plant(monkeypatch) -> None:
    factory = await _factory()
    await _connect(factory, PLANT_A, "casa@example.com")
    async with factory() as session:
        repository = CollectionQueueRepository(session)
        for plant_id in (PLANT_A, PLANT_B):
            await repository.enqueue(
                plant_id=plant_id, task_type=COLLECTION_TASK_TYPE, target_date=DAY.isoformat()
            )
        await session.commit()
    seen: list[str] = []
    _patch(monkeypatch, factory, {"casa@example.com": AccountProvider(["SN-A1"])}, seen)

    result = await drain_collection_queue()

    assert result.claimed == 2
    assert result.completed == 1
    assert result.rescheduled == 1  # Sítio sem conexão: fica na fila
    assert seen == ["casa@example.com"]
    assert await _devices_by_plant(factory) == {PLANT_A: {"SN-A1"}}
    async with factory() as session:
        repository = CollectionQueueRepository(session)
        statuses = {
            (await repository.by_id(task_id)).plant_id: (await repository.by_id(task_id)).status  # type: ignore[union-attr]
            for task_id in await repository.due_ids(
                task_type=COLLECTION_TASK_TYPE, now=datetime.max.replace(tzinfo=NOW.tzinfo)
            )
        }
    assert statuses.get(PLANT_B) is CollectionTaskStatus.PENDING


async def test_service_refuses_an_inverter_that_belongs_to_another_plant() -> None:
    factory = await _factory()
    async with factory() as session:
        session.add(Device(plant_id=PLANT_C, provider="NEPVIEWER", serial_number="SN-X"))
        await session.commit()
        with pytest.raises(CollectionPlantError, match="another plant"):
            await SolarCollectionService(
                session,
                AccountProvider(["SN-X"]),
                provider_name="NEPVIEWER",
                energy_source="NEPVIEWER_V2",
            ).collect(
                plant_id=PLANT_A, start=DAY, end=DAY
            )
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(DailyEnergyRow)) == 0


async def test_drain_with_connections_fails_fast_without_the_keyring(monkeypatch) -> None:
    factory = await _factory()
    await _connect(factory, PLANT_A, "casa@example.com")
    seen: list[str] = []
    _patch(monkeypatch, factory, {}, seen)
    monkeypatch.delenv("MPLACAS_PROVIDER_SECRET_KEYS")
    get_settings.cache_clear()

    with pytest.raises(Exception, match="MPLACAS_PROVIDER_SECRET_KEYS"):
        await drain_collection_queue()
    assert seen == []


async def test_failures_never_carry_login_or_password(monkeypatch, caplog) -> None:
    import logging

    factory = await _factory()
    await _connect(factory, PLANT_A, "casa@example.com")
    async with factory() as session:
        session.add(Device(plant_id=PLANT_C, provider="NEPVIEWER", serial_number="SN-A1"))
        await session.commit()
    seen: list[str] = []
    _patch(monkeypatch, factory, {"casa@example.com": AccountProvider(["SN-A1"])}, seen)

    with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeError) as raised:
        await cloud_jobs.run_collection(target_date=DAY.isoformat(), now=NOW)

    rendered = str(raised.value) + caplog.text
    assert "casa@example.com" not in rendered
    assert "senha-" not in rendered


async def test_outcome_bookkeeping_failure_does_not_stop_other_plants(monkeypatch) -> None:
    factory = await _factory()
    await _connect(factory, PLANT_A, "casa@example.com")
    await _connect(factory, PLANT_B, "sitio@example.com")
    seen: list[str] = []
    _patch(
        monkeypatch,
        factory,
        {
            "casa@example.com": AccountProvider(["SN-A1"]),
            "sitio@example.com": AccountProvider(["SN-B1"]),
        },
        seen,
    )

    async def _broken(*_args, **_kwargs):
        raise OSError("banco fora")

    monkeypatch.setattr(cloud_jobs, "_write_provider_outcome", _broken)

    await cloud_jobs.run_collection(target_date=DAY.isoformat(), now=NOW)

    assert sorted(seen) == ["casa@example.com", "sitio@example.com"]


async def test_task_of_a_plant_that_lost_its_connection_is_retried_then_failed(monkeypatch) -> None:
    """Outra usina continua conectada; a tarefa da usina desconectada não usa
    conta alheia: reagenda e, no limite de tentativas, vira falha."""
    factory = await _factory()
    await _connect(factory, PLANT_A, "casa@example.com")
    async with factory() as session:
        await CollectionQueueRepository(session).enqueue(
            plant_id=PLANT_B, task_type=COLLECTION_TASK_TYPE, target_date=DAY.isoformat()
        )
        await session.commit()
    seen: list[str] = []
    _patch(monkeypatch, factory, {"casa@example.com": AccountProvider(["SN-A1"])}, seen)

    for _ in range(2):
        await drain_collection_queue(max_attempts=2)
        async with factory() as session:
            from mplacas.collection.db_models import CollectionTaskRecord

            task = (await session.scalars(select(CollectionTaskRecord))).one()
            if task.status is CollectionTaskStatus.PENDING:
                task.available_at = task.created_at
                await session.commit()

    async with factory() as session:
        from mplacas.collection.db_models import CollectionTaskRecord

        task = (await session.scalars(select(CollectionTaskRecord))).one()
    assert task.status is CollectionTaskStatus.FAILED
    assert seen == []
    assert await _devices_by_plant(factory) == {}


async def test_each_brand_records_its_own_provider_and_source(monkeypatch) -> None:
    """ADR-092: NEPViewer e Growatt lado a lado, cada uma com a sua marca gravada."""
    from mplacas.db.models import DailyEnergy as EnergyRow

    factory = await _factory()
    await _connect(factory, PLANT_A, "casa@example.com")
    await _connect(factory, PLANT_B, "sitio-growatt", provider="GROWATT")
    seen: list[str] = []
    brands: dict[str, str] = {}
    _patch(
        monkeypatch,
        factory,
        {
            "casa@example.com": AccountProvider(["SN-1"]),
            # Mesmo número em marcas diferentes não colide.
            "sitio-growatt": AccountProvider(["SN-1"]),
        },
        seen,
        brands,
    )

    await cloud_jobs.run_collection(target_date=DAY.isoformat(), now=NOW)

    assert brands == {"casa@example.com": "NEPVIEWER", "sitio-growatt": "GROWATT"}
    async with factory() as session:
        rows = (
            await session.execute(
                select(Device.plant_id, Device.provider, EnergyRow.source).join(
                    EnergyRow, EnergyRow.device_id == Device.id
                )
            )
        ).all()
    assert sorted((str(p), prov, src) for p, prov, src in rows) == sorted(
        [
            (str(PLANT_A), "NEPVIEWER", "NEPVIEWER_V2"),
            (str(PLANT_B), "GROWATT", "GROWATT_CLASSIC"),
        ]
    )
