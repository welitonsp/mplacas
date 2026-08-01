from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mplacas.billing.db_models import BillStatus, UtilityBillRecord
from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy, DataStatus, Device, Plant
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord
from mplacas.reports.daily_digest import (
    DailyDigestDataNotFoundError,
    DailyDigestMetrics,
    gather_daily_digest_metrics,
    render_daily_digest,
    send_daily_digest,
)


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


async def _make_device(session: AsyncSession, plant_id: uuid.UUID) -> uuid.UUID:
    device = Device(plant_id=plant_id, serial_number="SN001")
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


async def _add_confirmed_bill(
    session: AsyncSession, plant_id: uuid.UUID, credit_balance_kwh: str
) -> None:
    session.add(
        UtilityBillRecord(
            plant_id=plant_id,
            distributor="Enel",
            reference_month="2026-07",
            cycle_start=date(2026, 6, 15),
            cycle_end=date(2026, 7, 15),
            billed_days=30,
            imported_kwh=Decimal("100"),
            injected_kwh=Decimal("200"),
            compensated_kwh=Decimal("100"),
            credit_balance_kwh=Decimal(credit_balance_kwh),
            total_amount_brl=Decimal("50.00"),
            public_lighting_brl=Decimal("0"),
            status=BillStatus.CONFIRMED,
            source_hash=f"hash-{credit_balance_kwh}",
        )
    )
    await session.flush()


class RecordingProvider:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send_message(self, text, *, parse_mode=None, reply_markup=None) -> None:
        self.calls.append(
            {"text": text, "parse_mode": parse_mode, "reply_markup": reply_markup}
        )


async def test_gather_metrics_raises_when_no_production(session: AsyncSession) -> None:
    plant_id = await _make_plant(session)
    await _make_device(session, plant_id)

    with pytest.raises(DailyDigestDataNotFoundError):
        await gather_daily_digest_metrics(
            session,
            plant_id=plant_id,
            target_date=date(2026, 7, 31),
            expected_daily_production_kwh=Decimal("18.7"),
        )


async def test_send_daily_digest_is_a_noop_without_production_data(
    session: AsyncSession,
) -> None:
    plant_id = await _make_plant(session)
    await _make_device(session, plant_id)
    provider = RecordingProvider()

    sent = await send_daily_digest(
        session,
        plant_id=plant_id,
        target_date=date(2026, 7, 31),
        expected_daily_production_kwh=Decimal("18.7"),
        provider=provider,
    )

    assert sent is False
    assert provider.calls == []


async def test_gather_metrics_full_scenario(session: AsyncSession) -> None:
    plant_id = await _make_plant(session)
    device_id = await _make_device(session, plant_id)
    target = date(2026, 7, 31)

    # Baseline history to establish a rendimento median (~4.0).
    for day in range(1, 31):
        history_date = date(2026, 7, day)
        await _add_energy(session, device_id, history_date, "20.0")
        await _add_climate(session, plant_id, history_date, "5.0", "10")

    await _add_energy(session, device_id, target, "21.5")
    await _add_climate(session, plant_id, target, "5.24", "10")
    await _add_confirmed_bill(session, plant_id, "8")

    metrics = await gather_daily_digest_metrics(
        session,
        plant_id=plant_id,
        target_date=target,
        expected_daily_production_kwh=Decimal("18.7"),
    )

    assert metrics.production_kwh == Decimal("21.5")
    assert metrics.irradiation_kwh_m2 == Decimal("5.24")
    assert metrics.rendimento is not None
    assert metrics.rendimento_median == Decimal("4.0")
    assert metrics.month_total_kwh == Decimal("621.5")
    assert metrics.month_days == 31
    assert metrics.credit_balance_kwh == Decimal("8")


async def test_render_full_message_matches_expected_format(session: AsyncSession) -> None:
    metrics = DailyDigestMetrics(
        plant_id=uuid.uuid4(),
        target_date=date(2026, 7, 31),
        production_kwh=Decimal("21.5"),
        expected_daily_production_kwh=Decimal("18.7"),
        irradiation_kwh_m2=Decimal("5.24"),
        cloud_cover_percent=Decimal("10"),
        rendimento=Decimal("4.10"),
        rendimento_median=Decimal("3.9"),
        month_total_kwh=Decimal("577"),
        month_days=31,
        credit_balance_kwh=Decimal("8"),
    )

    content = render_daily_digest(metrics)

    assert "☀️ Ontem, 31 de julho" in content.text
    assert "<b>21,5 kWh</b>" in content.text
    assert "115% do esperado ▲" in content.text
    assert "Sol: 5,24 kWh/m² · dia claro" in content.text
    assert "Rendimento: 4,10 — acima do normal" in content.text
    assert "Julho: 577 kWh em 31 dias" in content.text
    assert "Saldo de créditos: 8 kWh" in content.text
    assert content.reply_markup == {
        "inline_keyboard": [
            [{"text": "Abrir painel", "url": "https://mplacas-frontend.pages.dev/dashboard"}]
        ]
    }
    assert "Ação recomendada" not in content.text


async def test_render_omits_sun_and_rendimento_when_irradiation_missing() -> None:
    metrics = DailyDigestMetrics(
        plant_id=uuid.uuid4(),
        target_date=date(2026, 7, 31),
        production_kwh=Decimal("21.5"),
        expected_daily_production_kwh=Decimal("18.7"),
        irradiation_kwh_m2=None,
        cloud_cover_percent=None,
        rendimento=None,
        rendimento_median=None,
        month_total_kwh=Decimal("577"),
        month_days=31,
        credit_balance_kwh=Decimal("8"),
    )

    content = render_daily_digest(metrics)

    assert "Sol" not in content.text
    assert "Rendimento" not in content.text
    assert "<b>21,5 kWh</b>" in content.text
    assert "Julho: 577 kWh em 31 dias" in content.text


async def test_render_omits_month_and_credit_lines_when_absent() -> None:
    metrics = DailyDigestMetrics(
        plant_id=uuid.uuid4(),
        target_date=date(2026, 7, 31),
        production_kwh=Decimal("21.5"),
        expected_daily_production_kwh=Decimal("18.7"),
        irradiation_kwh_m2=None,
        cloud_cover_percent=None,
        rendimento=None,
        rendimento_median=None,
        month_total_kwh=None,
        month_days=None,
        credit_balance_kwh=None,
    )

    content = render_daily_digest(metrics)

    assert "kWh em" not in content.text
    assert "Saldo de créditos" not in content.text


def test_render_escapes_html_special_characters_in_dynamic_labels() -> None:
    metrics = DailyDigestMetrics(
        plant_id=uuid.uuid4(),
        target_date=date(2026, 7, 31),
        production_kwh=Decimal("21.5"),
        expected_daily_production_kwh=Decimal("18.7"),
        irradiation_kwh_m2=Decimal("5.24"),
        cloud_cover_percent=Decimal("10"),
        rendimento=Decimal("4.10"),
        rendimento_median=Decimal("3.9"),
        month_total_kwh=Decimal("577"),
        month_days=31,
        credit_balance_kwh=Decimal("8"),
    )

    dangerous = "<script>alert(1)</script> & <b>bold</b>"
    with (
        patch("mplacas.reports.daily_digest._climate_label", return_value=dangerous),
        patch("mplacas.reports.daily_digest._rendimento_label", return_value=dangerous),
    ):
        content = render_daily_digest(metrics)

    assert "<script>" not in content.text
    assert dangerous not in content.text
    escaped = "&lt;script&gt;alert(1)&lt;/script&gt; &amp; &lt;b&gt;bold&lt;/b&gt;"
    assert content.text.count(escaped) == 2


async def test_send_daily_digest_delivers_html_message_with_url_button(
    session: AsyncSession,
) -> None:
    plant_id = await _make_plant(session)
    device_id = await _make_device(session, plant_id)
    target = date(2026, 7, 31)
    await _add_energy(session, device_id, target, "21.5")
    provider = RecordingProvider()

    sent = await send_daily_digest(
        session,
        plant_id=plant_id,
        target_date=target,
        expected_daily_production_kwh=Decimal("18.7"),
        provider=provider,
    )

    assert sent is True
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert call["parse_mode"] == "HTML"
    assert call["reply_markup"]["inline_keyboard"][0][0]["url"] == (
        "https://mplacas-frontend.pages.dev/dashboard"
    )
    assert "<b>21,5 kWh</b>" in call["text"]
