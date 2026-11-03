"""Produção pela leitura do total da madrugada (ADR-098)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

import mplacas.collection.job as job_module
import mplacas.collection.meter as meter_module
from mplacas.core.config import get_settings
from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy, DataStatus, MeterReading, Plant
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord
from mplacas.providers import db_models as _provider_models  # noqa: F401
from mplacas.providers.accounts import GROWATT_TOKEN, ProviderLogin
from mplacas.providers.base import ProviderAuthError
from mplacas.providers.growatt.openapi import GrowattOpenApiClient
from mplacas.providers.resilient import ResilientSolarProvider
from mplacas.services.collection import SolarCollectionService

PLANT = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
SERIAL = "GW-PLANT-1383141"
_ENGINES: list[AsyncEngine] = []


@pytest.fixture(autouse=True)
async def _dispose():
    get_settings.cache_clear()
    yield
    while _ENGINES:
        await _ENGINES.pop().dispose()


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _ENGINES.append(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(OrganizationRecord(id=DEFAULT_ORGANIZATION_ID, name="D", slug="d", active=True))
        await session.flush()
        session.add(Plant(id=PLANT, organization_id=DEFAULT_ORGANIZATION_ID, name="Casa"))
        await session.commit()
    return factory


async def _record(factory, total: str, day: date):
    async with factory() as session:
        result = await SolarCollectionService(
            session, None, provider_name=GROWATT_TOKEN, energy_source="GROWATT_TOTAL_DIFF"
        ).record_meter_totals(plant_id=PLANT, totals={SERIAL: Decimal(total)}, covered_date=day)
        await session.commit()
    return result


async def _energy(factory) -> dict[date, Decimal]:
    async with factory() as session:
        rows = (await session.scalars(select(DailyEnergy))).all()
    return {row.production_date: row.energy_kwh for row in rows}


@pytest.mark.asyncio
async def test_two_nights_in_a_row_give_the_production_of_the_day_between() -> None:
    factory = await _factory()
    first = await _record(factory, "900.0", date(2026, 11, 3))
    assert first.records_received == 0  # primeira noite: nada inventado
    second = await _record(factory, "921.4", date(2026, 11, 4))
    assert second.records_received == 1
    assert await _energy(factory) == {date(2026, 11, 4): Decimal("21.400")}
    async with factory() as session:
        row = await session.scalar(select(DailyEnergy))
    assert row.status == DataStatus.CONSOLIDATED
    assert row.source == "GROWATT_TOTAL_DIFF"


@pytest.mark.asyncio
async def test_a_missing_night_never_becomes_a_made_up_day() -> None:
    factory = await _factory()
    await _record(factory, "900", date(2026, 11, 3))
    await _record(factory, "950", date(2026, 11, 5))  # pulou a noite do dia 4
    assert await _energy(factory) == {}


@pytest.mark.asyncio
async def test_total_going_down_is_not_production_and_rereading_is_idempotent() -> None:
    factory = await _factory()
    await _record(factory, "900", date(2026, 11, 3))
    await _record(factory, "10", date(2026, 11, 4))  # troca de inversor/zeramento
    assert await _energy(factory) == {}
    await _record(factory, "15", date(2026, 11, 5))
    await _record(factory, "15", date(2026, 11, 5))
    assert await _energy(factory) == {date(2026, 11, 5): Decimal("5.000")}
    async with factory() as session:
        assert len((await session.scalars(select(MeterReading))).all()) == 3


def _token_client(total: str = "921.4") -> GrowattOpenApiClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/plant/list":
            data = {"count": 1, "plants": [{"plant_id": 1383141, "total_energy": total}]}
            return httpx.Response(200, json={"error_code": 0, "data": data})
        return httpx.Response(
            200, json={"error_code": 10011, "error_msg": "error_permission_denied"}
        )

    return GrowattOpenApiClient(token="t", transport=httpx.MockTransport(handler))


def _patch(monkeypatch, factory, client):
    monkeypatch.setattr(job_module, "SessionFactory", factory)
    monkeypatch.setattr(meter_module, "SessionFactory", factory)
    monkeypatch.setattr(
        job_module,
        "build_resilient_provider",
        lambda *a, **k: (client, ResilientSolarProvider(client)),
    )


def test_covered_date_is_the_day_already_closed_by_the_sun() -> None:
    def at(text: str):
        return meter_module.covered_date(datetime.fromisoformat(text))

    assert at("2026-11-03T21:00:00-03:00") == date(2026, 11, 3)
    assert at("2026-11-04T03:07:00-03:00") == date(2026, 11, 3)
    assert at("2026-11-04T16:25:00-03:00") is None  # o ciclo do GitHub cai de dia
    assert at("2026-11-04T19:29:00-03:00") is None


@pytest.mark.asyncio
async def test_job_in_the_dark_reads_the_total_when_history_is_denied(monkeypatch) -> None:
    factory = await _factory()
    await _record(factory, "900.0", date(2026, 11, 2))
    _patch(monkeypatch, factory, _token_client())
    result = await job_module.run_solar_collection(
        target_date=date(2026, 11, 2),
        plant_id=PLANT,
        credentials=ProviderLogin(login="token-x", password="t"),
        provider=GROWATT_TOKEN,
        now=datetime.fromisoformat("2026-11-04T03:07:00-03:00"),
    )
    assert result is not None and result.records_received == 1
    assert await _energy(factory) == {date(2026, 11, 3): Decimal("21.400")}


@pytest.mark.asyncio
async def test_job_in_daylight_is_not_a_connection_failure(monkeypatch) -> None:
    factory = await _factory()
    _patch(monkeypatch, factory, _token_client())
    result = await job_module.run_solar_collection(
        target_date=date(2026, 11, 3),
        plant_id=PLANT,
        credentials=ProviderLogin(login="token-x", password="t"),
        provider=GROWATT_TOKEN,
        now=datetime.fromisoformat("2026-11-04T16:25:00-03:00"),
    )
    assert result is not None and result.records_received == 0
    assert await _energy(factory) == {}
    async with factory() as session:
        assert (await session.scalars(select(MeterReading))).all() == []


@pytest.mark.asyncio
async def test_history_from_the_brand_is_never_overwritten() -> None:
    factory = await _factory()
    await _record(factory, "900", date(2026, 11, 3))
    async with factory() as session:
        from mplacas.db.models import Device

        device = await session.scalar(select(Device))
        session.add(
            DailyEnergy(
                device_id=device.id,
                production_date=date(2026, 11, 4),
                energy_kwh=Decimal("20.0"),
                status=DataStatus.CONSOLIDATED,
                source="GROWATT_OPENAPI_V1",
            )
        )
        await session.commit()
    await _record(factory, "921.4", date(2026, 11, 4))
    assert await _energy(factory) == {date(2026, 11, 4): Decimal("20.000")}


@pytest.mark.asyncio
async def test_meter_readings_job_skips_daylight_without_touching_the_database(
    monkeypatch,
) -> None:
    from mplacas import cloud_jobs

    def boom():
        raise AssertionError("não deveria abrir o banco de dia")

    monkeypatch.setattr(cloud_jobs, "SessionFactory", boom)
    await cloud_jobs.run_meter_readings(now=datetime.fromisoformat("2026-11-04T12:00:00-03:00"))


@pytest.mark.asyncio
async def test_token_refused_on_the_list_is_still_an_auth_failure(monkeypatch) -> None:
    factory = await _factory()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error_code": 10011, "error_msg": "denied"})

    client = GrowattOpenApiClient(token="t", transport=httpx.MockTransport(handler))
    _patch(monkeypatch, factory, client)
    queued: list[date] = []

    async def _enqueue(**kwargs):
        queued.append(kwargs["target_date"])

    monkeypatch.setattr(job_module, "_enqueue_retry", _enqueue)
    with pytest.raises(ProviderAuthError):
        await job_module.run_solar_collection(
            target_date=date(2026, 11, 3),
            plant_id=PLANT,
            credentials=ProviderLogin(login="token-x", password="t"),
            provider=GROWATT_TOKEN,
            now=datetime.fromisoformat("2026-11-04T03:07:00-03:00"),
        )
    assert queued == [date(2026, 11, 3)]


@pytest.mark.asyncio
async def test_meter_totals_skip_unreadable_totals_never_zero() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        plants = [{"plant_id": 1, "total_energy": "1234.5"}, {"plant_id": 2}]
        return httpx.Response(200, json={"error_code": 0, "data": {"count": 2, "plants": plants}})

    client = GrowattOpenApiClient(token="t", transport=httpx.MockTransport(handler))
    totals = await client.meter_totals()
    await client.aclose()
    assert totals == {"GW-PLANT-1": Decimal("1234.5")}


@pytest.mark.asyncio
async def test_unchanged_total_is_not_a_zero_day() -> None:
    """A lista da Growatt atualiza com atraso: total igual não é 0 kWh confirmado."""
    factory = await _factory()
    await _record(factory, "900", date(2026, 11, 3))
    await _record(factory, "900", date(2026, 11, 4))
    assert await _energy(factory) == {}


@pytest.mark.asyncio
async def test_meter_readings_job_reads_token_plants_in_the_dark(monkeypatch) -> None:
    import base64

    import mplacas.providers.factory as factory_module
    from mplacas import cloud_jobs
    from mplacas.core.secret_box import KEY_BYTES, SecretBox
    from mplacas.providers.accounts import ProviderAccountService

    key = base64.b64encode(b"\x07" * KEY_BYTES).decode()
    monkeypatch.setenv("MPLACAS_PROVIDER_SECRET_KEYS", f"1:{key}")
    get_settings.cache_clear()
    factory = await _factory()
    async with factory() as session:
        await ProviderAccountService(session, SecretBox.from_keyring(f"1:{key}")).save(
            plant_id=PLANT,
            provider=GROWATT_TOKEN,
            credentials=ProviderLogin(login="token-x", password="tok"),
        )
        await session.commit()
    await _record(factory, "900.0", date(2026, 11, 2))
    monkeypatch.setattr(cloud_jobs, "SessionFactory", factory)
    monkeypatch.setattr(meter_module, "SessionFactory", factory)
    monkeypatch.setattr(factory_module, "build_client", lambda *a, **k: _token_client())
    await cloud_jobs.run_meter_readings(now=datetime.fromisoformat("2026-11-03T21:10:00-03:00"))
    assert await _energy(factory) == {date(2026, 11, 3): Decimal("21.400")}
