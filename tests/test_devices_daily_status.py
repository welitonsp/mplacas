"""Tests for `mplacas.devices.read_service` / `router` (ADR-074, Decision 3).

Covers the taxonomy of per-device yield unavailability
(`NOT_REPORTED` / `NO_IRRADIATION_READING` / `INSUFFICIENT_DEVICE_HISTORY`),
the two correctness restrictions the ADR calls out explicitly — a silent
inverter must still appear (Restriction 1) and `UNKNOWN` must never be
confused with "healthy" via `DeviceYieldAssessment.dropped` (the "armadilha"
of Decision 3) — the always-200 contract, and multi-tenant isolation.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
import mplacas.devices.router as devices_router
from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy, DataStatus, Device, Plant
from mplacas.devices.read_service import (
    INSUFFICIENT_DEVICE_HISTORY_REASON,
    NO_CLIMATE_OBSERVATION_REASON,
    NO_IRRADIATION_READING_REASON,
    NO_PRODUCTION_HISTORY_REASON,
    NOT_REPORTED_REASON,
    get_daily_status,
)
from mplacas.main import app
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord

# --- DB fixtures (unit-level, direct `get_daily_status` calls) ----------------


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _set_fk_pragma(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session_instance:
        yield db_session_instance
    await engine.dispose()


async def _ensure_default_organization(session: AsyncSession) -> uuid.UUID:
    record = await session.get(OrganizationRecord, DEFAULT_ORGANIZATION_ID)
    if record is None:
        record = OrganizationRecord(
            id=DEFAULT_ORGANIZATION_ID, name="Default", slug="default", active=True
        )
        session.add(record)
        await session.flush()
    return record.id


async def _make_plant(session: AsyncSession) -> uuid.UUID:
    organization_id = await _ensure_default_organization(session)
    plant = Plant(name="Test Plant", organization_id=organization_id)
    session.add(plant)
    await session.flush()
    return plant.id


async def _make_device(session: AsyncSession, plant_id: uuid.UUID, serial: str) -> uuid.UUID:
    device = Device(plant_id=plant_id, serial_number=serial)
    session.add(device)
    await session.flush()
    return device.id


async def _add_energy(
    session: AsyncSession, device_id: uuid.UUID, production_date: date, energy_kwh: str
) -> None:
    session.add(
        DailyEnergy(
            device_id=device_id,
            production_date=production_date,
            energy_kwh=Decimal(energy_kwh),
            status=DataStatus.CONSOLIDATED,
        )
    )
    await session.flush()


async def _add_climate(
    session: AsyncSession,
    plant_id: uuid.UUID,
    observation_date: date,
    irradiation_kwh_m2: str | None,
) -> None:
    session.add(
        DailyClimateObservationRecord(
            plant_id=plant_id,
            observation_date=observation_date,
            irradiation_kwh_m2=(
                Decimal(irradiation_kwh_m2) if irradiation_kwh_m2 is not None else None
            ),
            precipitation_mm=Decimal("0"),
            source="OPEN_METEO",
        )
    )
    await session.flush()


async def _seed_history(
    session: AsyncSession,
    plant_id: uuid.UUID,
    device_ids: list[uuid.UUID],
    *,
    before: date,
    days: int = 5,
    irradiation: str = "4.89",
    energy_per_device: str = "9.75",
) -> None:
    for offset in range(1, days + 1):
        history_date = before - timedelta(days=offset)
        await _add_climate(session, plant_id, history_date, irradiation)
        for device_id in device_ids:
            await _add_energy(session, device_id, history_date, energy_per_device)


# --- Happy path -----------------------------------------------------------


async def test_plant_with_devices_reporting_normally(session: AsyncSession) -> None:
    plant_id = await _make_plant(session)
    device_a = await _make_device(session, plant_id, "SN-A")
    device_b = await _make_device(session, plant_id, "SN-B")
    target = date(2026, 8, 11)
    await _seed_history(session, plant_id, [device_a, device_b], before=target)
    await _add_climate(session, plant_id, target, "4.89")
    await _add_energy(session, device_a, target, "9.75")
    await _add_energy(session, device_b, target, "9.75")
    await session.commit()

    result = await get_daily_status(session, plant_id=plant_id)

    assert result.observation_date == target
    assert result.observation_date_unavailable_reason is None
    assert result.irradiation_kwh_m2 == Decimal("4.89")
    assert result.irradiation_unavailable_reason is None
    assert result.device_count == 2
    assert result.reporting_device_count == 2
    assert result.device_normal_threshold == Decimal("0.85")

    serials = [status.assessment.device.serial_number for status in result.devices]
    assert serials == ["SN-A", "SN-B"]
    for status in result.devices:
        assert status.reporting_status == "REPORTED"
        assert status.assessment.device.production_kwh == Decimal("9.75")
        assert status.assessment.relative_to_own_median == Decimal("1")
        assert status.yield_status == "NORMAL"
        assert status.yield_unavailable_reason is None
        assert status.last_reported_date == target


async def test_device_that_reported_zero_is_distinguishable_from_silent(
    session: AsyncSession,
) -> None:
    """A device reporting exactly 0 kWh is REPORTED with production "0", never
    conflated with a device that has no DailyEnergy row at all."""
    plant_id = await _make_plant(session)
    device_id = await _make_device(session, plant_id, "SN-ZERO")
    target = date(2026, 8, 11)
    await _seed_history(session, plant_id, [device_id], before=target)
    await _add_climate(session, plant_id, target, "4.89")
    await _add_energy(session, device_id, target, "0")
    await session.commit()

    result = await get_daily_status(session, plant_id=plant_id)

    status = result.devices[0]
    assert status.reporting_status == "REPORTED"
    assert status.assessment.device.production_kwh == Decimal("0")


# --- Restriction 1: the silent inverter must still show up --------------------


async def test_device_that_did_not_report_still_appears_in_response(
    session: AsyncSession,
) -> None:
    """The most serious failure mode: an inverter with no `DailyEnergy` row
    for the target day must not vanish from the response."""
    plant_id = await _make_plant(session)
    device_reporting = await _make_device(session, plant_id, "SN-REPORTING")
    device_silent = await _make_device(session, plant_id, "SN-SILENT")
    target = date(2026, 8, 11)
    await _seed_history(session, plant_id, [device_reporting, device_silent], before=target)
    await _add_climate(session, plant_id, target, "4.89")
    # device_silent has no DailyEnergy row at all for the target day.
    await _add_energy(session, device_reporting, target, "9.75")
    await session.commit()

    result = await get_daily_status(session, plant_id=plant_id)

    assert result.device_count == 2
    assert result.reporting_device_count == 1
    silent = next(
        status
        for status in result.devices
        if status.assessment.device.serial_number == "SN-SILENT"
    )
    assert silent.reporting_status == "NOT_REPORTED"
    assert silent.assessment.device.production_kwh is None
    assert silent.yield_status == "UNKNOWN"
    assert silent.yield_unavailable_reason == NOT_REPORTED_REASON
    # Never conflated with zero production.
    assert silent.assessment.device.production_kwh != Decimal("0")


async def test_not_reported_wins_over_no_irradiation_when_both_causes_present(
    session: AsyncSession,
) -> None:
    """Overlap: a device that did not report on a day the plant also has no
    irradiance reading for. `_derive_yield_unavailable_reason` checks
    `device.production_kwh is None` before it checks `irradiation is None`,
    so the more specific, device-level cause (`NOT_REPORTED`) must win over
    the plant-level one (`NO_IRRADIATION_READING`). This pins that priority
    order against a future reordering of the `if` chain."""
    plant_id = await _make_plant(session)
    device_reporting = await _make_device(session, plant_id, "SN-REPORTING")
    device_silent = await _make_device(session, plant_id, "SN-SILENT")
    target = date(2026, 8, 11)
    await _seed_history(session, plant_id, [device_reporting, device_silent], before=target)
    # No climate record at all for the target date: the plant itself has no
    # irradiance reading for this day.
    await _add_energy(session, device_reporting, target, "9.75")
    # device_silent has no DailyEnergy row at all for the target day.
    await session.commit()

    result = await get_daily_status(session, plant_id=plant_id)

    assert result.irradiation_kwh_m2 is None
    assert result.irradiation_unavailable_reason == NO_CLIMATE_OBSERVATION_REASON
    silent = next(
        status
        for status in result.devices
        if status.assessment.device.serial_number == "SN-SILENT"
    )
    assert silent.reporting_status == "NOT_REPORTED"
    assert silent.yield_status == "UNKNOWN"
    assert silent.yield_unavailable_reason == NOT_REPORTED_REASON


# --- Taxonomy: NO_IRRADIATION_READING ------------------------------------------


async def test_no_irradiation_reading_yields_unknown_with_reason(session: AsyncSession) -> None:
    plant_id = await _make_plant(session)
    device_id = await _make_device(session, plant_id, "SN-A")
    target = date(2026, 8, 11)
    await _seed_history(session, plant_id, [device_id], before=target)
    # No climate record at all for the target date.
    await _add_energy(session, device_id, target, "9.75")
    await session.commit()

    result = await get_daily_status(session, plant_id=plant_id)

    assert result.irradiation_kwh_m2 is None
    assert result.irradiation_unavailable_reason == NO_CLIMATE_OBSERVATION_REASON

    status = result.devices[0]
    assert status.reporting_status == "REPORTED"
    assert status.yield_status == "UNKNOWN"
    assert status.yield_unavailable_reason == NO_IRRADIATION_READING_REASON
    assert status.assessment.dropped is False


async def test_zero_irradiation_reading_is_treated_as_no_irradiation(
    session: AsyncSession,
) -> None:
    plant_id = await _make_plant(session)
    device_id = await _make_device(session, plant_id, "SN-A")
    target = date(2026, 8, 11)
    await _seed_history(session, plant_id, [device_id], before=target)
    await _add_climate(session, plant_id, target, "0")
    await _add_energy(session, device_id, target, "9.75")
    await session.commit()

    result = await get_daily_status(session, plant_id=plant_id)

    assert result.irradiation_kwh_m2 is None
    assert result.irradiation_unavailable_reason == NO_CLIMATE_OBSERVATION_REASON
    status = result.devices[0]
    assert status.yield_status == "UNKNOWN"
    assert status.yield_unavailable_reason == NO_IRRADIATION_READING_REASON


# --- Taxonomy: INSUFFICIENT_DEVICE_HISTORY, and the "armadilha do dropped" ----


async def test_insufficient_device_history_yields_reason_and_is_never_normal(
    session: AsyncSession,
) -> None:
    """Fewer than MINIMUM_RENDIMENTO_SAMPLE_DAYS (5) days of history: the
    device is reporting and irradiation is present, but there is no median to
    compare against. This is the trap the ADR calls out by name: `dropped` is
    `False` here (nothing to compare, so nothing to flag), and the response
    must say `UNKNOWN`, never `NORMAL`."""
    plant_id = await _make_plant(session)
    device_id = await _make_device(session, plant_id, "SN-A")
    target = date(2026, 8, 11)
    await _seed_history(session, plant_id, [device_id], before=target, days=4)
    await _add_climate(session, plant_id, target, "4.89")
    await _add_energy(session, device_id, target, "9.75")
    await session.commit()

    result = await get_daily_status(session, plant_id=plant_id)

    status = result.devices[0]
    assert status.reporting_status == "REPORTED"
    assert status.assessment.device.rendimento_median is None
    assert status.assessment.relative_to_own_median is None
    # The trap: `dropped` is False here too, and must not be read as healthy.
    assert status.assessment.dropped is False
    assert status.yield_status == "UNKNOWN"
    assert status.yield_status != "NORMAL"
    assert status.yield_unavailable_reason == INSUFFICIENT_DEVICE_HISTORY_REASON


async def test_five_days_of_history_is_enough_for_a_median(session: AsyncSession) -> None:
    """Fixes the MINIMUM_RENDIMENTO_SAMPLE_DAYS threshold: 5 days is enough,
    4 is not (see the test above)."""
    plant_id = await _make_plant(session)
    device_id = await _make_device(session, plant_id, "SN-A")
    target = date(2026, 8, 11)
    await _seed_history(session, plant_id, [device_id], before=target, days=5)
    await _add_climate(session, plant_id, target, "4.89")
    await _add_energy(session, device_id, target, "9.75")
    await session.commit()

    result = await get_daily_status(session, plant_id=plant_id)

    status = result.devices[0]
    assert status.assessment.device.rendimento_median is not None
    assert status.yield_status == "NORMAL"
    assert status.yield_unavailable_reason is None


# --- relative_to_own_median_deviation_percent (ADR-074 correction, P1 review
# of T1c, 2026-08-12) -----------------------------------------------------


async def test_relative_to_own_median_deviation_percent_matches_dropped_ratio(
    session: AsyncSession,
) -> None:
    """A device 20% below its own median (`relative_to_own_median == 0.8`)
    must expose `relative_to_own_median_deviation_percent == -20` — the
    ready-to-render percent that used to be computed in the frontend as
    `(ratio - 1) * 100` (`device-contracts.ts::relativeToMedianPercent`,
    removed in this correction). Chosen so both the ratio and the median
    divide evenly (irradiation 5, history production 10, target production
    8), keeping the assertion exact instead of approximate."""
    plant_id = await _make_plant(session)
    device_id = await _make_device(session, plant_id, "SN-A")
    target = date(2026, 8, 11)
    await _seed_history(
        session,
        plant_id,
        [device_id],
        before=target,
        irradiation="5",
        energy_per_device="10",
    )
    await _add_climate(session, plant_id, target, "5")
    await _add_energy(session, device_id, target, "8")
    await session.commit()

    result = await get_daily_status(session, plant_id=plant_id)

    status = result.devices[0]
    assert status.assessment.relative_to_own_median == Decimal("0.8")
    assert status.assessment.relative_to_own_median_deviation_percent == Decimal("-20")
    assert status.assessment.dropped is True
    assert status.yield_status == "DROPPED"


async def test_relative_to_own_median_deviation_percent_is_null_with_the_ratio(
    session: AsyncSession,
) -> None:
    """Same nullability as `relative_to_own_median` — never invented on its
    own when there is no median to compare against (INSUFFICIENT_DEVICE_HISTORY)."""
    plant_id = await _make_plant(session)
    device_id = await _make_device(session, plant_id, "SN-A")
    target = date(2026, 8, 11)
    await _seed_history(session, plant_id, [device_id], before=target, days=4)
    await _add_climate(session, plant_id, target, "4.89")
    await _add_energy(session, device_id, target, "9.75")
    await session.commit()

    result = await get_daily_status(session, plant_id=plant_id)

    status = result.devices[0]
    assert status.assessment.relative_to_own_median is None
    assert status.assessment.relative_to_own_median_deviation_percent is None


# --- Plant-level extremes: no history at all, no devices at all ---------------


async def test_plant_with_no_production_history_returns_200_with_devices_listed(
    session: AsyncSession,
) -> None:
    plant_id = await _make_plant(session)
    device_id = await _make_device(session, plant_id, "SN-A")
    await session.commit()

    result = await get_daily_status(session, plant_id=plant_id)

    assert result.observation_date is None
    assert result.observation_date_unavailable_reason == NO_PRODUCTION_HISTORY_REASON
    # `_resolve_irradiation` is never called when there is no `observation_date`
    # to resolve it for (the `if observation_date is not None:` guard in
    # `get_daily_status`), so the irradiation fields fall back to the
    # unconditional defaults set before that guard: `None` and
    # `NO_CLIMATE_OBSERVATION_REASON`. Note this reason is the same one used
    # when a day *does* exist but has no matching climate row — here there is
    # no day at all, so the label is a reused default rather than a
    # purpose-built one for this extreme case.
    assert result.irradiation_kwh_m2 is None
    assert result.irradiation_unavailable_reason == NO_CLIMATE_OBSERVATION_REASON
    assert result.device_count == 1
    assert result.reporting_device_count == 0
    status = result.devices[0]
    assert status.assessment.device.device_id == device_id
    assert status.reporting_status == "NOT_REPORTED"
    assert status.yield_status == "UNKNOWN"
    assert status.yield_unavailable_reason == NOT_REPORTED_REASON


async def test_plant_with_no_devices_returns_empty_list_not_404(session: AsyncSession) -> None:
    plant_id = await _make_plant(session)
    await session.commit()

    result = await get_daily_status(session, plant_id=plant_id)

    assert result.device_count == 0
    assert result.reporting_device_count == 0
    assert result.devices == ()


# --- Ordering -------------------------------------------------------------


async def test_devices_are_ordered_by_serial_number_not_insertion_order(
    session: AsyncSession,
) -> None:
    plant_id = await _make_plant(session)
    # Inserted out of alphabetical order on purpose.
    await _make_device(session, plant_id, "SN-Z")
    await _make_device(session, plant_id, "SN-A")
    await _make_device(session, plant_id, "SN-M")
    await session.commit()

    result = await get_daily_status(session, plant_id=plant_id)

    serials = [status.assessment.device.serial_number for status in result.devices]
    assert serials == ["SN-A", "SN-M", "SN-Z"]


# --- Router: always-200 contract + tenant isolation (HTTP level) --------------


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def _seed_router_plant(factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Org A with a plant with one reporting device; org B has no plants."""
    async with factory() as session:
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        plant_id = uuid.uuid4()
        session.add_all(
            [
                OrganizationRecord(
                    id=org_a, name="Org A", slug=f"org-a-{org_a.hex[:8]}", active=True
                ),
                OrganizationRecord(
                    id=org_b, name="Org B", slug=f"org-b-{org_b.hex[:8]}", active=True
                ),
            ]
        )
        session.add(Plant(id=plant_id, organization_id=org_a, name="Plant A"))
        device = Device(plant_id=plant_id, serial_number="SN-A")
        session.add(device)
        await session.flush()
        target = date(2026, 8, 11)
        for offset in range(1, 6):
            history_date = target - timedelta(days=offset)
            session.add(
                DailyClimateObservationRecord(
                    plant_id=plant_id,
                    observation_date=history_date,
                    irradiation_kwh_m2=Decimal("4.89"),
                    precipitation_mm=Decimal("0"),
                    source="OPEN_METEO",
                )
            )
            session.add(
                DailyEnergy(
                    device_id=device.id,
                    production_date=history_date,
                    energy_kwh=Decimal("9.75"),
                    status=DataStatus.CONSOLIDATED,
                )
            )
        session.add(
            DailyClimateObservationRecord(
                plant_id=plant_id,
                observation_date=target,
                irradiation_kwh_m2=Decimal("4.89"),
                precipitation_mm=Decimal("0"),
                source="OPEN_METEO",
            )
        )
        session.add(
            DailyEnergy(
                device_id=device.id,
                production_date=target,
                energy_kwh=Decimal("9.75"),
                status=DataStatus.CONSOLIDATED,
            )
        )
        await session.commit()
        return org_a, org_b, plant_id


@pytest.fixture
def router_setup(monkeypatch):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    import asyncio

    factory, engine = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(devices_router, "SessionFactory", factory)

    org_a, org_b, plant_id = asyncio.run(_seed_router_plant(factory))
    token_a = encode_access_token(uuid.uuid4(), org_a, OperationsRole.ADMIN.value)
    token_b = encode_access_token(uuid.uuid4(), org_b, OperationsRole.ADMIN.value)

    yield plant_id, token_a, token_b

    asyncio.run(engine.dispose())
    get_settings.cache_clear()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_daily_status_endpoint_returns_full_envelope(router_setup) -> None:
    plant_id, token_a, _token_b = router_setup
    client = TestClient(app)

    response = client.get(
        "/devices/daily-status",
        headers=_auth(token_a),
        params={"plant_id": str(plant_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["plant_id"] == str(plant_id)
    assert body["observation_date"] == "2026-08-11"
    assert body["observation_date_unavailable_reason"] is None
    assert body["irradiation_kwh_m2"] == "4.890"
    assert body["device_count"] == 1
    assert body["reporting_device_count"] == 1
    assert body["device_normal_threshold"] == "0.85"
    assert body["units"] == {
        "production": "kWh",
        "irradiation": "kWh/m2",
        "rendimento": "kWh/(kWh/m2)",
        "relative_to_own_median": "ratio",
        "relative_to_own_median_deviation": "percent",
    }
    assert len(body["devices"]) == 1
    device = body["devices"][0]
    assert device["serial_number"] == "SN-A"
    assert device["reporting_status"] == "REPORTED"
    assert device["production_kwh"] == "9.750"
    assert device["yield_status"] == "NORMAL"
    assert device["yield_unavailable_reason"] is None
    # Ready-to-render percent deviation from this inverter's own median — the
    # server-side counterpart of what used to be `(ratio - 1) * 100` in the
    # frontend (ADR-074 correction, P1 review of T1c). `relative_to_own_median`
    # is exactly the median here ("1"), so the deviation is "0".
    assert device["relative_to_own_median"] == "1"
    assert device["relative_to_own_median_deviation_percent"] == "0"


def test_cross_tenant_principal_cannot_see_other_organizations_devices(router_setup) -> None:
    plant_id, _token_a, token_b = router_setup
    client = TestClient(app)

    response = client.get(
        "/devices/daily-status",
        headers=_auth(token_b),
        params={"plant_id": str(plant_id)},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}
