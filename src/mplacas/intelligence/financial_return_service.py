"""ROI / payback projection for a plant's registered investment (ADR-067).

Strictly read-only: sums ``estimated_savings_brl`` across the plant's
existing ``monthly_report_snapshots`` (ADR-038, immutable, versioned) and
never recomputes savings from ``utility_bills`` — the whole point of the
snapshot-backed design is that the number never changes retroactively when
the calculation engine evolves (see ADR-067, "Decisão", item 5).

This module does not materialize any snapshot. Faturas confirmadas antes de
`estimated_savings_brl` existir no relatório mensal permanecem, para sempre,
fora da cobertura (`cycles_counted` menor que `cycles_expected`) — e é isso
que a cobertura explícita torna visível ao usuário, em vez de esconder.
"""

from __future__ import annotations

import enum
import math
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.core.authorization import PlantScope, UNRESTRICTED_PLANT_SCOPE
from mplacas.db.models import Plant
from mplacas.reports.snapshot import MonthlyReportSnapshotRepository

_SAVINGS_METRIC_KEY = "estimated_savings_brl"
_MINIMUM_CYCLES_FOR_PAYBACK = 6


class FinancialReturnUnavailableReason(str, enum.Enum):
    """Shared enum for both ``unavailable_reason`` and
    ``payback_unavailable_reason`` (ADR-067, Decisão item 5).

    Kept as a single enum, deliberately used across two separate response
    fields: with one field alone, a plant with valid ROI but too little
    history to project a payback would have its ROI hidden along with the
    payback — exactly the ambiguity the ADR calls out as unacceptable.
    """

    INVESTMENT_NOT_REGISTERED = "INVESTMENT_NOT_REGISTERED"
    NO_CONSOLIDATED_SAVINGS = "NO_CONSOLIDATED_SAVINGS"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


class FinancialReturnPlantNotFoundError(LookupError):
    """The plant does not exist within the caller's scope."""


@dataclass(frozen=True, slots=True)
class FinancialReturnResult:
    plant_id: uuid.UUID
    investment_amount_brl: Decimal | None
    investment_recorded_on: date | None
    commissioned_on: date | None
    accumulated_savings_brl: Decimal | None
    average_monthly_savings_brl: Decimal | None
    cycles_counted: int | None
    cycles_expected: int | None
    roi_percent: Decimal | None
    payback_projection_months: int | None
    unavailable_reason: FinancialReturnUnavailableReason | None
    payback_unavailable_reason: FinancialReturnUnavailableReason | None


def _months_between_inclusive(start: date, end_reference_month: str) -> int:
    """Months from ``start`` to ``end_reference_month`` ("YYYY-MM"), both ends
    included — matching the definition in ADR-067, Decisão item 5."""
    end_year, end_month = (int(part) for part in end_reference_month.split("-"))
    return (end_year - start.year) * 12 + (end_month - start.month) + 1


def _accumulate_savings(
    snapshots: tuple,
) -> tuple[Decimal, int, str | None]:
    """Sum ``estimated_savings_brl`` across ``snapshots``.

    Snapshots without the metric (materialized before it was projected) or
    with an empty value are skipped entirely — they neither sum nor count,
    by design (ADR-067). Returns the accumulated total, the count of
    snapshots that contributed, and the reference month of the most recent
    snapshot overall (regardless of whether it contributed), used as the
    upper bound for ``cycles_expected``.
    """
    accumulated = Decimal("0")
    counted = 0
    latest_reference_month: str | None = None
    for snapshot in snapshots:
        report = snapshot.report
        if (
            latest_reference_month is None
            or report.reference_month > latest_reference_month
        ):
            latest_reference_month = report.reference_month
        metric = next(
            (item for item in report.metrics if item.key == _SAVINGS_METRIC_KEY),
            None,
        )
        if metric is None or metric.value == "":
            continue
        accumulated += Decimal(metric.value)
        counted += 1
    return accumulated, counted, latest_reference_month


async def get_latest_financial_return(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
) -> FinancialReturnResult:
    """Compute the ROI/payback indicator for ``plant_id`` (ADR-067).

    Strictly a read: never writes to the database, never materializes a
    snapshot. Raises :class:`FinancialReturnPlantNotFoundError` when the
    plant does not exist within ``plant_scope`` — routers map this to 404,
    the same convention used by every other plant-scoped endpoint.
    """
    if not plant_scope.allows(plant_id):
        raise FinancialReturnPlantNotFoundError("plant not found")
    plant = await session.get(Plant, plant_id)
    if plant is None:
        raise FinancialReturnPlantNotFoundError("plant not found")

    investment_amount_brl = plant.investment_amount_brl
    investment_recorded_on = plant.investment_recorded_on
    commissioned_on = plant.commissioned_on

    if investment_amount_brl is None:
        # ADR-067, item 5: sem CAPEX registrado não há base para nenhum
        # cálculo derivado, incluindo cobertura — todos vêm `null`, não `0`.
        return FinancialReturnResult(
            plant_id=plant_id,
            investment_amount_brl=None,
            investment_recorded_on=investment_recorded_on,
            commissioned_on=commissioned_on,
            accumulated_savings_brl=None,
            average_monthly_savings_brl=None,
            cycles_counted=None,
            cycles_expected=None,
            roi_percent=None,
            payback_projection_months=None,
            unavailable_reason=FinancialReturnUnavailableReason.INVESTMENT_NOT_REGISTERED,
            payback_unavailable_reason=None,
        )

    snapshots = await MonthlyReportSnapshotRepository(
        session, plant_scope=plant_scope
    ).list_for_plant(plant_id=plant_id)
    accumulated_savings_brl, cycles_counted, latest_reference_month = _accumulate_savings(
        snapshots
    )

    cycles_expected = (
        _months_between_inclusive(commissioned_on, latest_reference_month)
        if commissioned_on is not None and latest_reference_month is not None
        else None
    )

    if cycles_counted == 0:
        return FinancialReturnResult(
            plant_id=plant_id,
            investment_amount_brl=investment_amount_brl,
            investment_recorded_on=investment_recorded_on,
            commissioned_on=commissioned_on,
            accumulated_savings_brl=None,
            average_monthly_savings_brl=None,
            cycles_counted=0,
            cycles_expected=cycles_expected,
            roi_percent=None,
            payback_projection_months=None,
            unavailable_reason=FinancialReturnUnavailableReason.NO_CONSOLIDATED_SAVINGS,
            payback_unavailable_reason=None,
        )

    average_monthly_savings_brl = (accumulated_savings_brl / cycles_counted).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    roi_percent = (accumulated_savings_brl / investment_amount_brl * 100).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )

    payback_unavailable_reason: FinancialReturnUnavailableReason | None = None
    payback_projection_months: int | None = None
    if cycles_counted < _MINIMUM_CYCLES_FOR_PAYBACK or average_monthly_savings_brl <= 0:
        payback_unavailable_reason = FinancialReturnUnavailableReason.INSUFFICIENT_HISTORY
    elif accumulated_savings_brl >= investment_amount_brl:
        # Economia acumulada já cobre o investimento: payback já ocorreu
        # (ADR-067, Decisão item 5).
        payback_projection_months = cycles_counted
    else:
        remaining = investment_amount_brl - accumulated_savings_brl
        extra_cycles = math.ceil(remaining / average_monthly_savings_brl)
        payback_projection_months = cycles_counted + extra_cycles

    return FinancialReturnResult(
        plant_id=plant_id,
        investment_amount_brl=investment_amount_brl,
        investment_recorded_on=investment_recorded_on,
        commissioned_on=commissioned_on,
        accumulated_savings_brl=accumulated_savings_brl,
        average_monthly_savings_brl=average_monthly_savings_brl,
        cycles_counted=cycles_counted,
        cycles_expected=cycles_expected,
        roi_percent=roi_percent,
        payback_projection_months=payback_projection_months,
        unavailable_reason=None,
        payback_unavailable_reason=payback_unavailable_reason,
    )
