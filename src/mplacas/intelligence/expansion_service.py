"""Leitura do "Vale a pena ampliar a usina?" (ADR-089).

Só lê o que já está gravado — snapshots dos ciclos, faturas confirmadas e o
cadastro da usina (ADR-038) — e entrega ao motor puro
(:mod:`mplacas.intelligence.expansion`). A conferência da distribuidora de cada
ciclo vem do mesmo histórico da tela de produção, para os dois nunca
divergirem.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.billing.read_repository import ConfirmedBillReadRepository
from mplacas.core.authorization import UNRESTRICTED_PLANT_SCOPE, PlantScope
from mplacas.db.models import Device, Plant
from mplacas.intelligence.expansion import (
    ExpansionAssessment,
    ExpansionCycle,
    MoneyInputs,
    assess_expansion,
)
from mplacas.intelligence.investor_service import calculation_version_tuple
from mplacas.reports.history_service import (
    MAX_HISTORY_CYCLES,
    load_monthly_production_history,
)
from mplacas.reports.contract import MonthlyEnergyReport
from mplacas.reports.snapshot import MonthlyReportSnapshotRepository

# Usina ligada a partir daqui, com Fio B na fatura, está na regra simples do
# art. 27 (60/75/90%). Quem protocolou entre 07/01 e 07/07/2023 tem outra
# transição e pode ter ligado ao longo de 2023: aí o Fio B pleno não pode ser
# deduzido da fatura e o valor em reais fica indisponível.
ART_27_REGIME_FROM = date(2024, 1, 1)
_WELL_BELOW_CODE = "PRODUCTION_WELL_BELOW_EXPECTED"
# Tarifa cheia com bandeira e créditos externos separados (ADR-085): ciclo
# anterior a isso não serve de preço para a energia nova.
MONEY_CALCULATION_VERSION = (0, 5, 0)


class ExpansionPlantNotFoundError(LookupError):
    pass


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def _metric(report: MonthlyEnergyReport, key: str) -> str | None:
    for metric in report.metrics:
        if metric.key == key:
            return metric.value if metric.value != "" else None
    return None


async def get_expansion_assessment(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    today: date,
    plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
) -> tuple[ExpansionAssessment, tuple[str, ...]]:
    """Avaliação e avisos de contexto (cadastro da usina)."""
    if not plant_scope.allows(plant_id):
        raise ExpansionPlantNotFoundError("plant not found")
    plant = await session.get(Plant, plant_id)
    if plant is None:
        raise ExpansionPlantNotFoundError("plant not found")
    devices = (await session.scalars(select(Device).where(Device.plant_id == plant_id))).all()

    history = await load_monthly_production_history(
        session, plant_id=plant_id, plant_scope=plant_scope, limit=MAX_HISTORY_CYCLES
    )
    snapshots = await MonthlyReportSnapshotRepository(
        session, plant_scope=plant_scope
    ).list_recent_for_plant(plant_id=plant_id, limit=MAX_HISTORY_CYCLES)
    reports = {(s.report.reference_month, str(s.report.bill_id)): s.report for s in snapshots}
    bills = {
        str(confirmed.id): confirmed.bill
        for confirmed in await ConfirmedBillReadRepository(
            session, plant_scope=plant_scope
        ).list_for_plant(plant_id=plant_id)
    }

    context: list[str] = []
    commissioned_month = plant.commissioned_on.strftime("%Y-%m") if plant.commissioned_on else None
    if commissioned_month is None:
        context.append("COMMISSIONING_DATE_MISSING")

    raw_cycles = history["cycles"]
    assert isinstance(raw_cycles, list)
    # Um ciclo por mês (o mais recente do refaturamento vence) e só depois do
    # mês da ligação, cuja fatura é de geração parcial.
    by_month: dict[str, dict[str, object]] = {}
    for cycle in raw_cycles:
        month = str(cycle["reference_month"])
        if commissioned_month is None or month > commissioned_month:
            by_month[month] = cycle
    ordered = [by_month[m] for m in sorted(by_month)]

    cycles: list[ExpansionCycle] = []
    for cycle in ordered:
        check = cycle["utility_check"]
        assert isinstance(check, dict)
        quality = cycle.get("quality") or {}
        assert isinstance(quality, dict)
        report = reports.get((str(cycle["reference_month"]), str(cycle["bill_id"])))
        bill = bills.get(str(cycle["bill_id"]))
        start, end = cycle.get("cycle_start"), cycle.get("cycle_end")
        days = (
            (date.fromisoformat(str(end)) - date.fromisoformat(str(start))).days
            if start and end
            else None
        )
        cycles.append(
            ExpansionCycle(
                reference_month=str(cycle["reference_month"]),
                imported_kwh=_decimal(cycle.get("imported_kwh")),
                meter_export_kwh=_decimal(check.get("meter_export_kwh")),
                production_kwh=_decimal(cycle.get("production_kwh")),
                production_estimated=any(
                    (quality.get(key) or 0) > 0
                    for key in (
                        "estimated_production_days",
                        "missing_days",
                        "unavailable_days",
                        "incomplete_days",
                    )
                ),
                cycle_days=days if days and days > 0 else None,
                utility_verdict=str(check.get("verdict")),
                production_well_below_expected=bool(
                    report and any(d.code == _WELL_BELOW_CODE for d in report.diagnostics)
                ),
                generation_share_percent=bill.generation_share_percent if bill else None,
                credit_balance_kwh=bill.credit_balance_kwh if bill else None,
            )
        )

    window_start = len(cycles) - 12
    previous_balance = None
    if window_start >= 0 and cycles:
        first_check = ordered[window_start]["utility_check"]
        assert isinstance(first_check, dict)
        previous_balance = _decimal(first_check.get("previous_balance_kwh"))

    money_inputs = None
    if ordered:
        latest = ordered[-1]
        latest_check = latest["utility_check"]
        assert isinstance(latest_check, dict)
        report = reports.get((str(latest["reference_month"]), str(latest["bill_id"])))
        bill = bills.get(str(latest["bill_id"]))
        version_ok = report is not None and (
            calculation_version_tuple(report.calculation_version) >= MONEY_CALCULATION_VERSION
        )
        tariff_class_presumed = bool(
            report
            and any(m.key == "tariff_class" and m.nature == "ASSUMPTION" for m in report.metrics)
        )
        if tariff_class_presumed:
            context.append("TARIFF_CLASS_PRESUMED")
        money_inputs = MoneyInputs(
            reference_month=str(latest["reference_month"]),
            full_tariff_brl_kwh=(
                _decimal(_metric(report, "savings_tariff_brl_kwh"))
                if report is not None
                and _metric(report, "savings_tariff_source") == "DISTRIBUTOR_FULL_TARIFF"
                and version_ok
                else None
            ),
            wire_b_tariff_brl_kwh=bill.wire_b_tariff_brl_kwh if bill else None,
            model_matches_bill=latest_check.get("credit_unit_value_brl") is not None,
            regime_confirmed=(
                plant.commissioned_on is not None
                and plant.commissioned_on >= ART_27_REGIME_FROM
                and bill is not None
                and bill.wire_b_tariff_brl_kwh is not None
            ),
        )

    single_ac = devices[0].ac_capacity_kw if len(devices) == 1 else None
    if single_ac is None and len(devices) == 1:
        single_ac = plant.ac_capacity_kw
    installed = plant.installed_power_kwp
    if installed is None and devices and all(d.dc_capacity_kwp for d in devices):
        installed = sum((d.dc_capacity_kwp for d in devices if d.dc_capacity_kwp), Decimal("0"))

    assessment = assess_expansion(
        cycles=cycles,
        previous_balance_kwh=previous_balance,
        installed_kwp=installed,
        device_count=len(devices),
        inverter_ac_kw=single_ac,
        money_inputs=money_inputs,
        request_year=today.year,
    )
    return assessment, tuple(context)
