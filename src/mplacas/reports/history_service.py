"""Serializes a bounded window of closed billing cycles for dashboard charts.

Reads exclusively from :class:`MonthlyReportSnapshotRepository` — never
recomputes or materializes anything (ADR-038). There is no "current cycle"
here: only cycles with a confirmed bill and a persisted snapshot are
represented.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.billing.read_repository import ConfirmedBillReadRepository
from mplacas.billing.models import UtilityBill
from mplacas.intelligence.energy_engine import SAVINGS_TARIFF_BILL
from mplacas.core.authorization import PlantScope, UNRESTRICTED_PLANT_SCOPE
from mplacas.db.models import Plant
from mplacas.intelligence.investor_service import (
    calculation_version_tuple,
    commissioning_month,
    counts_in_savings,
)
from mplacas.reports.contract import MonthlyEnergyReport, ReportMetric
from mplacas.reports.savings_gaps import (
    SAVINGS_METRIC_KEY,
    SAVINGS_REASON_METRIC_KEY,
    SAVINGS_TARIFF_SOURCE_METRIC_KEY,
    SavingsGapCause,
    savings_gap_cause,
)
from mplacas.reports.snapshot import (
    MonthlyReportSnapshot,
    MonthlyReportSnapshotRepository,
    ReportSnapshotIntegrityError,
)
from mplacas.reports.utility_check import (
    check_cycle,
    credit_unit_value_brl,
    missing_credits_value_brl,
)

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_CYCLES = 12
MAX_HISTORY_CYCLES = 36

_QUALITY_KEYS = (
    "missing_days",
    "provisional_days",
    "incomplete_days",
    "unavailable_days",
    "estimated_production_days",
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


# A injeção do medidor (`generation_cycle_kwh`) entrou no cálculo na versão
# 0.3.0 (ADR-078). Snapshots anteriores são imutáveis (ADR-038) e guardaram a
# linha de injeção da fatura — no layout SCEE, a energia COMPENSADA, não a
# medida. Mesmo em 0.3.0+, `reconcile_bill` cai nessa linha quando a fatura
# não traz a leitura do medidor.
METERED_INJECTION_VERSION = (0, 3, 0)


def _grid_injection_basis(
    *, injection: str | None, calculation_version: str, bill: UtilityBill | None
) -> str | None:
    """De onde veio a injeção gravada no snapshot: METER, BILL_LINE ou None.

    METER só quando há prova: snapshot 0.3.0+ e o valor gravado é IGUAL à
    leitura do medidor da fatura. Não basta a fatura ter a leitura hoje: o PDF
    pode completá-la depois do snapshot (`billing/completion.py`, ADR-081), e
    o snapshot continua com a linha da fatura até o mês ser reprocessado.
    Qualquer dúvida vira BILL_LINE — a tela nunca rotula como "medidor" o que
    pode ser compensação.
    """
    if injection is None:
        return None
    if (
        calculation_version_tuple(calculation_version) < METERED_INJECTION_VERSION
        or bill is None
        or bill.generation_cycle_kwh is None
    ):
        return "BILL_LINE"
    try:
        recorded = Decimal(injection)
    except InvalidOperation:
        return "BILL_LINE"
    return "METER" if recorded == bill.generation_cycle_kwh else "BILL_LINE"


def _previous_month(reference_month: str) -> str:
    year, month = (int(part) for part in reference_month.split("-"))
    return f"{year - 1}-12" if month == 1 else f"{year}-{month - 1:02d}"


def _decimal_or_none(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _metric_or_absent(metrics: tuple[ReportMetric, ...], key: str) -> str | None:
    """Valor cru da métrica; ``None`` só quando ela NÃO existe no snapshot.

    Diferente de :func:`_metric_value`, que trata métrica ausente e métrica
    vazia do mesmo jeito: para a economia, ausente = snapshot anterior à
    métrica; vazia = indisponível, com motivo gravado.
    """
    for metric in metrics:
        if metric.key == key:
            return metric.value
    return None


def _money(value: Decimal | None) -> str | None:
    """Valor monetário dos campos NOVOS, sempre em notação posicional.

    ``format(..., "f")`` evita ``1E+2``; não arredonda nem quantiza o gravado.
    """
    return None if value is None else format(value, "f")


def _superseded_by_rebilling(reference_months: list[str]) -> list[bool]:
    """Por ciclo: ``True`` se outro ciclo do MESMO mês o substitui na janela.

    Regra do refaturamento, a mesma de ``expansion_service`` ("o mais recente
    do refaturamento vence"): a lista de ciclos vem ordenada por mês e, dentro
    do mês, por ``created_at`` do snapshot (``list_recent_for_plant``); o ÚLTIMO
    ciclo de cada mês é o que vale, igual ao ``by_month[month] = cycle`` que
    sobrescreve na iteração daquele serviço.
    """
    last_index = {month: index for index, month in enumerate(reference_months)}
    return [last_index[month] != index for index, month in enumerate(reference_months)]


def _savings_fields(
    snapshot: MonthlyReportSnapshot, bill: UtilityBill | None
) -> tuple[Decimal | None, dict[str, object]]:
    """Economia do ciclo tal como gravada no snapshot (nada recalculado)."""
    metrics = snapshot.report.metrics
    raw = _metric_or_absent(metrics, SAVINGS_METRIC_KEY)
    value: Decimal | None = None
    reason: str | None = None
    cause = savings_gap_cause(snapshot, bill)
    if raw is None:
        reason = SavingsGapCause.REPORT_PREDATES_SAVINGS.value
    else:
        value = _decimal_or_none(raw) if raw != "" else None
        if value is not None and not value.is_finite():
            value = None
        if value is None:
            # Vazia (indisponível) ou ilegível: nunca vira zero.
            reason = (
                _metric_value(metrics, SAVINGS_REASON_METRIC_KEY)
                or SavingsGapCause.SAVINGS_UNAVAILABLE.value
            )
            cause = SavingsGapCause.SAVINGS_UNAVAILABLE
    return value, {
        # Pode ser NEGATIVA (a conta "sem a usina" pode dar menos que a fatura):
        # nunca truncar nem trocar null por "0".
        "estimated_savings_brl": _money(value),
        "savings_unavailable_reason": reason,
        "savings_tariff_source": _metric_value(metrics, SAVINGS_TARIFF_SOURCE_METRIC_KEY),
        "savings_gap_cause": None if cause is None else cause.value,
        "calculation_version": snapshot.report.calculation_version,
        "report_revision": snapshot.revision,
        "report_created_at": snapshot.created_at.isoformat(),
    }


@dataclass(frozen=True)
class _CycleFacts:
    """Fatos do ciclo que alimentam a janela (valores ainda em ``Decimal``)."""

    cycle: dict[str, object]
    saving: Decimal | None
    bill_amount: Decimal | None
    superseded: bool
    counts: bool


def _savings_window(
    facts: list[_CycleFacts], *, commissioning_known: bool
) -> dict[str, object]:
    """Totais da janela, em ``Decimal``, só com o que já está nos ciclos.

    A lista de ciclos devolve TODOS os ciclos; a janela aplica duas regras de
    dinheiro, as mesmas do painel do investidor e da expansão:

    - Refaturamento: dois ciclos do mesmo mês ficam na lista, mas só um conta
      (o mais recente, ver :func:`_superseded_by_rebilling`) — para economia e
      para o total da fatura.
    - Mês de ligação (ADR-079): só contam meses ESTRITAMENTE posteriores a ele
      (:func:`counts_in_savings`). Vale para a economia; o total da fatura
      inclui esses ciclos (valor de face da fatura, não estimativa).

    Contadores (identidade que sempre vale)::

        cycles_in_window = cycles_with_savings + cycles_without_savings
                           + cycles_excluded_commissioning
                           + cycles_superseded_by_rebilling

    - ``cycles_superseded_by_rebilling``: ciclos que perderam para um
      refaturamento, qualquer que seja o valor (contam só aqui).
    - Entre os demais: ``cycles_without_savings`` = sem valor de economia;
      ``cycles_excluded_commissioning`` = com valor, mas mês <= mês de ligação;
      ``cycles_with_savings`` = com valor e dentro da regra (entram na soma).
    - ``commissioning_known``: a usina tem data de ligação (e foi lida). Sem
      ela nada é excluído e os totais seguem calculados.
    - Contadores de tarifa/defasagem olham só os ciclos que contribuem.
    - ``cycles_with_bill_amount``: cobertura própria do total da fatura (ciclos
      não substituídos cuja fatura segue entre as confirmadas).
    """
    kept = [f for f in facts if not f.superseded]
    contributing = [f for f in kept if f.saving is not None and f.counts]
    without = sum(1 for f in kept if f.saving is None)
    excluded = sum(1 for f in kept if f.saving is not None and not f.counts)
    total: Decimal | None = None
    if contributing:
        total = sum((f.saving for f in contributing if f.saving is not None), Decimal("0"))
    bill_amounts = [f.bill_amount for f in kept if f.bill_amount is not None]
    months = [str(f.cycle["reference_month"]) for f in contributing]
    return {
        "total_estimated_savings_brl": _money(total),
        "cycles_in_window": len(facts),
        "cycles_with_savings": len(contributing),
        "cycles_without_savings": without,
        "cycles_excluded_commissioning": excluded,
        "cycles_superseded_by_rebilling": len(facts) - len(kept),
        "commissioning_known": commissioning_known,
        "first_reference_month": min(months) if months else None,
        "last_reference_month": max(months) if months else None,
        "cycles_with_bill_tariff": sum(
            1 for f in contributing if f.cycle["savings_tariff_source"] == SAVINGS_TARIFF_BILL
        ),
        "cycles_with_outdated_or_partial": sum(
            1
            for f in contributing
            if f.cycle["savings_gap_cause"]
            in (
                SavingsGapCause.OUTDATED_CALCULATION.value,
                SavingsGapCause.PARTIAL_PRODUCTION.value,
            )
        ),
        "total_bill_amount_brl": _money(sum(bill_amounts, Decimal("0")) if bill_amounts else None),
        "cycles_with_bill_amount": len(bill_amounts),
    }


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
    # Datas do ciclo vêm da fatura confirmada (o snapshot só guarda o mês de
    # referência). Uma leitura para a janela inteira, não uma por ciclo.
    confirmed_bills = await ConfirmedBillReadRepository(
        session, plant_scope=plant_scope
    ).list_for_plant(plant_id=plant_id)
    bills = {confirmed.id: confirmed.bill for confirmed in confirmed_bills}
    # Fatura do mês anterior dá o saldo de partida da conferência de créditos.
    # Mais de uma confirmada no mesmo mês (refaturamento) com saldos
    # diferentes deixa o saldo de partida incerto: a conferência não roda.
    bills_by_month: dict[str, list[UtilityBill]] = {}
    for confirmed in confirmed_bills:
        bills_by_month.setdefault(confirmed.bill.reference_month, []).append(confirmed.bill)

    # Mês de ligação da usina: uma leitura para o pedido inteiro, na mesma
    # sessão/contexto RLS. Fora do escopo ou sem data → None (nada é excluído).
    plant = await session.get(Plant, plant_id) if plant_scope.allows(plant_id) else None
    commissioned_month = commissioning_month(plant.commissioned_on if plant else None)
    superseded_flags = _superseded_by_rebilling([s.report.reference_month for s in snapshots])

    cycles: list[dict[str, object]] = []
    facts: list[_CycleFacts] = []
    export_shares: list[Decimal] = []
    for snapshot, superseded in zip(snapshots, superseded_flags, strict=True):
        report = snapshot.report
        bill = bills.get(report.bill_id)
        injection = _metric_value(report.metrics, "injected_kwh")
        production = _decimal_or_none(_metric_value(report.metrics, "cycle_production_kwh"))
        previous_candidates = bills_by_month.get(_previous_month(report.reference_month), [])
        starting_points = {
            (b.credit_balance_kwh, b.credits_expiring_30d_kwh) for b in previous_candidates
        }
        previous_ambiguous = len(starting_points) > 1
        quality = _quality_payload(report.quality) or {}
        # Produção com dias estimados pelo sol ou sem leitura (ADR-082) pode
        # ter sido elevada até a leitura do medidor: não serve de prova.
        production_estimated = any(
            (quality.get(key) or 0) > 0
            for key in ("estimated_production_days", "missing_days", "unavailable_days")
        )
        utility_check = check_cycle(
            bill=bill,
            previous_bill=previous_candidates[0] if previous_candidates else None,
            production_kwh=production,
            previous_export_shares=list(export_shares),
            production_estimated=production_estimated,
            previous_bill_ambiguous=previous_ambiguous,
        )
        share = utility_check.export_share_percent
        if share is not None:
            export_shares.append(share)
        # Valor de 1 kWh de crédito no ciclo, pela tarifa gravada no snapshot
        # (a mesma da economia) — prejuízo em reais, sem recalcular nada.
        unit_value = credit_unit_value_brl(
            savings_tariff_brl_kwh=_decimal_or_none(
                _metric_value(report.metrics, "savings_tariff_brl_kwh")
            ),
            flag_tariff_brl_kwh=_decimal_or_none(
                _metric_value(report.metrics, "flag_tariff_brl_kwh")
            ),
            bill=bill,
            savings_tariff_source=_metric_value(report.metrics, "savings_tariff_source"),
        )
        check_payload = utility_check.as_payload()
        check_payload["credit_unit_value_brl"] = None if unit_value is None else str(unit_value)
        missing_value = missing_credits_value_brl(utility_check, unit_value)
        check_payload["missing_credits_value_brl"] = (
            None if missing_value is None else str(missing_value)
        )
        savings_value, savings_fields = _savings_fields(snapshot, bill)
        is_commissioning = (
            None if commissioned_month is None else report.reference_month == commissioned_month
        )
        facts.append(
            _CycleFacts(
                cycle={},  # preenchido abaixo, junto do dict do ciclo
                saving=savings_value,
                bill_amount=bill.total_amount_brl if bill else None,
                superseded=superseded,
                counts=counts_in_savings(report.reference_month, commissioned_month),
            )
        )
        cycles.append(
            {
                "reference_month": report.reference_month,
                "bill_id": str(report.bill_id),
                "status": report.status,
                "cycle_start": bill.cycle_start.isoformat() if bill else None,
                "cycle_end": bill.cycle_end.isoformat() if bill else None,
                # Placas × distribuidora no MESMO ciclo da fatura (ADR-083,
                # etapa 3), tal como gravado no snapshot — nada recalculado
                # aqui. A injeção vem com a origem (`grid_injection_basis`):
                # medidor ou linha da fatura. O autoconsumo é estimativa do
                # motor (produção do inversor − injeção).
                "production_kwh": _metric_value(report.metrics, "cycle_production_kwh"),
                "grid_injection_kwh": injection,
                "grid_injection_basis": _grid_injection_basis(
                    injection=injection,
                    calculation_version=report.calculation_version,
                    bill=bill,
                ),
                "distributor": bill.distributor if bill else None,
                "imported_kwh": _metric_value(report.metrics, "imported_kwh"),
                "self_consumption_kwh": _metric_value(
                    report.metrics, "estimated_self_consumption_kwh"
                ),
                "quality": _quality_payload(report.quality),
                # Conferência da distribuidora (ADR-084): créditos, envio
                # impossível e fração enviada à rede contra o histórico.
                "utility_check": check_payload,
                # Conta do ciclo (só leitura do snapshot e da fatura confirmada).
                **savings_fields,
                "bill_total_amount_brl": _money(bill.total_amount_brl if bill else None),
                "bill_public_lighting_brl": _money(bill.public_lighting_brl if bill else None),
                "is_commissioning_month": is_commissioning,
                "is_before_commissioning": (
                    None
                    if commissioned_month is None
                    else report.reference_month < commissioned_month
                ),
                "superseded_by_rebilling": superseded,
            }
        )
        facts[-1] = replace(facts[-1], cycle=cycles[-1])

    return {
        "plant_id": str(plant_id),
        "limit": limit,
        "cycles_returned": len(cycles),
        "cycles": cycles,
        "savings_window": _savings_window(
            facts, commissioning_known=commissioned_month is not None
        ),
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
