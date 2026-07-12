from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class DailyProductionPoint:
    production_date: date
    energy_kwh: Decimal
    consolidated: bool = True


@dataclass(frozen=True, slots=True)
class CycleProductionSummary:
    cycle_start: date
    cycle_end: date
    production_kwh: Decimal
    expected_days: int
    available_days: int
    missing_dates: tuple[date, ...]
    provisional_dates: tuple[date, ...]

    @property
    def complete(self) -> bool:
        return not self.missing_dates and not self.provisional_dates


def summarize_cycle_production(
    points: list[DailyProductionPoint], *, cycle_start: date, cycle_end: date
) -> CycleProductionSummary:
    """Sum one value per calendar date in the exact inclusive billing cycle."""
    if cycle_end < cycle_start:
        raise ValueError("cycle end cannot precede start")

    by_date: dict[date, DailyProductionPoint] = {}
    for point in points:
        if point.energy_kwh < 0:
            raise ValueError("daily production cannot be negative")
        if not cycle_start <= point.production_date <= cycle_end:
            continue
        if point.production_date in by_date:
            raise ValueError(f"duplicate production date: {point.production_date.isoformat()}")
        by_date[point.production_date] = point

    expected_dates = tuple(
        cycle_start + timedelta(days=offset)
        for offset in range((cycle_end - cycle_start).days + 1)
    )
    missing = tuple(day for day in expected_dates if day not in by_date)
    provisional = tuple(
        day for day in expected_dates if day in by_date and not by_date[day].consolidated
    )
    total = sum((by_date[day].energy_kwh for day in expected_dates if day in by_date), Decimal("0"))
    return CycleProductionSummary(
        cycle_start=cycle_start,
        cycle_end=cycle_end,
        production_kwh=total.quantize(Decimal("0.001")),
        expected_days=len(expected_dates),
        available_days=len(by_date),
        missing_dates=missing,
        provisional_dates=provisional,
    )
