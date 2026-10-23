"""Nova revisão de um relatório mensal já gravado (ADR-081).

Separado de ``snapshot.py`` para manter aquele módulo focado na
materialização imutável (ADR-038). Uma revisão nunca altera a anterior:
entra ao lado, com ``revision`` + 1, e os leitores usam a maior.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.core.authorization import PlantScope, UNRESTRICTED_PLANT_SCOPE
from mplacas.reports.contract import MonthlyEnergyReport
from mplacas.reports.db_models import MonthlyReportSnapshotRecord
from mplacas.reports.snapshot import (
    MonthlyReportSnapshot,
    _canonical_payload,
    _payload_sha256,
    _to_snapshot,
)


async def create_snapshot_revision(
    session: AsyncSession,
    report: MonthlyEnergyReport,
    *,
    previous: MonthlyReportSnapshot,
    plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
) -> MonthlyReportSnapshot | None:
    """Grava a revisão seguinte a ``previous`` para a mesma fatura.

    Devolve ``None`` quando outra requisição gravou a mesma revisão ao mesmo
    tempo (a unicidade ``(bill_id, revision)`` decide quem fica) — o
    chamador relê.
    """
    if not plant_scope.allows(report.plant_id):
        raise PermissionError("plant is outside the report snapshot scope")
    if report.bill_id != previous.report.bill_id or report.plant_id != previous.report.plant_id:
        raise ValueError("revision must belong to the same bill and plant")
    payload_json = _canonical_payload(report)
    record = MonthlyReportSnapshotRecord(
        plant_id=report.plant_id,
        bill_id=report.bill_id,
        reference_month=report.reference_month,
        revision=previous.revision + 1,
        schema_version=report.schema_version,
        calculation_version=report.calculation_version,
        payload_json=payload_json,
        payload_sha256=_payload_sha256(payload_json),
    )
    try:
        async with session.begin_nested():
            session.add(record)
            await session.flush()
    except IntegrityError:
        return None
    await session.refresh(record)
    return _to_snapshot(record)
