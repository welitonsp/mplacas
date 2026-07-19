from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.billing.db_models import BillStatus, UtilityBillRecord
from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy, DataStatus, Device, Plant
from mplacas.reports.db_models import MonthlyReportSnapshotRecord
from mplacas.reports.snapshot import (
    MonthlyReportSnapshotRepository,
    ReportSnapshotIntegrityError,
    get_or_materialize_latest_monthly_report_snapshot,
    materialize_monthly_report_snapshot,
)


def _bill(
    *,
    plant_id: uuid.UUID,
    reference_month: str,
    cycle_day: date,
    source_hash: str,
) -> UtilityBillRecord:
    return UtilityBillRecord(
        plant_id=plant_id,
        distributor="EQUATORIAL_GO",
        reference_month=reference_month,
        cycle_start=cycle_day,
        cycle_end=cycle_day,
        billed_days=1,
        imported_kwh=Decimal("20"),
        injected_kwh=Decimal("40"),
        compensated_kwh=Decimal("20"),
        credit_balance_kwh=Decimal("50"),
        total_amount_brl=Decimal("60"),
        public_lighting_brl=Decimal("30"),
        status=BillStatus.CONFIRMED,
        source_hash=source_hash,
        reviewed_at=datetime(2026, 7, 19, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_snapshots_are_exact_idempotent_and_immutable_after_source_changes() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Snapshot plant")
        session.add(plant)
        await session.flush()
        device = Device(plant_id=plant.id, serial_number="SNAPSHOT-001")
        session.add(device)
        await session.flush()
        june = _bill(
            plant_id=plant.id,
            reference_month="2026-06",
            cycle_day=date(2026, 6, 30),
            source_hash="1" * 64,
        )
        july = _bill(
            plant_id=plant.id,
            reference_month="2026-07",
            cycle_day=date(2026, 7, 31),
            source_hash="2" * 64,
        )
        june_energy = DailyEnergy(
            device_id=device.id,
            production_date=date(2026, 6, 30),
            energy_kwh=Decimal("100"),
            status=DataStatus.CONSOLIDATED,
        )
        july_energy = DailyEnergy(
            device_id=device.id,
            production_date=date(2026, 7, 31),
            energy_kwh=Decimal("120"),
            status=DataStatus.CONSOLIDATED,
        )
        session.add_all([june, july, june_energy, july_energy])
        await session.commit()

        june_snapshot = await materialize_monthly_report_snapshot(
            session,
            bill_id=june.id,
            plant_id=plant.id,
        )
        assert june_snapshot.report.bill_id == june.id
        assert june_snapshot.report.reference_month == "2026-06"

        july_snapshot = await get_or_materialize_latest_monthly_report_snapshot(
            session,
            plant_id=plant.id,
        )
        assert july_snapshot.report.bill_id == july.id
        assert july_snapshot.report.reference_month == "2026-07"
        original_metrics = july_snapshot.report.metrics

        july_energy.energy_kwh = Decimal("999")
        await session.flush()
        repeated = await materialize_monthly_report_snapshot(
            session,
            bill_id=july.id,
            plant_id=plant.id,
        )

        assert repeated.id == july_snapshot.id
        assert repeated.payload_sha256 == july_snapshot.payload_sha256
        assert repeated.report.metrics == original_metrics
        count = await session.scalar(select(func.count(MonthlyReportSnapshotRecord.id)))
        assert count == 2

    await engine.dispose()


@pytest.mark.asyncio
async def test_snapshot_repository_detects_payload_tampering() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Integrity plant")
        session.add(plant)
        await session.flush()
        device = Device(plant_id=plant.id, serial_number="SNAPSHOT-002")
        session.add(device)
        await session.flush()
        bill = _bill(
            plant_id=plant.id,
            reference_month="2026-06",
            cycle_day=date(2026, 6, 30),
            source_hash="3" * 64,
        )
        session.add_all(
            [
                bill,
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 6, 30),
                    energy_kwh=Decimal("100"),
                    status=DataStatus.CONSOLIDATED,
                ),
            ]
        )
        await session.commit()

        snapshot = await materialize_monthly_report_snapshot(
            session,
            bill_id=bill.id,
            plant_id=plant.id,
        )
        bill_id = bill.id
        plant_id = plant.id
        record = await session.get(MonthlyReportSnapshotRecord, snapshot.id)
        assert record is not None
        record.payload_json = record.payload_json.replace("HEALTHY", "CRITICAL")
        await session.flush()
        session.expire_all()

        with pytest.raises(ReportSnapshotIntegrityError, match="checksum mismatch"):
            await MonthlyReportSnapshotRepository(session).by_bill_id(
                bill_id,
                plant_id=plant_id,
            )

    await engine.dispose()
