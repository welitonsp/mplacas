from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.billing.read_repository import ConfirmedBillReadRepository
from mplacas.core.authorization import PlantScope, UNRESTRICTED_PLANT_SCOPE
from mplacas.intelligence.cycle_service import (
    EnergyCycleNotFoundError,
    PersistedCycleIntelligence,
    analyze_confirmed_cycle,
)
from mplacas.intelligence.history_service import (
    EnergyHistoryNotFoundError,
    PersistedEnergyTrend,
    compare_confirmed_cycle_with_previous,
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
    for current_diagnostic in current.intelligence.diagnostics:
        if current_diagnostic.recommended_action not in actions:
            actions.append(current_diagnostic.recommended_action)
    if trend is not None:
        for trend_diagnostic in trend.diagnostics:
            if trend_diagnostic.recommended_action not in actions:
                actions.append(trend_diagnostic.recommended_action)
    return tuple(actions[:limit])


async def build_executive_dashboard(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    expected_production_kwh: Decimal | None = None,
    stable_tolerance_percent: Decimal = Decimal("2.0"),
    plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
) -> ExecutiveEnergyDashboard:
    latest_bill = await ConfirmedBillReadRepository(
        session,
        plant_scope=plant_scope,
    ).latest(plant_id=plant_id)
    if latest_bill is None:
        raise EnergyCycleNotFoundError("confirmed bill not found for plant")
    current = await analyze_confirmed_cycle(
        session,
        confirmed_bill=latest_bill,
        expected_production_kwh=expected_production_kwh,
    )
    trend: PersistedEnergyTrend | None
    try:
        trend = await compare_latest_confirmed_cycles(
            session,
            plant_id=plant_id,
            stable_tolerance_percent=stable_tolerance_percent,
            plant_scope=plant_scope,
        )
    except EnergyHistoryNotFoundError:
        trend = None
    return assemble_executive_dashboard(current=current, trend=trend)


async def build_executive_dashboard_for_bill(
    session: AsyncSession,
    *,
    bill_id: uuid.UUID,
    plant_id: uuid.UUID,
    expected_production_kwh: Decimal | None = None,
    stable_tolerance_percent: Decimal = Decimal("2.0"),
    plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
) -> ExecutiveEnergyDashboard:
    confirmed_bill = await ConfirmedBillReadRepository(
        session,
        plant_scope=plant_scope,
    ).by_id(bill_id, plant_id=plant_id)
    if confirmed_bill is None:
        raise EnergyCycleNotFoundError("confirmed bill not found for plant")
    current = await analyze_confirmed_cycle(
        session,
        confirmed_bill=confirmed_bill,
        expected_production_kwh=expected_production_kwh,
    )
    try:
        trend = await compare_confirmed_cycle_with_previous(
            session,
            current_bill=confirmed_bill,
            stable_tolerance_percent=stable_tolerance_percent,
            plant_scope=plant_scope,
        )
    except EnergyHistoryNotFoundError:
        trend = None
    return assemble_executive_dashboard(current=current, trend=trend)


def assemble_executive_dashboard(
    *,
    current: PersistedCycleIntelligence,
    trend: PersistedEnergyTrend | None,
) -> ExecutiveEnergyDashboard:
    status = _status_for_cycle(current)
    return ExecutiveEnergyDashboard(
        plant_id=current.plant_id,
        status=status,
        current_cycle=current,
        trend=trend,
        headline=_headline(status, current),
        priority_actions=_priority_actions(current, trend),
    )
