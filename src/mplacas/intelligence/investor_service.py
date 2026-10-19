"""Painel do investidor: junta dados da usina, snapshots e indicadores (ADR-079).

Leitura (a única escrita possível é o reabastecimento de taxas públicas de
CDI/IPCA em ``market_index_monthly``). Toda a matemática fica em
``investor_metrics``; aqui só se reúne e se decide o que está disponível.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.billing.read_repository import ConfirmedBillReadRepository
from mplacas.core.authorization import UNRESTRICTED_PLANT_SCOPE, PlantScope
from mplacas.db.models import Plant
from mplacas.intelligence.investor_metrics import (
    InvestorPremises,
    Projection,
    RealizedComparison,
    add_months,
    annualize,
    project,
    realized_comparison,
)
from mplacas.market.bcb import BcbSgsClient
from mplacas.market.service import last_closed_month, monthly_rates
from mplacas.reports.snapshot import MonthlyReportSnapshotRepository

_SAVINGS_METRIC_KEY = "estimated_savings_brl"
# Abaixo disto a média mensal ainda não cobre as estações do ano.
MINIMUM_CYCLES_FOR_CONFIDENT_BASELINE = 12
# Fórmula da economia corrigida (injeção pelo medidor, ADR-078).
CORRECTED_CALCULATION_VERSION = (0, 3, 0)


class InvestorUnavailableReason(str, enum.Enum):
    INVESTMENT_NOT_REGISTERED = "INVESTMENT_NOT_REGISTERED"
    COMMISSIONING_DATE_MISSING = "COMMISSIONING_DATE_MISSING"
    NO_CONSOLIDATED_SAVINGS = "NO_CONSOLIDATED_SAVINGS"
    MARKET_DATA_UNAVAILABLE = "MARKET_DATA_UNAVAILABLE"


class InvestorPlantNotFoundError(LookupError):
    """A usina não existe no escopo de quem chamou."""


@dataclass(frozen=True, slots=True)
class InvestorPanel:
    plant_id: uuid.UUID
    unavailable_reason: InvestorUnavailableReason | None
    investment_brl: Decimal | None
    commissioned_month: str | None
    months_since_commissioning: int | None
    cycles_counted: int
    calculation_versions: tuple[str, ...]
    includes_pre_correction_cycles: bool
    low_confidence_baseline: bool
    cdi_12m_per_year: Decimal | None
    ipca_12m_per_year: Decimal | None
    indices_as_of_month: str | None
    realized: RealizedComparison | None
    projection: Projection | None
    premises: InvestorPremises | None


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in version.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


async def get_investor_panel(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    today: date,
    bcb_client: BcbSgsClient | None,
    plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
) -> InvestorPanel:
    if not plant_scope.allows(plant_id):
        raise InvestorPlantNotFoundError("plant not found")
    plant = await session.get(Plant, plant_id)
    if plant is None:
        raise InvestorPlantNotFoundError("plant not found")

    snapshots = await MonthlyReportSnapshotRepository(
        session, plant_scope=plant_scope
    ).list_for_plant(plant_id=plant_id)
    savings: dict[str, Decimal] = {}
    versions: set[str] = set()
    for snapshot in snapshots:
        report = snapshot.report
        metric = next((m for m in report.metrics if m.key == _SAVINGS_METRIC_KEY), None)
        if metric is None or metric.value == "":
            continue
        savings[report.reference_month] = Decimal(metric.value)
        versions.add(report.calculation_version)
    sorted_versions = tuple(sorted(versions, key=_version_tuple))
    pre_correction = any(_version_tuple(v) < CORRECTED_CALCULATION_VERSION for v in sorted_versions)

    investment = plant.investment_amount_brl
    commissioned_on = plant.commissioned_on
    commissioned_month = commissioned_on.strftime("%Y-%m") if commissioned_on else None

    def unavailable(reason: InvestorUnavailableReason, **extra: object) -> InvestorPanel:
        base: dict[str, object] = dict(
            plant_id=plant_id,
            unavailable_reason=reason,
            investment_brl=investment,
            commissioned_month=commissioned_month,
            months_since_commissioning=None,
            cycles_counted=len(savings),
            calculation_versions=sorted_versions,
            includes_pre_correction_cycles=pre_correction,
            low_confidence_baseline=len(savings) < MINIMUM_CYCLES_FOR_CONFIDENT_BASELINE,
            cdi_12m_per_year=None,
            ipca_12m_per_year=None,
            indices_as_of_month=None,
            realized=None,
            projection=None,
            premises=None,
        )
        base.update(extra)
        return InvestorPanel(**base)  # type: ignore[arg-type]

    if investment is None:
        return unavailable(InvestorUnavailableReason.INVESTMENT_NOT_REGISTERED)
    if commissioned_on is None or commissioned_month is None:
        return unavailable(InvestorUnavailableReason.COMMISSIONING_DATE_MISSING)
    if not savings:
        return unavailable(InvestorUnavailableReason.NO_CONSOLIDATED_SAVINGS)

    closed = last_closed_month(today)
    # CDI desde a ligação (para o realizado) e pelo menos 12 meses (premissa).
    cdi_start = min(add_months(commissioned_month, 1), add_months(closed, -11))
    cdi = await monthly_rates(
        session, "CDI", start_month=cdi_start, end_month=closed, client=bcb_client, today=today
    )
    ipca = await monthly_rates(
        session,
        "IPCA",
        start_month=add_months(closed, -14),
        end_month=closed,
        client=bcb_client,
        today=today,
    )
    cdi_months = sorted(cdi)
    ipca_months = sorted(ipca)
    if len(cdi_months) < 12 or len(ipca_months) < 12:
        return unavailable(InvestorUnavailableReason.MARKET_DATA_UNAVAILABLE)

    cdi_12m = annualize([cdi[m] for m in cdi_months[-12:]])
    ipca_12m = annualize([ipca[m] for m in ipca_months[-12:]])
    as_of = cdi_months[-1]

    premises = InvestorPremises(
        cdi_per_year=cdi_12m.quantize(Decimal("0.0001")),
        ipca_per_year=ipca_12m.quantize(Decimal("0.0001")),
        tariff_growth_per_year=ipca_12m.quantize(Decimal("0.0001")),
    )

    latest_bill = await ConfirmedBillReadRepository(session, plant_scope=plant_scope).latest(
        plant_id=plant_id
    )
    compensated = latest_bill.bill.compensated_kwh if latest_bill else None
    wire_b = latest_bill.bill.wire_b_tariff_brl_kwh if latest_bill else None
    wire_b_year = int(latest_bill.bill.reference_month[:4]) if latest_bill else None

    realized = realized_comparison(
        investment_brl=investment,
        start_month=commissioned_month,
        savings_by_month=savings,
        cdi_by_month=cdi,
        as_of_month=as_of,
    )
    projection = project(
        investment_brl=investment,
        start_month=commissioned_month,
        commissioned_on=commissioned_on,
        savings_by_month=savings,
        compensated_kwh_per_month=compensated,
        wire_b_tariff_brl_kwh=wire_b,
        wire_b_reference_year=wire_b_year,
        premises=premises,
    )
    year, month = (int(part) for part in commissioned_month.split("-"))
    months_since = (today.year - year) * 12 + (today.month - month)
    return InvestorPanel(
        plant_id=plant_id,
        unavailable_reason=None,
        investment_brl=investment,
        commissioned_month=commissioned_month,
        months_since_commissioning=max(0, months_since),
        cycles_counted=len(savings),
        calculation_versions=sorted_versions,
        includes_pre_correction_cycles=pre_correction,
        low_confidence_baseline=len(savings) < MINIMUM_CYCLES_FOR_CONFIDENT_BASELINE,
        cdi_12m_per_year=premises.cdi_per_year,
        ipca_12m_per_year=premises.ipca_per_year,
        indices_as_of_month=as_of,
        realized=realized,
        projection=projection,
        premises=premises,
    )
