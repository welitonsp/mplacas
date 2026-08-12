"""Tests for `mplacas.alerts.production_alert`.

The four "table" tests near the bottom of this file encode the acceptance
criteria from real production data (Caldas Novas/GO): 10/06, 24/06, 22/07
and 31/07. They are the contract this module must never violate — see the
module docstring for the two governing rules (irradiation over cloud cover,
never invent a cause without evidence).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mplacas.alerts.ledger import InMemoryAlertDeliveryLedger
from mplacas.alerts.models import AlertSeverity
from mplacas.alerts.production_alert import (
    ProductionAlertDataNotFoundError,
    ProductionAlertMetrics,
    ProductionAlertReason,
    assess_production_alert,
    gather_production_alert_metrics,
    render_production_alert,
    send_production_alert,
)
from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy, DataStatus, Device, Plant
from mplacas.devices.metrics import DeviceProductionMetrics
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord

EXPECTED_DAILY_PRODUCTION = Decimal("18.7")


# --- DB fixtures --------------------------------------------------------------


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
    async with factory() as db_session:
        yield db_session
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
    cloud_cover_percent: str | None = None,
) -> None:
    session.add(
        DailyClimateObservationRecord(
            plant_id=plant_id,
            observation_date=observation_date,
            irradiation_kwh_m2=(
                Decimal(irradiation_kwh_m2) if irradiation_kwh_m2 is not None else None
            ),
            cloud_cover_percent=(
                Decimal(cloud_cover_percent) if cloud_cover_percent is not None else None
            ),
            precipitation_mm=Decimal("0"),
            source="OPEN_METEO",
        )
    )
    await session.flush()


class RecordingProvider:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send_message(self, text, *, parse_mode=None, reply_markup=None) -> None:
        self.calls.append({"text": text, "parse_mode": parse_mode, "reply_markup": reply_markup})


async def _seed_history(
    session: AsyncSession,
    plant_id: uuid.UUID,
    device_ids: list[uuid.UUID],
    *,
    before: date,
    days: int = 30,
    irradiation: str = "4.89",
    energy_per_device: str = "9.75",
) -> None:
    """Seed `days` of unremarkable history ending the day before `before`.

    Chosen so that, with a two-device plant, the plant-level rendimento
    median lands on ~3.9 (matches `tests/test_daily_digest.py`'s baseline)
    and the irradiation median lands on 4.89 kWh/m^2 — the real Caldas
    Novas figure quoted in the acceptance table.
    """
    for offset in range(1, days + 1):
        history_date = before - timedelta(days=offset)
        await _add_climate(session, plant_id, history_date, irradiation, "20")
        for device_id in device_ids:
            await _add_energy(session, device_id, history_date, energy_per_device)


async def test_device_baselines_use_constant_query_count(session: AsyncSession) -> None:
    """Adding inverters must not add one historical query per inverter."""
    plant_id = await _make_plant(session)
    device_ids = [
        await _make_device(session, plant_id, f"SN-{index:02d}") for index in range(8)
    ]
    target = date(2026, 8, 1)
    await _seed_history(session, plant_id, device_ids, before=target, days=5)
    await _add_climate(session, plant_id, target, "4.89", "20")
    for device_id in device_ids:
        await _add_energy(session, device_id, target, "9.75")
    await session.commit()

    select_count = 0

    def _count_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
        nonlocal select_count
        if statement.lstrip().upper().startswith("SELECT"):
            select_count += 1

    sync_engine = session.bind.sync_engine
    event.listen(sync_engine, "before_cursor_execute", _count_selects)
    try:
        metrics = await gather_production_alert_metrics(
            session,
            plant_id=plant_id,
            target_date=target,
            expected_daily_production_kwh=EXPECTED_DAILY_PRODUCTION,
        )
    finally:
        event.remove(sync_engine, "before_cursor_execute", _count_selects)

    assert len(metrics.devices) == 8
    assert all(device.rendimento_median is not None for device in metrics.devices)
    # Nine reads total: plant production/climate/history, device roster/day,
    # and two batched device-history reads. This ceiling stays fixed as the
    # number of inverters grows.
    assert select_count <= 9


# --- Acceptance table: real Caldas Novas days ---------------------------------


async def test_10_06_both_inverters_drop_is_not_blamed_on_weather(session: AsyncSession) -> None:
    """74% clouds, irradiation normal (4.75 vs 4.89 median) -> real equipment alert."""
    plant_id = await _make_plant(session)
    device_a = await _make_device(session, plant_id, "SN-A")
    device_b = await _make_device(session, plant_id, "SN-B")
    target = date(2026, 6, 10)
    await _seed_history(session, plant_id, [device_a, device_b], before=target)

    # Both inverters ran well below their historical baseline, matching the
    # 11.8 kWh actually produced on 10/06.
    await _add_energy(session, device_a, target, "5.9")
    await _add_energy(session, device_b, target, "5.9")
    await _add_climate(session, plant_id, target, "4.75", "74")

    metrics = await gather_production_alert_metrics(
        session,
        plant_id=plant_id,
        target_date=target,
        expected_daily_production_kwh=EXPECTED_DAILY_PRODUCTION,
    )
    assert metrics.irradiation_median_kwh_m2 == Decimal("4.89")
    assert metrics.irradiation_sample_days == 30

    assessment = assess_production_alert(metrics)

    assert assessment.should_alert is True
    assert assessment.reason is ProductionAlertReason.REAL_DROP_SET
    assert assessment.low_irradiation is False

    content = render_production_alert(metrics, assessment, consecutive_days=1)
    # Rule 2: the high cloud cover must never be shown as a false excuse.
    assert "74" not in content.text
    assert "não foi o tempo" in content.text
    assert "4,75 kWh/m²" in content.text


async def test_24_06_low_irradiation_with_above_normal_yield_is_not_alerted(
    session: AsyncSession,
) -> None:
    """67% clouds, irradiation 57% of median, yield +27% above normal -> no alert."""
    plant_id = await _make_plant(session)
    device_a = await _make_device(session, plant_id, "SN-A")
    device_b = await _make_device(session, plant_id, "SN-B")
    target = date(2026, 6, 24)
    await _seed_history(session, plant_id, [device_a, device_b], before=target)

    await _add_energy(session, device_a, target, "6.6")
    await _add_energy(session, device_b, target, "6.6")
    await _add_climate(session, plant_id, target, "2.79", "67")

    metrics = await gather_production_alert_metrics(
        session,
        plant_id=plant_id,
        target_date=target,
        expected_daily_production_kwh=EXPECTED_DAILY_PRODUCTION,
    )
    assert metrics.production_kwh == Decimal("13.2")

    assessment = assess_production_alert(metrics)

    assert assessment.low_irradiation is True
    assert assessment.should_alert is False
    assert assessment.reason is ProductionAlertReason.NONE


async def test_22_07_single_inverter_drop_is_flagged_by_device(session: AsyncSession) -> None:
    """18% clouds, irradiation normal -> only the underperforming inverter alerts."""
    plant_id = await _make_plant(session)
    device_bad = await _make_device(session, plant_id, "86c41d70")
    device_good = await _make_device(session, plant_id, "SN-GOOD")
    target = date(2026, 7, 22)
    await _seed_history(session, plant_id, [device_bad, device_good], before=target)

    # Bad inverter down ~21% from its own baseline, good inverter unaffected.
    await _add_energy(session, device_bad, target, "7.40")
    await _add_energy(session, device_good, target, "8.20")
    await _add_climate(session, plant_id, target, "4.70", "18")

    metrics = await gather_production_alert_metrics(
        session,
        plant_id=plant_id,
        target_date=target,
        expected_daily_production_kwh=EXPECTED_DAILY_PRODUCTION,
    )

    assessment = assess_production_alert(metrics)

    assert assessment.should_alert is True
    assert assessment.reason is ProductionAlertReason.REAL_DROP_SINGLE
    assert assessment.low_irradiation is False

    dropped = [device for device in assessment.devices if device.dropped]
    assert len(dropped) == 1
    assert dropped[0].device.serial_number == "86c41d70"

    content = render_production_alert(metrics, assessment, consecutive_days=1)
    assert "86c41d70" in content.text
    assert "SN-GOOD" in content.text
    # A single inverter dropping is equipment/local-shade, not general dirt —
    # the copy must point the user at the assistência técnica.
    assert "assistência" in content.text.lower()


async def test_31_07_good_day_never_alerts(session: AsyncSession) -> None:
    """17% clouds, irradiation 5.24, production well above expected -> no alert."""
    plant_id = await _make_plant(session)
    device_a = await _make_device(session, plant_id, "SN-A")
    device_b = await _make_device(session, plant_id, "SN-B")
    target = date(2026, 7, 31)
    await _seed_history(session, plant_id, [device_a, device_b], before=target)

    await _add_energy(session, device_a, target, "10.75")
    await _add_energy(session, device_b, target, "10.75")
    await _add_climate(session, plant_id, target, "5.24", "17")

    metrics = await gather_production_alert_metrics(
        session,
        plant_id=plant_id,
        target_date=target,
        expected_daily_production_kwh=EXPECTED_DAILY_PRODUCTION,
    )
    assert metrics.production_kwh == Decimal("21.5")

    assessment = assess_production_alert(metrics)

    assert assessment.should_alert is False
    assert assessment.reason is ProductionAlertReason.NONE


# --- Additional real-data-shaped regression coverage --------------------------


async def test_silent_inverter_is_listed_as_sem_dados_not_omitted_end_to_end(
    session: AsyncSession,
) -> None:
    """Blocker regression, exercised through the real DB query path: an
    inverter with zero `DailyEnergy` rows for the target day (total
    communication loss, not zero production) must still appear in
    `metrics.devices` and in the rendered message — in a two-inverter plant
    this is the single most serious failure mode there is."""
    plant_id = await _make_plant(session)
    device_reporting = await _make_device(session, plant_id, "SN-REPORTING")
    device_silent = await _make_device(session, plant_id, "SN-SILENT")
    target = date(2026, 8, 1)
    await _seed_history(session, plant_id, [device_reporting, device_silent], before=target)

    # device_silent has no DailyEnergy row at all for the target day.
    await _add_energy(session, device_reporting, target, "5.0")
    await _add_climate(session, plant_id, target, "4.75", "74")

    metrics = await gather_production_alert_metrics(
        session,
        plant_id=plant_id,
        target_date=target,
        expected_daily_production_kwh=EXPECTED_DAILY_PRODUCTION,
    )

    assert len(metrics.devices) == 2
    silent = next(device for device in metrics.devices if device.serial_number == "SN-SILENT")
    assert silent.production_kwh is None
    assert silent.rendimento is None

    assessment = assess_production_alert(metrics)
    assert assessment.should_alert is True

    content = render_production_alert(metrics, assessment, consecutive_days=1)
    assert "SN-SILENT" in content.text
    assert "sem dados" in content.text


async def test_device_rendimento_median_requires_minimum_sample_days(
    session: AsyncSession,
) -> None:
    """A one- or two-day history must never become a trusted "median" — see
    `MINIMUM_RENDIMENTO_SAMPLE_DAYS`. Without this floor, a fresh inverter
    with two lucky days of history could have a genuine cloudy-day dip
    marked `dropped=True` from pure noise, and — since a per-device drop now
    outranks the weather explanation — turn a normal cloudy day into a false
    equipment alert."""
    plant_id = await _make_plant(session)
    device_id = await _make_device(session, plant_id, "SN-NEW")
    target = date(2026, 8, 1)

    # Only 2 days of thin history: below MINIMUM_RENDIMENTO_SAMPLE_DAYS (5).
    await _add_climate(session, plant_id, target - timedelta(days=2), "4.89", "20")
    await _add_energy(session, device_id, target - timedelta(days=2), "9.75")
    await _add_climate(session, plant_id, target - timedelta(days=1), "4.89", "20")
    await _add_energy(session, device_id, target - timedelta(days=1), "9.75")

    await _add_energy(session, device_id, target, "6.6")
    await _add_climate(session, plant_id, target, "4.89", "20")

    metrics = await gather_production_alert_metrics(
        session,
        plant_id=plant_id,
        target_date=target,
        expected_daily_production_kwh=EXPECTED_DAILY_PRODUCTION,
    )

    assert len(metrics.devices) == 1
    assert metrics.devices[0].rendimento_median is None


async def test_chronic_device_asymmetry_does_not_trigger_a_daily_alert(
    session: AsyncSession,
) -> None:
    """Real Caldas Novas devices carry a large, permanent baseline
    difference (`86c41d70`: 710.8 kWh vs `86c41950`: 917.6 kWh over 92
    days — roughly 30% apart). Each inverter must be judged only against its
    own historical median; the asymmetry between them must never, on its
    own, look like a drop."""
    plant_id = await _make_plant(session)
    device_low_baseline = await _make_device(session, plant_id, "86c41d70")
    device_high_baseline = await _make_device(session, plant_id, "86c41950")
    target = date(2026, 8, 1)

    daily_low = "7.7261"  # ~710.8 kWh / 92 days
    daily_high = "9.9739"  # ~917.6 kWh / 92 days

    for offset in range(1, 31):
        history_date = target - timedelta(days=offset)
        await _add_climate(session, plant_id, history_date, "4.89", "20")
        await _add_energy(session, device_low_baseline, history_date, daily_low)
        await _add_energy(session, device_high_baseline, history_date, daily_high)

    # Target day: both inverters exactly at their own historical baseline.
    await _add_energy(session, device_low_baseline, target, daily_low)
    await _add_energy(session, device_high_baseline, target, daily_high)
    await _add_climate(session, plant_id, target, "4.89", "20")

    # `expected_daily_production_kwh` models nameplate sizing, not the
    # observed baseline — production sits well below it even on a
    # perfectly normal day, which is exactly the case that must not alert.
    expected = Decimal("25.29")

    metrics = await gather_production_alert_metrics(
        session,
        plant_id=plant_id,
        target_date=target,
        expected_daily_production_kwh=expected,
    )
    assert metrics.production_kwh < expected * Decimal("0.85")

    assessment = assess_production_alert(metrics)

    assert assessment.should_alert is False
    assert assessment.reason is ProductionAlertReason.NONE
    assert all(not device.dropped for device in assessment.devices)


# --- Data-not-found and dispatch behavior --------------------------------------


async def test_gather_metrics_raises_when_no_production(session: AsyncSession) -> None:
    plant_id = await _make_plant(session)
    await _make_device(session, plant_id, "SN-A")

    with pytest.raises(ProductionAlertDataNotFoundError):
        await gather_production_alert_metrics(
            session,
            plant_id=plant_id,
            target_date=date(2026, 7, 31),
            expected_daily_production_kwh=EXPECTED_DAILY_PRODUCTION,
        )


async def test_send_production_alert_is_a_noop_without_production_data(
    session: AsyncSession,
) -> None:
    plant_id = await _make_plant(session)
    await _make_device(session, plant_id, "SN-A")
    provider = RecordingProvider()

    result = await send_production_alert(
        session,
        plant_id=plant_id,
        target_date=date(2026, 7, 31),
        expected_daily_production_kwh=EXPECTED_DAILY_PRODUCTION,
        provider=provider,
        ledger=InMemoryAlertDeliveryLedger(),
    )

    assert result.sent is False
    assert result.reason == "no data"
    assert provider.calls == []


async def test_send_production_alert_is_a_noop_when_no_alert_condition(
    session: AsyncSession,
) -> None:
    plant_id = await _make_plant(session)
    device_a = await _make_device(session, plant_id, "SN-A")
    device_b = await _make_device(session, plant_id, "SN-B")
    target = date(2026, 7, 31)
    await _seed_history(session, plant_id, [device_a, device_b], before=target)
    await _add_energy(session, device_a, target, "10.75")
    await _add_energy(session, device_b, target, "10.75")
    await _add_climate(session, plant_id, target, "5.24", "17")
    provider = RecordingProvider()

    result = await send_production_alert(
        session,
        plant_id=plant_id,
        target_date=target,
        expected_daily_production_kwh=EXPECTED_DAILY_PRODUCTION,
        provider=provider,
        ledger=InMemoryAlertDeliveryLedger(),
    )

    assert result.sent is False
    assert result.reason == "no alert condition"
    assert provider.calls == []


async def test_send_production_alert_delivers_html_message_and_dedups(
    session: AsyncSession,
) -> None:
    plant_id = await _make_plant(session)
    device_a = await _make_device(session, plant_id, "SN-A")
    device_b = await _make_device(session, plant_id, "SN-B")
    target = date(2026, 6, 10)
    await _seed_history(session, plant_id, [device_a, device_b], before=target)
    await _add_energy(session, device_a, target, "5.9")
    await _add_energy(session, device_b, target, "5.9")
    await _add_climate(session, plant_id, target, "4.75", "74")
    provider = RecordingProvider()
    ledger = InMemoryAlertDeliveryLedger()

    first = await send_production_alert(
        session,
        plant_id=plant_id,
        target_date=target,
        expected_daily_production_kwh=EXPECTED_DAILY_PRODUCTION,
        provider=provider,
        ledger=ledger,
    )
    assert first.sent is True
    assert len(provider.calls) == 1
    assert provider.calls[0]["parse_mode"] == "HTML"
    assert provider.calls[0]["reply_markup"]["inline_keyboard"][0][0]["text"] == "Abrir painel"

    second = await send_production_alert(
        session,
        plant_id=plant_id,
        target_date=target,
        expected_daily_production_kwh=EXPECTED_DAILY_PRODUCTION,
        provider=provider,
        ledger=ledger,
    )
    assert second.sent is False
    assert second.reason == "duplicate alert"
    assert len(provider.calls) == 1


# --- Pure assessment/rendering unit tests --------------------------------------


def _metrics(
    *,
    production_kwh: str,
    expected: str = "18.7",
    irradiation: str | None,
    irradiation_median: str | None,
    irradiation_sample_days: int = 10,
    cloud_cover: str | None,
    rendimento: str | None,
    rendimento_median: str | None,
    devices: tuple[DeviceProductionMetrics, ...] = (),
) -> ProductionAlertMetrics:
    return ProductionAlertMetrics(
        plant_id=uuid.uuid4(),
        target_date=date(2026, 7, 15),
        production_kwh=Decimal(production_kwh),
        expected_daily_production_kwh=Decimal(expected),
        irradiation_kwh_m2=Decimal(irradiation) if irradiation is not None else None,
        irradiation_median_kwh_m2=(
            Decimal(irradiation_median) if irradiation_median is not None else None
        ),
        irradiation_sample_days=irradiation_sample_days,
        cloud_cover_percent=Decimal(cloud_cover) if cloud_cover is not None else None,
        rendimento=Decimal(rendimento) if rendimento is not None else None,
        rendimento_median=(
            Decimal(rendimento_median) if rendimento_median is not None else None
        ),
        devices=devices,
    )


def _device(
    serial: str,
    *,
    rendimento: str | None,
    rendimento_median: str | None,
    production_kwh: str | None = "5",
) -> DeviceProductionMetrics:
    return DeviceProductionMetrics(
        device_id=uuid.uuid4(),
        serial_number=serial,
        production_kwh=Decimal(production_kwh) if production_kwh is not None else None,
        rendimento=Decimal(rendimento) if rendimento is not None else None,
        rendimento_median=(
            Decimal(rendimento_median) if rendimento_median is not None else None
        ),
    )


def test_render_raises_for_non_alerting_assessment() -> None:
    metrics = _metrics(
        production_kwh="21.5",
        irradiation="5.24",
        irradiation_median="4.89",
        cloud_cover="17",
        rendimento="4.10",
        rendimento_median="3.9",
    )
    assessment = assess_production_alert(metrics)

    with pytest.raises(ValueError, match="non-alerting"):
        render_production_alert(metrics, assessment, consecutive_days=1)


def test_render_raises_when_consecutive_days_is_less_than_one() -> None:
    metrics = _metrics(
        production_kwh="8.0",
        irradiation="4.75",
        irradiation_median="4.89",
        cloud_cover="74",
        rendimento="1.6",
        rendimento_median="3.9",
    )
    assessment = assess_production_alert(metrics)
    assert assessment.should_alert is True

    with pytest.raises(ValueError, match="consecutive_days"):
        render_production_alert(metrics, assessment, consecutive_days=0)


def test_escalation_switches_icon_and_severity() -> None:
    metrics = _metrics(
        production_kwh="8.0",
        irradiation="4.75",
        irradiation_median="4.89",
        cloud_cover="74",
        rendimento="1.6",
        rendimento_median="3.9",
    )
    assessment = assess_production_alert(metrics)

    first_day = render_production_alert(metrics, assessment, consecutive_days=1)
    assert first_day.text.startswith("⚠️")
    assert first_day.severity is AlertSeverity.WARNING

    escalated = render_production_alert(metrics, assessment, consecutive_days=3)
    assert escalated.text.startswith("🚨")
    assert escalated.severity is AlertSeverity.CRITICAL
    assert "3º dia seguido" in escalated.text
    # Fingerprint must change with the escalation stage so dedup never
    # suppresses a change from "⚠️" to "🚨".
    assert first_day.fingerprint != escalated.fingerprint


def test_missing_rendimento_data_fails_toward_alerting_on_low_irradiation_day() -> None:
    """A cloudy day with *no* rendimento evidence must not be silently excused."""
    metrics = _metrics(
        production_kwh="6.0",
        irradiation="2.0",
        irradiation_median="4.89",
        irradiation_sample_days=10,
        cloud_cover="80",
        rendimento=None,
        rendimento_median=None,
    )

    assessment = assess_production_alert(metrics)

    assert assessment.should_alert is True
    assert assessment.reason is ProductionAlertReason.LOW_SUN_AND_LOW_YIELD
    assert assessment.low_irradiation is True


def test_too_few_irradiation_samples_never_excuses_a_drop_as_weather() -> None:
    """`is_low_irradiation`'s confidence gate must reach through to the alert."""
    metrics = _metrics(
        production_kwh="6.0",
        irradiation="2.0",
        irradiation_median="4.89",
        irradiation_sample_days=2,  # below DEFAULT_MINIMUM_IRRADIATION_SAMPLE_DAYS (5)
        cloud_cover="80",
        rendimento="1.0",
        rendimento_median="4.0",
    )

    assessment = assess_production_alert(metrics)

    assert assessment.low_irradiation is False
    assert assessment.should_alert is True
    assert assessment.reason is ProductionAlertReason.REAL_DROP_SET


def test_no_production_below_expected_never_alerts_regardless_of_climate() -> None:
    metrics = _metrics(
        production_kwh="17.0",
        expected="18.7",
        irradiation="1.0",
        irradiation_median="4.89",
        cloud_cover="90",
        rendimento="0.2",
        rendimento_median="4.0",
    )

    assessment = assess_production_alert(metrics)

    assert assessment.should_alert is False
    assert assessment.reason is ProductionAlertReason.NONE


def test_device_drop_on_a_genuinely_low_irradiation_day_still_alerts_by_device() -> None:
    """Regression test: a real per-device drop must never be buried by a
    coincidentally low-sun day, and the climate line must stay honest about
    the irradiation actually being low (not claim it was "normal")."""
    devices = (
        _device("SN-BAD", rendimento="0.6", rendimento_median="1.0"),
        _device("SN-OK", rendimento="0.95", rendimento_median="1.0"),
    )
    metrics = _metrics(
        production_kwh="8.0",
        irradiation="2.0",
        irradiation_median="4.89",
        cloud_cover="85",
        rendimento="0.9",
        rendimento_median="1.0",
        devices=devices,
    )

    assessment = assess_production_alert(metrics)

    assert assessment.low_irradiation is True
    assert assessment.should_alert is True
    assert assessment.reason is ProductionAlertReason.REAL_DROP_SINGLE

    content = render_production_alert(metrics, assessment, consecutive_days=1)
    assert "Pouco sol ontem" in content.text
    assert "chegou normal" not in content.text
    assert "SN-BAD" in content.text


def test_no_climate_and_no_device_evidence_fails_toward_alerting() -> None:
    metrics = _metrics(
        production_kwh="10.0",
        irradiation=None,
        irradiation_median=None,
        cloud_cover=None,
        rendimento=None,
        rendimento_median=None,
    )

    assessment = assess_production_alert(metrics)

    assert assessment.should_alert is True
    assert assessment.reason is ProductionAlertReason.UNEXPLAINED_LOW_PRODUCTION


def test_missing_climate_with_reporting_devices_still_fails_toward_alerting() -> None:
    """Blocker regression: a climate-provider outage (rate limit, downtime)
    must never silence the alert just because inverters exist and reported
    energy. `gather_production_alert_metrics` never computes device
    rendimento without an irradiation reading for the day, so a real outage
    produces exactly this shape: non-empty `devices`, every one of them with
    `rendimento=None`. The old gate only checked `not devices`, which this
    case does not satisfy, and stayed silent despite zero evidence that the
    day was actually fine.
    """
    devices = (
        _device("SN-A", rendimento=None, rendimento_median=None),
        _device("SN-B", rendimento=None, rendimento_median=None),
    )
    metrics = _metrics(
        production_kwh="10.0",
        expected="18.7",
        irradiation=None,
        irradiation_median=None,
        cloud_cover=None,
        rendimento=None,
        rendimento_median=None,
        devices=devices,
    )

    assessment = assess_production_alert(metrics)

    assert assessment.should_alert is True
    assert assessment.reason is ProductionAlertReason.UNEXPLAINED_LOW_PRODUCTION


def test_thin_device_history_with_no_plant_evidence_still_fails_toward_alerting() -> None:
    """Same failure mode as above, reached a different way: climate exists
    for the target day, but every inverter's history is too thin to trust a
    median (`relative_to_own_median` stays `None`), and the plant-level
    rendimento median is unavailable too. No evidence anywhere that the day
    was fine -> must still alert.
    """
    devices = (
        _device("SN-A", rendimento="1.0", rendimento_median=None),
        _device("SN-B", rendimento="1.0", rendimento_median=None),
    )
    metrics = _metrics(
        production_kwh="10.0",
        expected="18.7",
        irradiation="4.75",
        irradiation_median="4.89",
        cloud_cover="20",
        rendimento="1.0",
        rendimento_median=None,
        devices=devices,
    )

    assessment = assess_production_alert(metrics)

    assert assessment.should_alert is True
    assert assessment.reason is ProductionAlertReason.UNEXPLAINED_LOW_PRODUCTION


def test_at_least_one_known_normal_device_is_enough_evidence_to_not_alert() -> None:
    """The flip side of the two tests above: as soon as *any* evidence
    exists that the day was fine (here, one inverter with a trustworthy
    median reading normal), the gate must not fire — this is not a
    "no evidence" case."""
    devices = (
        _device("SN-A", rendimento="1.0", rendimento_median="1.0"),
        _device("SN-B", rendimento="1.0", rendimento_median=None),
    )
    metrics = _metrics(
        production_kwh="10.0",
        expected="18.7",
        irradiation="4.75",
        irradiation_median="4.89",
        cloud_cover="20",
        rendimento=None,
        rendimento_median=None,
        devices=devices,
    )

    assessment = assess_production_alert(metrics)

    assert assessment.should_alert is False
    assert assessment.reason is ProductionAlertReason.NONE


def test_expected_production_zero_or_negative_never_alerts() -> None:
    metrics = _metrics(
        production_kwh="0",
        expected="0",
        irradiation=None,
        irradiation_median=None,
        cloud_cover=None,
        rendimento=None,
        rendimento_median=None,
    )

    assessment = assess_production_alert(metrics)

    assert assessment.should_alert is False
    assert assessment.reason is ProductionAlertReason.NONE


def test_render_escapes_html_in_device_serial_number() -> None:
    devices = (
        _device("<script>x</script>", rendimento="0.5", rendimento_median="1.0"),
        _device("SN-OK", rendimento="0.95", rendimento_median="1.0"),
    )
    metrics = _metrics(
        production_kwh="8.0",
        irradiation="4.75",
        irradiation_median="4.89",
        cloud_cover="74",
        rendimento="0.9",
        rendimento_median="1.0",
        devices=devices,
    )

    assessment = assess_production_alert(metrics)
    content = render_production_alert(metrics, assessment, consecutive_days=1)

    assert "<script>" not in content.text
    assert "&lt;script&gt;" in content.text


def test_format_number_uses_brazilian_decimal_and_thousands_separators() -> None:
    from mplacas.alerts.production_alert import _format_number

    assert _format_number(Decimal("1234.5"), 1) == "1.234,5"
    assert _format_number(Decimal("21.5"), 1) == "21,5"
    assert _format_number(Decimal("74"), 0) == "74"


def test_title_text_is_grammatically_complete_for_every_reason() -> None:
    """Blocker regression: `REAL_DROP_SINGLE`'s first-day (non-escalated)
    title used to drop its suffix entirely, sending the owner the literal
    incomplete sentence "Um inversor rendendo abaixo" — abaixo of what?
    Every reason must produce a complete sentence, escalated or not.
    """
    from mplacas.alerts.production_alert import _title

    cases = [
        (
            ProductionAlertReason.REAL_DROP_SET,
            "Queda de rendimento ontem",
            "Queda de rendimento — 3º dia seguido",
        ),
        (
            ProductionAlertReason.REAL_DROP_SINGLE,
            "Um inversor rendendo abaixo do normal ontem",
            "Um inversor rendendo abaixo do normal — 3º dia seguido",
        ),
        (
            ProductionAlertReason.LOW_SUN_AND_LOW_YIELD,
            "Pouco sol e rendimento abaixo do normal ontem",
            "Pouco sol e rendimento abaixo do normal — 3º dia seguido",
        ),
        (
            ProductionAlertReason.UNEXPLAINED_LOW_PRODUCTION,
            "Produção abaixo do esperado ontem",
            "Produção abaixo do esperado — 3º dia seguido",
        ),
    ]
    for reason, expected_first_day, expected_escalated in cases:
        assert _title(reason, False, 1) == expected_first_day
        assert _title(reason, True, 3) == expected_escalated


def test_yield_line_matches_the_threshold_the_decision_actually_used() -> None:
    """Blocker regression: the plant-level yield line used to fire whenever
    `relative < 1`, while the decision tree calls a day "normal" at 0.85.
    A day alerting only because of a single dropped inverter, with the
    plant-level average at (say) 0.90, must not also claim the whole plant
    is "abaixo do normal" — that contradicts the assessment.
    """
    devices = (
        _device("SN-BAD", rendimento="0.6", rendimento_median="1.0"),
        _device("SN-OK", rendimento="0.95", rendimento_median="1.0"),
    )
    metrics = _metrics(
        production_kwh="8.0",
        irradiation="4.75",
        irradiation_median="4.89",
        cloud_cover="20",
        rendimento="0.9",
        rendimento_median="1.0",
        devices=devices,
    )

    assessment = assess_production_alert(metrics)
    assert assessment.reason is ProductionAlertReason.REAL_DROP_SINGLE

    content = render_production_alert(metrics, assessment, consecutive_days=1)

    assert "abaixo do normal desta usina" not in content.text


def test_device_with_no_data_today_is_listed_as_sem_dados_not_omitted() -> None:
    """Blocker regression: a device with no rendimento evidence must not
    render as if it produced 0 kWh, and must never be invented a number."""
    devices = (
        _device("SN-OK", rendimento="0.95", rendimento_median="1.0"),
        _device("SN-SILENT", rendimento=None, rendimento_median=None, production_kwh=None),
    )
    metrics = _metrics(
        production_kwh="8.0",
        irradiation="4.75",
        irradiation_median="4.89",
        cloud_cover="20",
        rendimento="0.5",
        rendimento_median="1.0",
        devices=devices,
    )

    assessment = assess_production_alert(metrics)
    # The plant-level rendimento drop alone is enough to alert here; the
    # point under test is only how the silent device renders.
    assert assessment.should_alert is True

    content = render_production_alert(metrics, assessment, consecutive_days=1)

    assert "SN-SILENT" in content.text
    assert "sem dados" in content.text
    assert "None" not in content.text
