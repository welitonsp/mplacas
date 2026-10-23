"""Reprocessamento de meses sem economia ou com cálculo desatualizado (ADR-081)."""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mplacas.billing.db_models import BillStatus, UtilityBillRecord
from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy, DataStatus, Device, Plant
from mplacas.reports.db_models import MonthlyReportSnapshotRecord
from mplacas.reports.projection import build_monthly_report_for_bill
from mplacas.reports.savings_gaps import (
    ReprocessOutcome,
    SavingsGapCause,
    list_savings_gaps,
    reprocess_savings_gaps,
)
from mplacas.reports.snapshot import (
    MonthlyReportSnapshotRepository,
    materialize_monthly_report_snapshot,
)
from mplacas.tariffs.db_models import DistributorTariffRecord
from mplacas.tariffs.service import RESIDENTIAL_B1_CONVENTIONAL


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add(
            DistributorTariffRecord(
                distributor="EQUATORIAL_GO",
                tariff_class=RESIDENTIAL_B1_CONVENTIONAL,
                valid_from=date(2025, 10, 22),
                valid_to=date(2026, 10, 21),
                full_brl_kwh=Decimal("0.891810"),
                scee_brl_kwh=Decimal("0.613030"),
                source="teste",
            )
        )
        await db.commit()
        yield db
    await engine.dispose()


def _bill(plant_id: uuid.UUID, month: str, day: date, n: int) -> UtilityBillRecord:
    return UtilityBillRecord(
        plant_id=plant_id,
        distributor="EQUATORIAL_GO",
        reference_month=month,
        cycle_start=day,
        cycle_end=day,
        billed_days=1,
        imported_kwh=Decimal("8"),
        injected_kwh=Decimal("8"),
        compensated_kwh=Decimal("8"),
        credit_balance_kwh=Decimal("10"),
        total_amount_brl=Decimal("32.00"),
        public_lighting_brl=Decimal("30.21"),
        generation_cycle_kwh=Decimal("9"),
        tariff_with_taxes_brl_kwh=Decimal("0.787589"),
        tariff_without_taxes_brl_kwh=Decimal("0.613030"),
        status=BillStatus.CONFIRMED,
        source_hash=str(n) * 64,
        reviewed_at=datetime(2026, 10, 1, tzinfo=UTC),
    )


async def _scenario(session: AsyncSession) -> dict[str, UtilityBillRecord]:
    plant = Plant(name="Usina reprocessamento")
    session.add(plant)
    await session.flush()
    device = Device(plant_id=plant.id, serial_number="REPROC-001")
    session.add(device)
    await session.flush()
    days = {
        "missing": date(2026, 5, 10),
        "predates": date(2026, 6, 10),
        "outdated": date(2026, 7, 10),
        "no_production": date(2026, 8, 10),
        "current": date(2026, 9, 10),
    }
    bills = {
        key: _bill(plant.id, day.strftime("%Y-%m"), day, n)
        for n, (key, day) in enumerate(days.items(), start=1)
    }
    session.add_all(bills.values())
    for key, day in days.items():
        if key != "no_production":
            session.add(
                DailyEnergy(
                    device_id=device.id,
                    production_date=day,
                    energy_kwh=Decimal("20"),
                    status=DataStatus.CONSOLIDATED,
                )
            )
    await session.commit()

    repository = MonthlyReportSnapshotRepository(session)
    # Relatório anterior ao cálculo de economia: sem a métrica.
    report = await build_monthly_report_for_bill(
        session, bill_id=bills["predates"].id, plant_id=plant.id
    )
    await repository.create(
        dataclasses.replace(
            report,
            calculation_version="0.2.0",
            metrics=tuple(
                m
                for m in report.metrics
                if not m.key.startswith("savings_") and m.key != "estimated_savings_brl"
            ),
        )
    )
    # Economia calculada pela tarifa SCEE (0.3.0): um piso.
    report = await build_monthly_report_for_bill(
        session, bill_id=bills["outdated"].id, plant_id=plant.id
    )
    await repository.create(
        dataclasses.replace(
            report,
            calculation_version="0.3.0",
            metrics=tuple(
                dataclasses.replace(m, value="5.00") if m.key == "estimated_savings_brl" else m
                for m in report.metrics
                if not m.key.startswith("savings_tariff")
            ),
        )
    )
    for key in ("no_production", "current"):
        await materialize_monthly_report_snapshot(
            session, bill_id=bills[key].id, plant_id=plant.id
        )
    await session.commit()
    return bills


async def test_lists_every_month_that_needs_recalculation(session: AsyncSession) -> None:
    bills = await _scenario(session)
    plant_id = bills["current"].plant_id

    gaps = {gap.reference_month: gap for gap in await list_savings_gaps(session, plant_id=plant_id)}

    assert gaps["2026-05"].cause is SavingsGapCause.REPORT_MISSING
    assert gaps["2026-06"].cause is SavingsGapCause.REPORT_PREDATES_SAVINGS
    assert gaps["2026-07"].cause is SavingsGapCause.OUTDATED_CALCULATION
    assert gaps["2026-07"].previous_savings_brl == "5.00"
    assert gaps["2026-08"].cause is SavingsGapCause.SAVINGS_UNAVAILABLE
    assert gaps["2026-08"].savings_unavailable_reason == "NO_PRODUCTION_DATA"
    assert "2026-09" not in gaps  # já calculado pela fórmula corrigida


async def test_reprocess_stores_new_revisions_and_keeps_the_old_ones(
    session: AsyncSession,
) -> None:
    bills = await _scenario(session)
    plant_id = bills["current"].plant_id
    before = await session.scalar(select(func.count(MonthlyReportSnapshotRecord.id)))

    reprocessed = await reprocess_savings_gaps(session, plant_id=plant_id)
    results = {r.reference_month: r for r in reprocessed}
    await session.commit()

    assert results["2026-05"].outcome is ReprocessOutcome.RECALCULATED
    assert results["2026-05"].stored_revision == 1
    assert results["2026-06"].stored_revision == 2
    assert results["2026-07"].stored_revision == 2
    assert results["2026-07"].previous_savings_brl == "5.00"
    assert results["2026-07"].estimated_savings_brl not in (None, "5.00")
    # Sem produção continua sem produção: nenhuma revisão nova.
    assert results["2026-08"].outcome is ReprocessOutcome.STILL_UNAVAILABLE
    assert results["2026-08"].stored_revision is None
    after = await session.scalar(select(func.count(MonthlyReportSnapshotRecord.id)))
    assert after == before + 3  # nada apagado: revisões antigas continuam

    # Leitores enxergam uma linha por fatura, a revisão mais recente.
    latest = await MonthlyReportSnapshotRepository(session).list_for_plant(plant_id=plant_id)
    assert [s.report.reference_month for s in latest] == [
        "2026-05",
        "2026-06",
        "2026-07",
        "2026-08",
        "2026-09",
    ]
    july = next(s for s in latest if s.report.reference_month == "2026-07")
    assert july.revision == 2
    assert july.report.calculation_version >= "0.4.0"


async def test_second_run_is_idempotent(session: AsyncSession) -> None:
    bills = await _scenario(session)
    plant_id = bills["current"].plant_id
    await reprocess_savings_gaps(session, plant_id=plant_id)
    await session.commit()
    count = await session.scalar(select(func.count(MonthlyReportSnapshotRecord.id)))

    again = await reprocess_savings_gaps(session, plant_id=plant_id)
    await session.commit()

    assert all(r.stored_revision is None for r in again)
    assert await session.scalar(select(func.count(MonthlyReportSnapshotRecord.id))) == count


def test_routes_are_tenant_scoped_and_reprocess_requires_admin(monkeypatch) -> None:
    import asyncio

    from fastapi.testclient import TestClient

    import mplacas.db.session as db_session
    import mplacas.reports.router as reports_router
    from mplacas.audit.db_models import AuditEventRecord
    from mplacas.core.config import get_settings
    from mplacas.core.jwt import encode_access_token
    from mplacas.core.security import OperationsRole
    from mplacas.main import app
    from mplacas.organizations.db_models import OrganizationRecord

    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()
    plant_id = uuid.uuid4()

    async def setup():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        async with factory() as db:
            db.add_all(
                [
                    OrganizationRecord(id=org_a, name="A", slug=f"a-{org_a.hex[:8]}", active=True),
                    OrganizationRecord(id=org_b, name="B", slug=f"b-{org_b.hex[:8]}", active=True),
                ]
            )
            db.add(Plant(id=plant_id, organization_id=org_a, name="Casa"))
            await db.flush()
            db.add(_bill(plant_id, "2026-05", date(2026, 5, 10), 7))  # confirmada, sem relatório
            await db.commit()
        return engine, factory, org_a, org_b

    engine, factory, org_a, org_b = asyncio.run(setup())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(reports_router, "SessionFactory", factory)
    read_a = encode_access_token(uuid.uuid4(), org_a, OperationsRole.READ.value)
    admin_a = encode_access_token(uuid.uuid4(), org_a, OperationsRole.ADMIN.value)
    admin_b = encode_access_token(uuid.uuid4(), org_b, OperationsRole.ADMIN.value)
    url = f"/reports/monthly/savings-gaps?plant_id={plant_id}"
    reprocess = f"/reports/monthly/savings-gaps/reprocess?plant_id={plant_id}"

    with TestClient(app) as client:
        listed = client.get(url, headers={"Authorization": f"Bearer {read_a}"})
        read_denied = client.post(reprocess, headers={"Authorization": f"Bearer {read_a}"})
        foreign = client.post(reprocess, headers={"Authorization": f"Bearer {admin_b}"})
        done = client.post(reprocess, headers={"Authorization": f"Bearer {admin_a}"})

    async def audit_actions():
        async with factory() as db:
            return list(await db.scalars(select(AuditEventRecord.action)))

    actions = asyncio.run(audit_actions())
    asyncio.run(engine.dispose())
    get_settings.cache_clear()

    assert listed.status_code == 200
    assert listed.json()["items"][0]["cause"] == "REPORT_MISSING"
    assert read_denied.status_code == 403
    assert foreign.status_code == 404
    assert done.status_code == 200
    assert done.json()["items"][0]["stored_revision"] == 1
    assert "reports.reprocess_savings" in actions


async def test_outdated_month_never_loses_its_savings(session: AsyncSession) -> None:
    # A telemetria de jul/2026 sumiu (ex.: retenção). O recálculo de hoje daria
    # "sem produção"; a revisão antiga, com economia, tem de continuar valendo.
    from sqlalchemy import delete

    bills = await _scenario(session)
    plant_id = bills["current"].plant_id
    july = date(2026, 7, 10)
    await session.execute(delete(DailyEnergy).where(DailyEnergy.production_date == july))
    await session.commit()

    reprocessed = await reprocess_savings_gaps(session, plant_id=plant_id)
    await session.commit()
    results = {r.reference_month: r for r in reprocessed}

    assert results["2026-07"].stored_revision is None
    latest = await MonthlyReportSnapshotRepository(session).by_bill_id(
        bills["outdated"].id, plant_id=plant_id
    )
    assert latest is not None and latest.revision == 1
    savings = next(m.value for m in latest.report.metrics if m.key == "estimated_savings_brl")
    assert savings == "5.00"


async def test_bill_completed_from_pdf_becomes_recalculable(session: AsyncSession) -> None:
    # Fatura confirmada sem tarifa (veio pelo texto do Telegram): relatório
    # sem economia. O PDF completa a tarifa e o recálculo passa a ter valor.
    from mplacas.billing.completion import complete_missing_fields
    from mplacas.billing.models import UtilityBill
    from mplacas.billing.repository import UtilityBillRepository

    plant = Plant(name="Usina Telegram")
    session.add(plant)
    await session.flush()
    device = Device(plant_id=plant.id, serial_number="TG-001")
    session.add(device)
    await session.flush()
    day = date(2026, 6, 10)
    record = _bill(plant.id, "2026-06", day, 9)
    record.tariff_with_taxes_brl_kwh = None
    record.tariff_without_taxes_brl_kwh = None
    session.add(record)
    session.add(
        DailyEnergy(
            device_id=device.id,
            production_date=day,
            energy_kwh=Decimal("20"),
            status=DataStatus.CONSOLIDATED,
        )
    )
    await session.commit()
    await materialize_monthly_report_snapshot(session, bill_id=record.id, plant_id=plant.id)
    await session.commit()
    gaps = await list_savings_gaps(session, plant_id=plant.id)
    assert gaps[0].savings_unavailable_reason == "TARIFF_NOT_AVAILABLE"

    repository = UtilityBillRepository(session)
    (found,) = await repository.find_confirmed_for_month(
        plant_id=plant.id, distributor="EQUATORIAL_GO", reference_month="2026-06"
    )
    assert found.id == record.id
    pdf = UtilityBill(
        distributor="EQUATORIAL_GO",
        reference_month="2026-06",
        cycle_start=day,
        cycle_end=day,
        billed_days=1,
        imported_kwh=Decimal("8.00"),
        injected_kwh=Decimal("8.00"),
        compensated_kwh=Decimal("8.00"),
        credit_balance_kwh=Decimal("10.00"),
        total_amount_brl=Decimal("32.00"),
        public_lighting_brl=Decimal("30.21"),
        generation_cycle_kwh=Decimal("9"),
        tariff_with_taxes_brl_kwh=Decimal("0.799059"),
        tariff_without_taxes_brl_kwh=Decimal("0.613030"),
    )
    assert complete_missing_fields(found, pdf) == (
        "tariff_with_taxes_brl_kwh",
        "tariff_without_taxes_brl_kwh",
    )
    await session.commit()

    results = await reprocess_savings_gaps(session, plant_id=plant.id)
    await session.commit()

    assert results[0].outcome is ReprocessOutcome.RECALCULATED
    assert results[0].stored_revision == 2
    assert results[0].estimated_savings_brl not in (None, "")


async def test_month_with_gaps_computed_before_estimates_is_recalculable(
    session: AsyncSession,
) -> None:
    # Snapshot 0.4.0 de um ciclo com dias sem leitura, gravado antes do
    # ADR-082 (sem as métricas de estimativa): entra como PARTIAL_PRODUCTION.
    plant = Plant(name="Usina parcial")
    session.add(plant)
    await session.flush()
    device = Device(plant_id=plant.id, serial_number="PARC-001")
    session.add(device)
    await session.flush()
    day = date(2026, 9, 12)
    record = _bill(plant.id, "2026-09", day, 8)
    session.add(record)
    session.add(
        DailyEnergy(
            device_id=device.id,
            production_date=day,
            energy_kwh=Decimal("20"),
            status=DataStatus.CONSOLIDATED,
        )
    )
    await session.commit()
    report = await build_monthly_report_for_bill(session, bill_id=record.id, plant_id=plant.id)
    legacy_quality = tuple(
        dataclasses.replace(m, value="3") if m.key == "missing_days" else m
        for m in report.quality
        if not m.key.startswith("estimated_") and m.key != "meter_floor_kwh"
    )
    await MonthlyReportSnapshotRepository(session).create(
        dataclasses.replace(report, quality=legacy_quality)
    )
    await session.commit()

    (gap,) = await list_savings_gaps(session, plant_id=plant.id)
    assert gap.cause is SavingsGapCause.PARTIAL_PRODUCTION

    # O ciclo de 1 dia está completo agora (leitura existe): buraco resolvido.
    (result,) = await reprocess_savings_gaps(session, plant_id=plant.id)
    await session.commit()
    assert result.stored_revision == 2
    assert await list_savings_gaps(session, plant_id=plant.id) == ()


async def test_partial_month_without_climate_stays_listed(session: AsyncSession) -> None:
    # Sem clima carregado não há estimativa: o mês NÃO pode sair da lista.
    plant = Plant(name="Usina sem clima")
    session.add(plant)
    await session.flush()
    device = Device(plant_id=plant.id, serial_number="SEMCLIMA-1")
    session.add(device)
    await session.flush()
    start = date(2026, 9, 1)
    record = _bill(plant.id, "2026-09", start, 11)
    record.cycle_end = date(2026, 9, 2)
    record.billed_days = 2
    session.add(record)
    session.add(
        DailyEnergy(
            device_id=device.id,
            production_date=start,
            energy_kwh=Decimal("20"),
            status=DataStatus.CONSOLIDATED,
        )
    )
    await session.commit()
    report = await build_monthly_report_for_bill(session, bill_id=record.id, plant_id=plant.id)
    await MonthlyReportSnapshotRepository(session).create(
        dataclasses.replace(
            report,
            quality=tuple(
                m
                for m in report.quality
                if not m.key.startswith("estimated_") and m.key != "meter_floor_kwh"
            ),
        )
    )
    await session.commit()

    (result,) = await reprocess_savings_gaps(session, plant_id=plant.id)
    await session.commit()

    assert result.stored_revision is None
    (gap,) = await list_savings_gaps(session, plant_id=plant.id)
    assert gap.cause is SavingsGapCause.PARTIAL_PRODUCTION
