"""Serializes a bounded window of closed billing cycles for dashboard charts.

Reads exclusively from :class:`MonthlyReportSnapshotRepository` — never
recomputes or materializes anything (ADR-038). There is no "current cycle"
here: only cycles with a confirmed bill and a persisted snapshot are
represented.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.core.authorization import PlantScope, UNRESTRICTED_PLANT_SCOPE
from mplacas.reports.contract import MonthlyEnergyReport, ReportMetric
from mplacas.reports.snapshot import MonthlyReportSnapshotRepository, ReportSnapshotIntegrityError

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_CYCLES = 12
MAX_HISTORY_CYCLES = 36

_QUALITY_KEYS = (
    "missing_days",
    "provisional_days",
    "incomplete_days",
    "unavailable_days",
)


def _metric_value(metrics: tuple[ReportMetric, ...], key: str) -> str | None:
    for metric in metrics:
        if metric.key == key:
            return metric.value if metric.value != "" else None
    return None


def _int_metric(metrics: tuple[ReportMetric, ...], key: str) -> int | None:
    value = _metric_value(metrics, key)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _quality_payload(metrics: tuple[ReportMetric, ...]) -> dict[str, int | None] | None:
    if not any(_metric_value(metrics, key) is not None for key in _QUALITY_KEYS):
        return None
    return {key: _int_metric(metrics, key) for key in _QUALITY_KEYS}


async def load_monthly_production_history(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
    limit: int,
) -> dict[str, object]:
    snapshots = await MonthlyReportSnapshotRepository(
        session, plant_scope=plant_scope
    ).list_recent_for_plant(plant_id=plant_id, limit=limit)

    cycles: list[dict[str, object]] = []
    for snapshot in snapshots:
        report = snapshot.report
        cycles.append(
            {
                "reference_month": report.reference_month,
                "bill_id": str(report.bill_id),
                "status": report.status,
                "production_kwh": _metric_value(report.metrics, "cycle_production_kwh"),
                "quality": _quality_payload(report.quality),
            }
        )

    return {
        "plant_id": str(plant_id),
        "limit": limit,
        "cycles_returned": len(cycles),
        "cycles": cycles,
    }


async def load_recent_monthly_reports(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
    limit: int = DEFAULT_HISTORY_CYCLES,
) -> tuple[MonthlyEnergyReport, ...]:
    """Relatórios já gravados dos ciclos mais recentes, para o histórico do PDF.

    Mesma leitura estrita de :func:`load_monthly_production_history` (ADR-038):
    nunca materializa nem recalcula — só devolve o que já foi persistido.

    O histórico é complementar: se algum snapshot antigo falhar na checagem de
    integridade, o PDF do ciclo atual sai sem a tabela (e o erro fica no log)
    em vez de o download inteiro falhar por causa de um ciclo passado.
    """
    try:
        snapshots = await MonthlyReportSnapshotRepository(
            session, plant_scope=plant_scope
        ).list_recent_for_plant(plant_id=plant_id, limit=limit)
    except ReportSnapshotIntegrityError:
        logger.error(
            "report_history_snapshot_integrity_failed",
            extra={"plant_id": str(plant_id)},
        )
        return ()
    return tuple(snapshot.report for snapshot in snapshots)
