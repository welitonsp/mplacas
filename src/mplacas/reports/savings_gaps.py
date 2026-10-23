"""Meses com fatura confirmada sem economia ou com economia desatualizada (ADR-081).

O relatório mensal de cada fatura é imutável (ADR-038) e é dele que o retorno
do investimento (ADR-067) e o painel do investidor (ADR-079) somam a economia.
Uma fatura confirmada pode ficar fora dessa soma para sempre quando:

- ``REPORT_MISSING`` — a fatura foi confirmada antes de existir relatório;
- ``REPORT_PREDATES_SAVINGS`` — o relatório é anterior ao cálculo de economia
  e não tem a métrica ``estimated_savings_brl``;
- ``SAVINGS_UNAVAILABLE`` — o relatório tem a métrica, mas vazia, com o motivo
  gravado (tarifa não lida na fatura, ou sem consumo/telemetria no ciclo);
- ``OUTDATED_CALCULATION`` — a economia existe, mas foi calculada antes da
  correção da fórmula (versão < 0.4.0: conta "sem a usina" pela tarifa SCEE,
  ADR-080) ou sem a tarifa cheia do período (``BILL_TARIFF``). É um piso.

Este módulo lista esses meses e, sob pedido explícito de um ADMIN, refaz o
relatório. O relatório antigo nunca é alterado nem apagado: o novo entra como
revisão seguinte da mesma fatura, e a auditoria registra qual revisão nasceu.
Um mês com economia calculada pela fórmula corrigida nunca é reprocessado.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.billing.read_repository import ConfirmedBillReadRepository
from mplacas.core.authorization import PlantScope, UNRESTRICTED_PLANT_SCOPE
from mplacas.intelligence.energy_engine import SAVINGS_TARIFF_BILL
from mplacas.intelligence.investor_service import (
    CORRECTED_CALCULATION_VERSION,
    calculation_version_tuple,
)
from mplacas.reports.contract import MonthlyEnergyReport
from mplacas.reports.projection import build_monthly_report_for_bill
from mplacas.reports.snapshot_revisions import create_snapshot_revision
from mplacas.reports.snapshot import (
    MonthlyReportSnapshot,
    MonthlyReportSnapshotRepository,
)

SAVINGS_METRIC_KEY = "estimated_savings_brl"
SAVINGS_REASON_METRIC_KEY = "savings_unavailable_reason"
SAVINGS_TARIFF_SOURCE_METRIC_KEY = "savings_tariff_source"


class SavingsGapCause(str, enum.Enum):
    REPORT_MISSING = "REPORT_MISSING"
    REPORT_PREDATES_SAVINGS = "REPORT_PREDATES_SAVINGS"
    SAVINGS_UNAVAILABLE = "SAVINGS_UNAVAILABLE"
    OUTDATED_CALCULATION = "OUTDATED_CALCULATION"


class ReprocessOutcome(str, enum.Enum):
    RECALCULATED = "RECALCULATED"
    STILL_UNAVAILABLE = "STILL_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class SavingsGap:
    bill_id: uuid.UUID
    reference_month: str
    cause: SavingsGapCause
    # Só preenchido em SAVINGS_UNAVAILABLE: o motivo que o motor gravou.
    savings_unavailable_reason: str | None
    current_revision: int | None
    # Economia gravada hoje (só em OUTDATED_CALCULATION), para mostrar o antes.
    previous_savings_brl: str | None = None


@dataclass(frozen=True, slots=True)
class ReprocessResult:
    bill_id: uuid.UUID
    reference_month: str
    previous_cause: SavingsGapCause
    previous_savings_brl: str | None
    outcome: ReprocessOutcome
    estimated_savings_brl: str | None
    savings_unavailable_reason: str | None
    # Revisão gravada por este reprocessamento; None quando nada mudou.
    stored_revision: int | None
    snapshot_id: uuid.UUID | None


def _metric_value(report: MonthlyEnergyReport, key: str) -> str | None:
    """Valor da métrica; ``None`` quando a métrica nem existe no relatório."""
    metric = next((item for item in report.metrics if item.key == key), None)
    return None if metric is None else metric.value


def _gap_for(
    bill_id: uuid.UUID,
    reference_month: str,
    snapshot: MonthlyReportSnapshot | None,
) -> SavingsGap | None:
    if snapshot is None:
        return SavingsGap(bill_id, reference_month, SavingsGapCause.REPORT_MISSING, None, None)
    savings = _metric_value(snapshot.report, SAVINGS_METRIC_KEY)
    if savings is None:
        return SavingsGap(
            bill_id,
            reference_month,
            SavingsGapCause.REPORT_PREDATES_SAVINGS,
            None,
            snapshot.revision,
        )
    if savings == "":
        reason = _metric_value(snapshot.report, SAVINGS_REASON_METRIC_KEY) or None
        return SavingsGap(
            bill_id,
            reference_month,
            SavingsGapCause.SAVINGS_UNAVAILABLE,
            reason,
            snapshot.revision,
        )
    outdated = calculation_version_tuple(
        snapshot.report.calculation_version
    ) < CORRECTED_CALCULATION_VERSION or (
        _metric_value(snapshot.report, SAVINGS_TARIFF_SOURCE_METRIC_KEY) == SAVINGS_TARIFF_BILL
    )
    if outdated:
        return SavingsGap(
            bill_id,
            reference_month,
            SavingsGapCause.OUTDATED_CALCULATION,
            None,
            snapshot.revision,
            previous_savings_brl=savings,
        )
    return None


async def list_savings_gaps(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
) -> tuple[SavingsGap, ...]:
    """Faturas confirmadas cujo relatório vigente não entrega economia.

    Leitura pura: não materializa nem grava nada.
    """
    bills = await ConfirmedBillReadRepository(session, plant_scope=plant_scope).list_for_plant(
        plant_id=plant_id
    )
    snapshots = MonthlyReportSnapshotRepository(session, plant_scope=plant_scope)
    gaps: list[SavingsGap] = []
    for confirmed in bills:
        snapshot = await snapshots.by_bill_id(confirmed.id, plant_id=plant_id)
        gap = _gap_for(confirmed.id, confirmed.bill.reference_month, snapshot)
        if gap is not None:
            gaps.append(gap)
    return tuple(gaps)


def _result(
    gap: SavingsGap,
    snapshot: MonthlyReportSnapshot,
    *,
    stored: bool,
) -> ReprocessResult:
    savings = _metric_value(snapshot.report, SAVINGS_METRIC_KEY) or None
    return ReprocessResult(
        bill_id=gap.bill_id,
        reference_month=gap.reference_month,
        previous_cause=gap.cause,
        previous_savings_brl=gap.previous_savings_brl,
        outcome=(
            ReprocessOutcome.RECALCULATED
            if savings is not None
            else ReprocessOutcome.STILL_UNAVAILABLE
        ),
        estimated_savings_brl=savings,
        savings_unavailable_reason=(
            None
            if savings is not None
            else _metric_value(snapshot.report, SAVINGS_REASON_METRIC_KEY) or None
        ),
        stored_revision=snapshot.revision if stored else None,
        snapshot_id=snapshot.id if stored else None,
    )


async def reprocess_savings_gaps(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
) -> tuple[ReprocessResult, ...]:
    """Refaz o relatório de cada lacuna; não faz commit (o chamador faz).

    Regras (ADR-081):

    - sem relatório → grava a revisão 1, como a confirmação teria feito;
    - relatório sem a métrica → grava a revisão seguinte, mesmo que a economia
      continue indisponível: o motivo passa a ficar registrado;
    - métrica vazia → só grava revisão nova se agora houver economia (ex.: a
      telemetria do ciclo chegou depois);
    - cálculo desatualizado → só grava revisão nova se a economia ou a origem
      da tarifa mudarem (ex.: a vigência do período foi cadastrada).
    Se nada mudou, não grava nada, para não acumular revisões idênticas a
    cada clique.
    """
    repository = MonthlyReportSnapshotRepository(session, plant_scope=plant_scope)
    results: list[ReprocessResult] = []
    for gap in await list_savings_gaps(session, plant_id=plant_id, plant_scope=plant_scope):
        previous = await repository.by_bill_id(gap.bill_id, plant_id=plant_id)
        if previous is None:
            created = await repository.create(
                await build_monthly_report_for_bill(
                    session, bill_id=gap.bill_id, plant_id=plant_id, plant_scope=plant_scope
                )
            )
            results.append(_result(gap, created, stored=True))
            continue
        report = await build_monthly_report_for_bill(
            session, bill_id=gap.bill_id, plant_id=plant_id, plant_scope=plant_scope
        )
        has_savings_now = bool(_metric_value(report, SAVINGS_METRIC_KEY))
        if gap.cause is SavingsGapCause.SAVINGS_UNAVAILABLE and not has_savings_now:
            results.append(_result(gap, previous, stored=False))
            continue
        if gap.cause is SavingsGapCause.OUTDATED_CALCULATION and all(
            _metric_value(report, key) == _metric_value(previous.report, key)
            for key in (SAVINGS_METRIC_KEY, SAVINGS_TARIFF_SOURCE_METRIC_KEY)
        ):
            results.append(_result(gap, previous, stored=False))
            continue
        revision = await create_snapshot_revision(
            session, report, previous=previous, plant_scope=plant_scope
        )
        if revision is None:
            # Outra requisição gravou a mesma revisão ao mesmo tempo: vale a dela.
            current = await repository.by_bill_id(gap.bill_id, plant_id=plant_id)
            if current is None:  # pragma: no cover - a revisão concorrente existe
                raise RuntimeError("concurrent report revision vanished")
            results.append(_result(gap, current, stored=False))
            continue
        results.append(_result(gap, revision, stored=True))
    return tuple(results)
