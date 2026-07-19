from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.billing.read_repository import ConfirmedBillReadRepository
from mplacas.core.authorization import PlantScope, UNRESTRICTED_PLANT_SCOPE
from mplacas.intelligence.cycle_service import analyze_confirmed_cycle
from mplacas.intelligence.trends import (
    EnergyCycleComparison,
    EnergyCycleSnapshot,
    TrendDirection,
    compare_energy_cycles,
)


class EnergyHistoryNotFoundError(LookupError):
    """There are not enough confirmed cycles to build a comparison."""


@dataclass(frozen=True, slots=True)
class HistoricalDiagnostic:
    code: str
    severity: str
    message: str
    recommended_action: str


@dataclass(frozen=True, slots=True)
class PersistedEnergyTrend:
    plant_id: uuid.UUID
    comparison: EnergyCycleComparison
    diagnostics: tuple[HistoricalDiagnostic, ...]


def _snapshot(result) -> EnergyCycleSnapshot:
    reconciliation = result.intelligence.reconciliation
    return EnergyCycleSnapshot(
        reference_month=result.reference_month,
        production_kwh=reconciliation.cycle_production_kwh,
        total_consumption_kwh=reconciliation.estimated_total_consumption_kwh,
        imported_kwh=reconciliation.imported_kwh,
        self_sufficiency_percent=reconciliation.self_sufficiency_rate_percent,
        health_score=result.intelligence.health_score,
    )


def _diagnostics(comparison: EnergyCycleComparison) -> tuple[HistoricalDiagnostic, ...]:
    items: list[HistoricalDiagnostic] = []
    if comparison.production.direction is TrendDirection.DOWN:
        items.append(
            HistoricalDiagnostic(
                code="PRODUCTION_TREND_DOWN",
                severity="WARNING",
                message="A produção do ciclo atual caiu em relação ao ciclo anterior.",
                recommended_action=(
                    "Comparar clima, disponibilidade, comunicação, sombreamento "
                    "e limpeza dos módulos."
                ),
            )
        )
    elif comparison.production.direction is TrendDirection.UP:
        items.append(
            HistoricalDiagnostic(
                code="PRODUCTION_TREND_UP",
                severity="INFO",
                message="A produção do ciclo atual aumentou em relação ao ciclo anterior.",
                recommended_action=(
                    "Manter o acompanhamento para confirmar a tendência nos próximos ciclos."
                ),
            )
        )
    if comparison.imported_energy.direction is TrendDirection.UP:
        items.append(
            HistoricalDiagnostic(
                code="GRID_IMPORT_TREND_UP",
                severity="WARNING",
                message="A energia importada da rede aumentou em relação ao ciclo anterior.",
                recommended_action=(
                    "Revisar a evolução do consumo e a distribuição das cargas "
                    "ao longo do dia."
                ),
            )
        )
    if comparison.self_sufficiency_delta_points <= Decimal("-5.0"):
        items.append(
            HistoricalDiagnostic(
                code="SELF_SUFFICIENCY_DECLINED",
                severity="WARNING",
                message="A autossuficiência caiu pelo menos 5 pontos percentuais.",
                recommended_action=(
                    "Verificar simultaneamente geração, consumo e importação da rede."
                ),
            )
        )
    if comparison.health_score_delta <= -10:
        items.append(
            HistoricalDiagnostic(
                code="HEALTH_SCORE_DECLINED",
                severity="CRITICAL",
                message="O índice de saúde caiu pelo menos 10 pontos.",
                recommended_action=(
                    "Priorizar a revisão dos diagnósticos e da qualidade dos dados "
                    "do ciclo atual."
                ),
            )
        )
    if not items:
        items.append(
            HistoricalDiagnostic(
                code="HISTORICAL_TREND_STABLE",
                severity="INFO",
                message=(
                    "Não foram identificadas variações históricas relevantes "
                    "pelos critérios atuais."
                ),
                recommended_action="Manter o acompanhamento periódico dos ciclos confirmados.",
            )
        )
    return tuple(items)


async def compare_latest_confirmed_cycles(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    stable_tolerance_percent: Decimal = Decimal("2.0"),
    plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
) -> PersistedEnergyTrend:
    bills = await ConfirmedBillReadRepository(
        session,
        plant_scope=plant_scope,
    ).two_latest(plant_id=plant_id)
    if len(bills) < 2:
        raise EnergyHistoryNotFoundError(
            "at least two confirmed bills are required for the requested plant"
        )
    current_result = await analyze_confirmed_cycle(
        session,
        confirmed_bill=bills[0],
    )
    previous_result = await analyze_confirmed_cycle(
        session,
        confirmed_bill=bills[1],
    )
    comparison = compare_energy_cycles(
        current=_snapshot(current_result),
        previous=_snapshot(previous_result),
        stable_tolerance_percent=stable_tolerance_percent,
    )
    return PersistedEnergyTrend(
        plant_id=plant_id,
        comparison=comparison,
        diagnostics=_diagnostics(comparison),
    )
