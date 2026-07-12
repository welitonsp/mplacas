from decimal import Decimal

import pytest

from mplacas.intelligence.trends import (
    EnergyCycleSnapshot,
    TrendDirection,
    compare_energy_cycles,
)


def _snapshot(
    *,
    reference_month: str,
    production: str,
    consumption: str,
    imported: str,
    self_sufficiency: str,
    health_score: int,
) -> EnergyCycleSnapshot:
    return EnergyCycleSnapshot(
        reference_month=reference_month,
        production_kwh=Decimal(production),
        total_consumption_kwh=Decimal(consumption),
        imported_kwh=Decimal(imported),
        self_sufficiency_percent=Decimal(self_sufficiency),
        health_score=health_score,
    )


def test_compares_cycles_with_auditable_deltas() -> None:
    result = compare_energy_cycles(
        current=_snapshot(
            reference_month="2026-07",
            production="330",
            consumption="410",
            imported="250",
            self_sufficiency="39.0",
            health_score=94,
        ),
        previous=_snapshot(
            reference_month="2026-06",
            production="300",
            consumption="400",
            imported="280",
            self_sufficiency="30.0",
            health_score=88,
        ),
    )

    assert result.production.absolute_delta == Decimal("30.000")
    assert result.production.percent_delta == Decimal("10.0")
    assert result.production.direction is TrendDirection.UP
    assert result.total_consumption.direction is TrendDirection.UP
    assert result.imported_energy.direction is TrendDirection.DOWN
    assert result.self_sufficiency_delta_points == Decimal("9.0")
    assert result.health_score_delta == 6


def test_treats_small_variation_as_stable() -> None:
    result = compare_energy_cycles(
        current=_snapshot(
            reference_month="2026-07",
            production="303",
            consumption="400",
            imported="280",
            self_sufficiency="30",
            health_score=90,
        ),
        previous=_snapshot(
            reference_month="2026-06",
            production="300",
            consumption="400",
            imported="280",
            self_sufficiency="30",
            health_score=90,
        ),
    )

    assert result.production.percent_delta == Decimal("1.0")
    assert result.production.direction is TrendDirection.STABLE


def test_handles_zero_baseline_without_division_or_fake_percentage() -> None:
    result = compare_energy_cycles(
        current=_snapshot(
            reference_month="2026-07",
            production="10",
            consumption="20",
            imported="10",
            self_sufficiency="50",
            health_score=80,
        ),
        previous=_snapshot(
            reference_month="2026-06",
            production="0",
            consumption="0",
            imported="0",
            self_sufficiency="0",
            health_score=70,
        ),
    )

    assert result.production.percent_delta is None
    assert result.production.direction is TrendDirection.UP


def test_rejects_non_chronological_comparison() -> None:
    current = _snapshot(
        reference_month="2026-06",
        production="300",
        consumption="400",
        imported="280",
        self_sufficiency="30",
        health_score=90,
    )
    with pytest.raises(ValueError, match="newer"):
        compare_energy_cycles(current=current, previous=current)
