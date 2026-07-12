from __future__ import annotations

from datetime import date
from typing import Protocol

from mplacas.climate.models import DailyClimateObservation


class ClimateProvider(Protocol):
    async def daily_observations(
        self,
        *,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
    ) -> tuple[DailyClimateObservation, ...]:
        """Return daily climate observations for the inclusive interval."""
