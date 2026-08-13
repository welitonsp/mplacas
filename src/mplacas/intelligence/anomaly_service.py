from __future__ import annotations

import uuid
from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.db.models import DailyEnergy, DataStatus, Device
from mplacas.intelligence.anomaly_engine import (
    AnomalyLevel,
    DailyAnomalyAssessment,
    DailyPerformanceInput,
    assess_daily_performance,
)


#: How many days *before* the analyzed window are additionally pulled to
#: seed the local irradiation median. The analyzed window itself (`days`,
#: typically 7 — see `mplacas.alerts.operations`) is almost always shorter
#: than `DEFAULT_MINIMUM_IRRADIATION_SAMPLE_DAYS` would need for any day
#: near its start, which would leave the relative-median threshold unable
#: to ever excuse a drop as weather in practice. Matches
#: `mplacas.alerts.production_alert.LOOKBACK_DAYS`.
IRRADIATION_MEDIAN_LOOKBACK_DAYS = 30

#: Severity threshold for flagging a day's yield (production/irradiation) as
#: atypical relative to the analyzed window's own aggregate yield. Moved
#: unchanged from `frontend/src/lib/dashboard/yield.ts::
#: YIELD_ATYPICAL_THRESHOLD_PERCENT` (2026-08-13, plan T7): this is a
#: severity policy calibrated on two real production incidents at this plant
#: (-33% and +27% deviation), not presentation — it belongs in the domain
#: layer with the calculation it gates, same reasoning as
#: `mplacas.devices.metrics.DEVICE_NORMAL_THRESHOLD`.
YIELD_ATYPICAL_THRESHOLD_PERCENT = Decimal("20")


class AnomalyDataNotFoundError(LookupError):
    """There is not enough persisted data to build an anomaly analysis."""


@dataclass(frozen=True, slots=True)
class DailyPersistedAnomaly:
    observation_date: date
    actual_production_kwh: Decimal
    expected_production_kwh: Decimal | None
    irradiation_kwh_m2: Decimal | None
    assessment: DailyAnomalyAssessment | None
    #: production_kwh / irradiation_kwh_m2 for this day. `None` only when
    #: there is no positive irradiation reading for the day (no denominator,
    #: no ratio possible). **Not** `None` for a day with zero production
    #: under a positive irradiation reading: `0 / irradiation` is a
    #: perfectly defined ratio, and it is the single worst yield event
    #: possible (full outage under sun) — fabricating an absence here would
    #: hide exactly the day an operator most needs to see (plan T7b P1, "dia
    #: de produção zero com sol desaparece"). That zero-production day is
    #: still excluded from `period_yield_kwh_per_kwh_m2`'s own aggregate
    #: (see `_compute_period_yield`) so it never drags down the very
    #: reference it would be judged against — its own ratio is defined, the
    #: aggregate it is compared to is not contaminated by it.
    yield_kwh_per_kwh_m2: Decimal | None = None
    #: `((yield_kwh_per_kwh_m2 / period_yield) - 1) * 100` — this day's yield
    #: re-expressed as a percent deviation from the analyzed window's own
    #: aggregate yield. `None` whenever either side of that ratio is
    #: unavailable — never invented. Moved from
    #: `frontend/src/lib/dashboard/yield.ts::computeYieldStats` (2026-08-13,
    #: plan T7): subtracting the constant `1` before rescaling to percent is
    #: domain math, not a unit conversion (same reasoning as
    #: `mplacas.devices.metrics.DeviceYieldAssessment.
    #: relative_to_own_median_deviation_percent`).
    yield_deviation_from_period_percent: Decimal | None = None


@dataclass(frozen=True, slots=True)
class PersistedAnomalySummary:
    plant_id: uuid.UUID
    start_date: date
    end_date: date
    days_analyzed: int
    current_streak_days: int
    worst_level: AnomalyLevel | None
    daily: tuple[DailyPersistedAnomaly, ...]
    expected_unavailable_reason: str | None = None
    #: Aggregate yield of the analyzed window: total production over total
    #: irradiation across the days that have both (see
    #: `_compute_period_yield`). `None` when no day in the window has both a
    #: positive production and a positive irradiation reading.
    period_yield_kwh_per_kwh_m2: Decimal | None = None
    #: Fixed policy threshold, always present regardless of data
    #: availability — same reasoning as `mplacas.devices.read_service.
    #: DailyStatusResult.device_normal_threshold` (ADR-074, Decision 3): the
    #: frontend renders it, it never hardcodes it.
    yield_atypical_threshold_percent: Decimal = YIELD_ATYPICAL_THRESHOLD_PERCENT
    #: How many of the `daily` days actually fed `period_yield_kwh_per_kwh_m2`
    #: (both production and irradiation positive) — deliberately **not**
    #: `days_analyzed` (`len(daily)`, every day with a persisted production
    #: row, regardless of whether it has irradiation at all). The two diverge
    #: whenever any day is missing a climate reading or reported zero
    #: production (plan T7b P1: `tests/test_anomaly_service.py` already had
    #: `days_analyzed == 4` against a yield computed over 2 days before this
    #: field existed — the frontend was labeling the aggregate with the wrong
    #: count). The frontend must label `period_yield_kwh_per_kwh_m2` with
    #: this field, never with `days_analyzed`.
    period_yield_sample_days: int = 0


def _severity(level: AnomalyLevel) -> int:
    return {
        AnomalyLevel.NORMAL: 0,
        AnomalyLevel.ATTENTION: 1,
        AnomalyLevel.ANOMALY: 2,
        AnomalyLevel.CRITICAL: 3,
    }[level]


def _compute_period_yield(
    energy_by_day: dict[date, list[DailyEnergy]],
    climate_by_day: dict[date, DailyClimateObservationRecord],
) -> tuple[Decimal | None, dict[date, Decimal], int]:
    """Aggregate production/irradiation ratio for the analyzed window itself.

    Originally moved from `frontend/src/lib/dashboard/yield.ts::
    computeYieldStats` (2026-08-13, plan T7) — the file's own comment
    admitted this used to be "calculado 100% no frontend". Revised for plan
    T7b (P1, "dia de produção zero com sol desaparece"): a zero-production
    day under a positive irradiation reading now gets a defined ratio of
    `0` in the returned per-day map, instead of being dropped as if no
    ratio were computable — `0 / irradiation` is exactly as defined as any
    other division here, and it is the worst yield event a day can have.
    It is still excluded from the **aggregate** (`total_actual`/
    `total_irradiation`) below, for the same reason `computeYieldStats`
    excluded it originally: a confirmed-outage day would otherwise drag
    down the very reference it is meant to be judged against.

    Deliberately **not** the same metric as either existing rendimento
    calculation in the backend, so it is not a duplicate of either:

    - `mplacas.devices.metrics._device_rendimento_medians` /
      `mplacas.alerts.production_alert._plant_rendimento_median`: the
      **median** of individual daily ratios over a fixed 30-day lookback
      *before* a single target day — a historical baseline used to judge
      that one day.
    - This function: the **irradiation-weighted mean** ratio (total
      production over total irradiation, not a median of per-day ratios)
      across exactly the days the caller already requested (`daily`, up to
      90 days) — used only to flag which of those *same* displayed days
      look atypical relative to each other, not to judge a single day
      against history.

    Returns `(period_yield, day_yields, sample_days)`: the aggregate (or
    `None` when no day qualifies for it), the per-day ratio map (a superset
    of the days counted in the aggregate — see above), and how many days
    fed the aggregate (`PersistedAnomalySummary.period_yield_sample_days`).
    """
    total_actual = Decimal("0")
    total_irradiation = Decimal("0")
    day_yields: dict[date, Decimal] = {}
    sample_days = 0
    for current_day, rows in energy_by_day.items():
        actual = sum((row.energy_kwh for row in rows), Decimal("0"))
        climate = climate_by_day.get(current_day)
        irradiation = climate.irradiation_kwh_m2 if climate is not None else None
        if irradiation is None or irradiation <= 0:
            # No denominator at all — genuinely no ratio possible, unlike
            # zero production (handled below), which still has one.
            continue
        if actual < 0:
            # Defensive: negative production is a data error, not a real
            # ratio to expose (should not occur in practice).
            continue
        day_yields[current_day] = actual / irradiation
        if actual > 0:
            total_actual += actual
            total_irradiation += irradiation
            sample_days += 1

    if total_irradiation <= 0:
        return None, day_yields, 0
    return total_actual / total_irradiation, day_yields, sample_days


def _yield_deviation_from_period_percent(
    day_yield: Decimal | None, period_yield: Decimal | None
) -> Decimal | None:
    """`((day_yield / period_yield) - 1) * 100`, `None` unless both sides are known."""
    if day_yield is None or period_yield is None or period_yield <= 0:
        return None
    return (day_yield - period_yield) / period_yield * Decimal("100")


async def analyze_recent_persisted_anomalies(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    expected_daily_production_kwh: Decimal | None,
    days: int = 7,
    end_date: date | None = None,
    expected_unavailable_reason: str | None = None,
) -> PersistedAnomalySummary:
    if expected_daily_production_kwh is not None and expected_daily_production_kwh <= 0:
        raise ValueError("expected daily production must be greater than zero")
    if not 1 <= days <= 90:
        raise ValueError("days must be between 1 and 90")

    last_day = end_date or date.today()
    first_day = last_day - timedelta(days=days - 1)

    energy_rows = list(
        (
            await session.execute(
                select(DailyEnergy)
                .join(Device)
                .where(
                    Device.plant_id == plant_id,
                    DailyEnergy.production_date >= first_day,
                    DailyEnergy.production_date <= last_day,
                )
            )
        ).scalars()
    )
    if not energy_rows:
        raise AnomalyDataNotFoundError("daily production not found for requested period")

    # The climate query reaches back further than `first_day` purely to seed
    # the irradiation median (see `IRRADIATION_MEDIAN_LOOKBACK_DAYS`) — the
    # analyzed window itself (`energy_by_day`) is unaffected.
    median_history_start = first_day - timedelta(days=IRRADIATION_MEDIAN_LOOKBACK_DAYS)
    climate_rows = list(
        (
            await session.execute(
                select(DailyClimateObservationRecord).where(
                    DailyClimateObservationRecord.plant_id == plant_id,
                    DailyClimateObservationRecord.observation_date >= median_history_start,
                    DailyClimateObservationRecord.observation_date <= last_day,
                )
            )
        ).scalars()
    )

    energy_by_day: dict[date, list[DailyEnergy]] = {}
    for row in energy_rows:
        energy_by_day.setdefault(row.production_date, []).append(row)
    climate_by_day = {row.observation_date: row for row in climate_rows}

    # Sorted (date, irradiation) pairs feed the local median for each day
    # below without a second per-day query — this single climate query
    # (widened above) already covers everything needed, so the median is
    # always computed from days strictly before the one being assessed.
    irradiation_by_day = sorted(
        (observation_date, record.irradiation_kwh_m2)
        for observation_date, record in climate_by_day.items()
        if record.irradiation_kwh_m2 is not None
    )
    irradiation_dates = [observation_date for observation_date, _ in irradiation_by_day]
    irradiation_values = [value for _, value in irradiation_by_day]

    period_yield, day_yields, period_yield_sample_days = _compute_period_yield(
        energy_by_day, climate_by_day
    )

    daily: list[DailyPersistedAnomaly] = []
    for current_day in sorted(energy_by_day):
        rows = energy_by_day[current_day]
        actual = sum((row.energy_kwh for row in rows), Decimal("0"))
        complete = all(row.status is DataStatus.CONSOLIDATED for row in rows)
        climate = climate_by_day.get(current_day)
        irradiation = climate.irradiation_kwh_m2 if climate is not None else None

        historical_count = bisect_left(irradiation_dates, current_day)
        historical_values = irradiation_values[:historical_count]
        irradiation_median = median(historical_values) if historical_values else None

        day_yield = day_yields.get(current_day)
        yield_deviation_percent = _yield_deviation_from_period_percent(day_yield, period_yield)

        if expected_daily_production_kwh is None:
            daily.append(
                DailyPersistedAnomaly(
                    observation_date=current_day,
                    actual_production_kwh=actual,
                    expected_production_kwh=None,
                    irradiation_kwh_m2=irradiation,
                    assessment=None,
                    yield_kwh_per_kwh_m2=day_yield,
                    yield_deviation_from_period_percent=yield_deviation_percent,
                )
            )
            continue

        assessment = assess_daily_performance(
            DailyPerformanceInput(
                actual_production_kwh=actual,
                expected_production_kwh=expected_daily_production_kwh,
                irradiation_kwh_m2=irradiation,
                data_complete=complete,
                irradiation_median_kwh_m2=irradiation_median,
                irradiation_sample_days=len(historical_values),
            )
        )
        daily.append(
            DailyPersistedAnomaly(
                observation_date=current_day,
                actual_production_kwh=actual,
                expected_production_kwh=expected_daily_production_kwh,
                irradiation_kwh_m2=irradiation,
                assessment=assessment,
                yield_kwh_per_kwh_m2=day_yield,
                yield_deviation_from_period_percent=yield_deviation_percent,
            )
        )

    assessed_levels = [item.assessment.level for item in daily if item.assessment is not None]
    worst = max(assessed_levels, key=_severity) if assessed_levels else None
    streak = 0
    for item in reversed(daily):
        if item.assessment is None:
            break
        if item.assessment.level in {AnomalyLevel.ANOMALY, AnomalyLevel.CRITICAL}:
            streak += 1
        else:
            break

    return PersistedAnomalySummary(
        plant_id=plant_id,
        start_date=first_day,
        end_date=last_day,
        days_analyzed=len(daily),
        current_streak_days=streak,
        worst_level=worst,
        daily=tuple(daily),
        expected_unavailable_reason=expected_unavailable_reason,
        period_yield_kwh_per_kwh_m2=period_yield,
        yield_atypical_threshold_percent=YIELD_ATYPICAL_THRESHOLD_PERCENT,
        period_yield_sample_days=period_yield_sample_days,
    )
