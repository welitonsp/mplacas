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


class AnomalyDataNotFoundError(LookupError):
    """There is not enough persisted data to build an anomaly analysis."""


@dataclass(frozen=True, slots=True)
class DailyPersistedAnomaly:
    observation_date: date
    actual_production_kwh: Decimal
    expected_production_kwh: Decimal | None
    irradiation_kwh_m2: Decimal | None
    assessment: DailyAnomalyAssessment | None


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


def _severity(level: AnomalyLevel) -> int:
    return {
        AnomalyLevel.NORMAL: 0,
        AnomalyLevel.ATTENTION: 1,
        AnomalyLevel.ANOMALY: 2,
        AnomalyLevel.CRITICAL: 3,
    }[level]


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

        if expected_daily_production_kwh is None:
            daily.append(
                DailyPersistedAnomaly(
                    observation_date=current_day,
                    actual_production_kwh=actual,
                    expected_production_kwh=None,
                    irradiation_kwh_m2=irradiation,
                    assessment=None,
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
    )
