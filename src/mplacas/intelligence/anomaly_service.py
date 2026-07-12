from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

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


class AnomalyDataNotFoundError(LookupError):
    """There is not enough persisted data to build an anomaly analysis."""


@dataclass(frozen=True, slots=True)
class DailyPersistedAnomaly:
    observation_date: date
    actual_production_kwh: Decimal
    expected_production_kwh: Decimal
    irradiation_kwh_m2: Decimal | None
    assessment: DailyAnomalyAssessment


@dataclass(frozen=True, slots=True)
class PersistedAnomalySummary:
    plant_id: uuid.UUID
    start_date: date
    end_date: date
    days_analyzed: int
    current_streak_days: int
    worst_level: AnomalyLevel
    daily: tuple[DailyPersistedAnomaly, ...]


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
    expected_daily_production_kwh: Decimal,
    days: int = 7,
    end_date: date | None = None,
) -> PersistedAnomalySummary:
    if expected_daily_production_kwh <= 0:
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

    climate_rows = list(
        (
            await session.execute(
                select(DailyClimateObservationRecord).where(
                    DailyClimateObservationRecord.plant_id == plant_id,
                    DailyClimateObservationRecord.observation_date >= first_day,
                    DailyClimateObservationRecord.observation_date <= last_day,
                )
            )
        ).scalars()
    )

    energy_by_day: dict[date, list[DailyEnergy]] = {}
    for row in energy_rows:
        energy_by_day.setdefault(row.production_date, []).append(row)
    climate_by_day = {row.observation_date: row for row in climate_rows}

    daily: list[DailyPersistedAnomaly] = []
    for current_day in sorted(energy_by_day):
        rows = energy_by_day[current_day]
        actual = sum((row.energy_kwh for row in rows), Decimal("0"))
        complete = all(row.status is DataStatus.CONSOLIDATED for row in rows)
        climate = climate_by_day.get(current_day)
        irradiation = climate.irradiation_kwh_m2 if climate is not None else None
        assessment = assess_daily_performance(
            DailyPerformanceInput(
                actual_production_kwh=actual,
                expected_production_kwh=expected_daily_production_kwh,
                irradiation_kwh_m2=irradiation,
                data_complete=complete,
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

    worst = max((item.assessment.level for item in daily), key=_severity)
    streak = 0
    for item in reversed(daily):
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
    )
