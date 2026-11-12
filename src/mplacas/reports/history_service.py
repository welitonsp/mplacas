"""Serializes a bounded window of closed billing cycles for dashboard charts.

Reads exclusively from :class:`MonthlyReportSnapshotRepository` — never
recomputes or materializes anything (ADR-038). There is no "current cycle"
here: only cycles with a confirmed bill and a persisted snapshot are
represented.
"""

from __future__ import annotations

import logging
import uuid
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
    return None if value is None else str(value)


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


def _savings_window(
    cycles: list[dict[str, object]], *, commissioning_excluded: list[bool]
) -> dict[str, object]:
    """Totais da janela, em ``Decimal``, só com o que já está nos ciclos.

    Regras de contagem (``contributing`` = ciclo com economia que entrou na soma):

    - ``cycles_in_window``: todos os ciclos devolvidos.
    - ``cycles_with_savings``: só os que contribuem. O mês de ligação com valor
      NÃO conta aqui (fica de fora da soma por regra, ADR-079).
    - ``cycles_without_savings``: ciclos com economia nula (indisponível ou
      snapshot anterior à métrica), inclusive no mês de ligação.
    - Logo: in_window = with + without + (1 se o mês de ligação com valor foi excluído).
    - ``commissioning_month_excluded``: há ciclo no mês de ligação COM valor que
      ficou fora da soma.
    - Contadores de tarifa/defasagem olham só os ciclos que contribuem.
    - Fatura: ``total_bill_amount_brl`` soma todos os ciclos cuja fatura ainda
      está entre as confirmadas (inclui o mês de ligação: é valor pago, não
      estimativa); cobertura própria em ``cycles_with_bill_amount``.
    - Dois ciclos no mesmo mês (refaturamento) são dois ciclos e somam ambos.
    """
    contributing: list[dict[str, object]] = []
    without = 0
    for cycle, excluded in zip(cycles, commissioning_excluded, strict=True):
        if cycle["estimated_savings_brl"] is None:
            without += 1
        elif not excluded:
            contributing.append(cycle)
    total: Decimal | None = None
    if contributing:
        total = sum((Decimal(str(c["estimated_savings_brl"])) for c in contributing), Decimal("0"))
    bill_amounts = [
        Decimal(str(c["bill_total_amount_brl"]))
        for c in cycles
        if c["bill_total_amount_brl"] is not None
    ]
    months = [str(c["reference_month"]) for c in contributing]
    return {
        "total_estimated_savings_brl": _money(total),
        "cycles_in_window": len(cycles),
        "cycles_with_savings": len(contributing),
        "cycles_without_savings": without,
        "commissioning_month_excluded": any(commissioning_excluded),
        "first_reference_month": min(months) if months else None,
        "last_reference_month": max(months) if months else None,
        "cycles_with_bill_tariff": sum(
            1 for c in contributing if c["savings_tariff_source"] == SAVINGS_TARIFF_BILL
        ),
        "cycles_with_outdated_or_partial": sum(
            1
            for c in contributing
            if c["savings_gap_cause"]
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

    cycles: list[dict[str, object]] = []
    commissioning_excluded: list[bool] = []
    export_shares: list[Decimal] = []
    for snapshot in snapshots:
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
        commissioning_excluded.append(bool(is_commissioning) and savings_value is not None)
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
            }
        )

    return {
        "plant_id": str(plant_id),
        "limit": limit,
        "cycles_returned": len(cycles),
        "cycles": cycles,
        "savings_window": _savings_window(cycles, commissioning_excluded=commissioning_excluded),
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
