from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class QualityCode(StrEnum):
    VALID = "VALID"
    NEGATIVE_ENERGY = "NEGATIVE_ENERGY"
    IMPLAUSIBLE_DAILY_YIELD = "IMPLAUSIBLE_DAILY_YIELD"
    FUTURE_DATE = "FUTURE_DATE"
    MISSING_INSTALLED_POWER = "MISSING_INSTALLED_POWER"


@dataclass(frozen=True, slots=True)
class QualityAssessment:
    score: int
    codes: tuple[QualityCode, ...]

    @property
    def accepted(self) -> bool:
        return self.score >= 70 and QualityCode.NEGATIVE_ENERGY not in self.codes


class DataQualityEngine:
    """Valida energia diária sem converter ausência ou inconsistência em zero."""

    def assess_daily_energy(
        self,
        *,
        production_date: date,
        energy_kwh: Decimal,
        installed_power_kwp: Decimal | None,
        today: date,
    ) -> QualityAssessment:
        score = 100
        codes: list[QualityCode] = []

        if production_date > today:
            score -= 50
            codes.append(QualityCode.FUTURE_DATE)

        if energy_kwh < 0:
            score = 0
            codes.append(QualityCode.NEGATIVE_ENERGY)

        if installed_power_kwp is None or installed_power_kwp <= 0:
            score -= 20
            codes.append(QualityCode.MISSING_INSTALLED_POWER)
        elif energy_kwh / installed_power_kwp > Decimal("12"):
            score -= 50
            codes.append(QualityCode.IMPLAUSIBLE_DAILY_YIELD)

        if not codes:
            codes.append(QualityCode.VALID)

        return QualityAssessment(score=max(score, 0), codes=tuple(codes))
