from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class DailyClimateObservation:
    observation_date: date
    irradiation_kwh_m2: Decimal | None
    cloud_cover_percent: Decimal | None = None
    precipitation_mm: Decimal | None = None
    source: str = "UNSPECIFIED"

    def validate(self) -> None:
        if self.irradiation_kwh_m2 is not None and self.irradiation_kwh_m2 < 0:
            raise ValueError("irradiation cannot be negative")
        if (
            self.cloud_cover_percent is not None
            and not Decimal("0") <= self.cloud_cover_percent <= Decimal("100")
        ):
            raise ValueError("cloud cover must be between 0 and 100 percent")
        if self.precipitation_mm is not None and self.precipitation_mm < 0:
            raise ValueError("precipitation cannot be negative")
