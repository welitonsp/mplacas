from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.billing.read_repository import ConfirmedBillReadRepository
from mplacas.core.authorization import PlantScope, UNRESTRICTED_PLANT_SCOPE
from mplacas.intelligence.cycle_service import EnergyCycleNotFoundError
from mplacas.reports.db_models import MonthlyReportSnapshotRecord
from mplacas.reports.service import (
    MonthlyEnergyReport,
    MonthlyReportTrend,
    ReportDiagnostic,
    ReportMetric,
    ReportTrendMetric,
    build_monthly_report_for_bill,
    serialize_monthly_report,
)


class ReportSnapshotIntegrityError(ValueError):
    """Stored snapshot payload does not match its immutable metadata."""


@dataclass(frozen=True, slots=True)
class MonthlyReportSnapshot:
    id: uuid.UUID
    report: MonthlyEnergyReport
    payload_sha256: str
    created_at: datetime


def _canonical_payload(report: MonthlyEnergyReport) -> str:
    return json.dumps(
        serialize_monthly_report(report),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _payload_sha256(payload_json: str) -> str:
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _deserialize_report(payload_json: str) -> MonthlyEnergyReport:
    try:
        payload = json.loads(payload_json)
        if not isinstance(payload, dict):
            raise TypeError("snapshot payload must be an object")
        trend_payload = payload["trend"]
        trend: MonthlyReportTrend | None = None
        if trend_payload is not None:
            trend = MonthlyReportTrend(
                current_reference_month=trend_payload["current_reference_month"],
                previous_reference_month=trend_payload["previous_reference_month"],
                metrics=tuple(
                    ReportTrendMetric(**item) for item in trend_payload["metrics"]
                ),
                diagnostics=tuple(
                    ReportDiagnostic(**item) for item in trend_payload["diagnostics"]
                ),
            )
        return MonthlyEnergyReport(
            schema_version=payload["schema_version"],
            calculation_version=payload["calculation_version"],
            plant_id=uuid.UUID(payload["plant_id"]),
            bill_id=uuid.UUID(payload["bill_id"]),
            reference_month=payload["reference_month"],
            status=payload["status"],
            headline=payload["headline"],
            metrics=tuple(ReportMetric(**item) for item in payload["metrics"]),
            quality=tuple(ReportMetric(**item) for item in payload["quality"]),
            diagnostics=tuple(
                ReportDiagnostic(**item) for item in payload["diagnostics"]
            ),
            priority_actions=tuple(payload["priority_actions"]),
            trend=trend,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ReportSnapshotIntegrityError("monthly report snapshot payload is invalid") from exc


def _to_snapshot(record: MonthlyReportSnapshotRecord) -> MonthlyReportSnapshot:
    checksum = _payload_sha256(record.payload_json)
    if not hmac.compare_digest(checksum, record.payload_sha256):
        raise ReportSnapshotIntegrityError("monthly report snapshot checksum mismatch")
    report = _deserialize_report(record.payload_json)
    if (
        report.plant_id != record.plant_id
        or report.bill_id != record.bill_id
        or report.reference_month != record.reference_month
        or report.schema_version != record.schema_version
        or report.calculation_version != record.calculation_version
    ):
        raise ReportSnapshotIntegrityError("monthly report snapshot metadata mismatch")
    return MonthlyReportSnapshot(
        id=record.id,
        report=report,
        payload_sha256=record.payload_sha256,
        created_at=record.created_at,
    )


class MonthlyReportSnapshotRepository:
    def __init__(
        self,
        session: AsyncSession,
        *,
        plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
    ) -> None:
        self._session = session
        self._plant_scope = plant_scope

    async def by_bill_id(
        self,
        bill_id: uuid.UUID,
        *,
        plant_id: uuid.UUID,
    ) -> MonthlyReportSnapshot | None:
        if not self._plant_scope.allows(plant_id):
            return None
        record = await self._session.scalar(
            select(MonthlyReportSnapshotRecord).where(
                MonthlyReportSnapshotRecord.bill_id == bill_id,
                MonthlyReportSnapshotRecord.plant_id == plant_id,
            )
        )
        return _to_snapshot(record) if record is not None else None

    async def latest(self, *, plant_id: uuid.UUID) -> MonthlyReportSnapshot | None:
        if not self._plant_scope.allows(plant_id):
            return None
        record = await self._session.scalar(
            select(MonthlyReportSnapshotRecord)
            .where(MonthlyReportSnapshotRecord.plant_id == plant_id)
            .order_by(
                desc(MonthlyReportSnapshotRecord.reference_month),
                desc(MonthlyReportSnapshotRecord.created_at),
            )
            .limit(1)
        )
        return _to_snapshot(record) if record is not None else None

    async def create(self, report: MonthlyEnergyReport) -> MonthlyReportSnapshot:
        if not self._plant_scope.allows(report.plant_id):
            raise PermissionError("plant is outside the report snapshot scope")
        existing = await self.by_bill_id(report.bill_id, plant_id=report.plant_id)
        if existing is not None:
            return existing

        payload_json = _canonical_payload(report)
        record = MonthlyReportSnapshotRecord(
            plant_id=report.plant_id,
            bill_id=report.bill_id,
            reference_month=report.reference_month,
            schema_version=report.schema_version,
            calculation_version=report.calculation_version,
            payload_json=payload_json,
            payload_sha256=_payload_sha256(payload_json),
        )
        try:
            async with self._session.begin_nested():
                self._session.add(record)
                await self._session.flush()
        except IntegrityError:
            concurrent = await self.by_bill_id(report.bill_id, plant_id=report.plant_id)
            if concurrent is None:
                raise
            return concurrent
        await self._session.refresh(record)
        return _to_snapshot(record)


async def materialize_monthly_report_snapshot(
    session: AsyncSession,
    *,
    bill_id: uuid.UUID,
    plant_id: uuid.UUID,
    plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
) -> MonthlyReportSnapshot:
    repository = MonthlyReportSnapshotRepository(session, plant_scope=plant_scope)
    existing = await repository.by_bill_id(bill_id, plant_id=plant_id)
    if existing is not None:
        return existing
    report = await build_monthly_report_for_bill(
        session,
        bill_id=bill_id,
        plant_id=plant_id,
        plant_scope=plant_scope,
    )
    return await repository.create(report)


async def get_or_materialize_latest_monthly_report_snapshot(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
) -> MonthlyReportSnapshot:
    latest_bill = await ConfirmedBillReadRepository(
        session,
        plant_scope=plant_scope,
    ).latest(plant_id=plant_id)
    if latest_bill is None:
        raise EnergyCycleNotFoundError("confirmed bill not found for plant")
    return await materialize_monthly_report_snapshot(
        session,
        bill_id=latest_bill.id,
        plant_id=plant_id,
        plant_scope=plant_scope,
    )
