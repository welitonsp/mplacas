from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum


_ONE_DECIMAL = Decimal("0.1")
_THREE_DECIMALS = Decimal("0.001")


class TrendDirection(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    STABLE = "STABLE"


@dataclass(frozen=True, slots=True)
class EnergyCycleSnapshot:
    reference_month: str
    production_kwh: Decimal
    total_consumption_kwh: Decimal
    imported_kwh: Decimal
    self_sufficiency_percent: Decimal
    health_score: int

    def validate(self) -> None:
        if len(self.reference_month) != 7 or self.reference_month[4] != "-":
            raise ValueError("reference month must use YYYY-MM format")
        if any(
            value < 0
            for value in (
                self.production_kwh,
                self.total_consumption_kwh,
                self.imported_kwh,
                self.self_sufficiency_percent,
            )
        ):
            raise ValueError("energy snapshot values cannot be negative")
        if self.self_sufficiency_percent > Decimal("100"):
            raise ValueError("self sufficiency cannot exceed 100 percent")
        if not 0 <= self.health_score <= 100:
            raise ValueError("health score must be between 0 and 100")


@dataclass(frozen=True, slots=True)
class MetricTrend:
    absolute_delta: Decimal
    percent_delta: Decimal | None
    direction: TrendDirection


@dataclass(frozen=True, slots=True)
class EnergyCycleComparison:
    current_reference_month: str
    previous_reference_month: str
    production: MetricTrend
    total_consumption: MetricTrend
    imported_energy: MetricTrend
    self_sufficiency_delta_points: Decimal
    health_score_delta: int


def _trend(current: Decimal, previous: Decimal, *, stable_tolerance_percent: Decimal) -> MetricTrend:
    absolute_delta = (current - previous).quantize(_THREE_DECIMALS, rounding=ROUND_HALF_UP)
    if previous == 0:
        direction = TrendDirection.STABLE if current == 0 else TrendDirection.UP
        return MetricTrend(
            absolute_delta=absolute_delta,
            percent_delta=None,
            direction=direction,
        )

    percent_delta = ((current - previous) / previous * Decimal("100")).quantize(
        _ONE_DECIMAL,
        rounding=ROUND_HALF_UP,
    )
    if abs(percent_delta) <= stable_tolerance_percent:
        direction = TrendDirection.STABLE
    elif percent_delta > 0:
        direction = TrendDirection.UP
    else:
        direction = TrendDirection.DOWN
    return MetricTrend(
        absolute_delta=absolute_delta,
        percent_delta=percent_delta,
        direction=direction,
    )


def compare_energy_cycles(
    *,
    current: EnergyCycleSnapshot,
    previous: EnergyCycleSnapshot,
    stable_tolerance_percent: Decimal = Decimal("2.0"),
) -> EnergyCycleComparison:
    """Compara dois ciclos sem inferir causas nem usar IA generativa."""
    current.validate()
    previous.validate()
    if stable_tolerance_percent < 0:
        raise ValueError("stable tolerance cannot be negative")
    if current.reference_month <= previous.reference_month:
        raise ValueError("current cycle must be newer than previous cycle")

    return EnergyCycleComparison(
        current_reference_month=current.reference_month,
        previous_reference_month=previous.reference_month,
        production=_trend(
            current.production_kwh,
            previous.production_kwh,
            stable_tolerance_percent=stable_tolerance_percent,
        ),
        total_consumption=_trend(
            current.total_consumption_kwh,
            previous.total_consumption_kwh,
            stable_tolerance_percent=stable_tolerance_percent,
        ),
        imported_energy=_trend(
            current.imported_kwh,
            previous.imported_kwh,
            stable_tolerance_percent=stable_tolerance_percent,
        ),
        self_sufficiency_delta_points=(
            current.self_sufficiency_percent - previous.self_sufficiency_percent
        ).quantize(_ONE_DECIMAL, rounding=ROUND_HALF_UP),
        health_score_delta=current.health_score - previous.health_score,
    )
