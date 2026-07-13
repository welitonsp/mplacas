from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.billing.db_models import BillStatus, UtilityBillRecord
from mplacas.intelligence.cycle_service import (
    EnergyCycleNotFoundError,
    PersistedCycleIntelligence,
    analyze_persisted_cycle,
)
from mplacas.intelligence.history_service import (
    EnergyHistoryNotFoundError,
    PersistedEnergyTrend,
    compare_latest_confirmed_cycles,
)


class ExecutiveStatus(StrEnum):
    HEALTHY = "HEALTHY"
    ATTENTION = "ATTENTION"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class ExecutiveEnergyDashboard:
    plant_id: uuid.UUID
    status: ExecutiveStatus
    current_cycle: PersistedCycleIntelligence
    trend: PersistedEnergyTrend | None
    headline: str
    priority_actions: tuple[str, ...]


def _status_for_cycle(result: PersistedCycleIntelligence) -> ExecutiveStatus:
    severities = {item.severity.value for item in result.intelligence.diagnostics}
    if "CRITICAL" in severities or result.intelligence.health_score < 60:
        return ExecutiveStatus.CRITICAL
    if "WARNING" in severities or result.intelligence.health_score < 85:
        return ExecutiveStatus.ATTENTION
    return ExecutiveStatus.HEALTHY


def _headline(status: ExecutiveStatus, result: PersistedCycleIntelligence) -> str:
    score = result.intelligence.health_score
    reference = result.reference_month
    if status is ExecutiveStatus.CRITICAL:
        return f"Ciclo {reference} exige atuação prioritária; índice de saúde {score}/100."
    if status is ExecutiveStatus.ATTENTION:
        return f"Ciclo {reference} requer acompanhamento; índice de saúde {score}/100."
    return f"Ciclo {reference} está dentro dos parâmetros avaliados; índice de saúde {score}/100."


def _priority_actions(
    current: PersistedCycleIntelligence,
    trend: PersistedEnergyTrend | None,
    *,
    limit: int = 5,
) -> tuple[str, ...]:
    actions: list[str] = []
    for diagnostic in current.intelligence.diagnostics:
        if diagnostic.recommended_action not in actions:
            actions.append(diagnostic.recommended_action)
    if trend is not None:
        for diagnostic in trend.diagnostics:
            if diagnostic.recommended_action not in actions:
                actions.append(diagnostic.recommended_action)
    return tuple(actions[:limit])


async def build_executive_dashboard(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    expected_production_kwh: Decimal | None = None,
    stable_tolerance_percent: Decimal = Decimal("2.0"),
) -> ExecutiveEnergyDashboard:
    latest_bill = await session.scalar(
        select(UtilityBillRecord)
        .where(
            UtilityBillRecord.status == BillStatus.CONFIRMED,
            UtilityBillRecord.plant_id == plant_id,
        )
        .order_by(desc(UtilityBillRecord.cycle_end), desc(UtilityBillRecord.created_at))
        .limit(1)
    )
    if latest_bill is None:
        raise EnergyCycleNotFoundError("confirmed bill not found for plant")

    current = await analyze_persisted_cycle(
        session,
        bill_id=latest_bill.id,
        plant_id=plant_id,
        expected_production_kwh=expected_production_kwh,
    )

    trend: PersistedEnergyTrend | None
    try:
        trend = await compare_latest_confirmed_cycles(
            session,
            plant_id=plant_id,
            stable_tolerance_percent=stable_tolerance_percent,
        )
    except EnergyHistoryNotFoundError:
        trend = None

    status = _status_for_cycle(current)
    return ExecutiveEnergyDashboard(
        plant_id=plant_id,
        status=status,
        current_cycle=current,
        trend=trend,
        headline=_headline(status, current),
        priority_actions=_priority_actions(current, trend),
    )
