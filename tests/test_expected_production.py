from __future__ import annotations

from decimal import Decimal

import pytest

from mplacas.intelligence.anomaly_engine import (
    AnomalyLevel,
    DailyPerformanceInput,
    assess_daily_performance,
)
from mplacas.photovoltaic.expected_production import (
    EXPECTED_PRODUCTION_MODEL_VERSION,
    EXPECTED_PRODUCTION_NATURE,
    calculate_expected_daily_production,
)


def test_model_version_and_nature_constants() -> None:
    assert EXPECTED_PRODUCTION_MODEL_VERSION == "MPLACAS_EXPECTED_DAILY_PRODUCTION_V1"
    assert EXPECTED_PRODUCTION_NATURE == "SEASONAL_CLEAR_SKY_P90_ENVELOPE"


def test_happy_path_multiplies_and_quantizes_to_three_decimals() -> None:
    result = calculate_expected_daily_production(
        dc_capacity_kwp=Decimal("100.000"),
        clear_sky_poa_p90_kwh_m2=Decimal("6.500"),
        baseline_median_performance_ratio=Decimal("0.8500"),
    )
    assert result is not None
    assert result.expected_daily_production_kwh == Decimal("552.500")
    assert result.dc_capacity_kwp == Decimal("100.000")
    assert result.clear_sky_poa_p90_kwh_m2 == Decimal("6.500")
    assert result.baseline_median_performance_ratio == Decimal("0.8500")
    assert result.model_version == EXPECTED_PRODUCTION_MODEL_VERSION
    assert result.nature == EXPECTED_PRODUCTION_NATURE


def test_quantization_rounds_half_up() -> None:
    # 10 * 1 * 0.33335 = 3.3335 -> rounds to 3.334 with ROUND_HALF_UP.
    result = calculate_expected_daily_production(
        dc_capacity_kwp=Decimal("10"),
        clear_sky_poa_p90_kwh_m2=Decimal("1"),
        baseline_median_performance_ratio=Decimal("0.33335"),
    )
    assert result is not None
    assert result.expected_daily_production_kwh == Decimal("3.334")


@pytest.mark.parametrize(
    "dc_capacity_kwp,clear_sky_poa_p90_kwh_m2,baseline_median_performance_ratio",
    [
        (None, Decimal("6.500"), Decimal("0.8500")),
        (Decimal("100.000"), None, Decimal("0.8500")),
        (Decimal("100.000"), Decimal("6.500"), None),
        (Decimal("0"), Decimal("6.500"), Decimal("0.8500")),
        (Decimal("100.000"), Decimal("0"), Decimal("0.8500")),
        (Decimal("100.000"), Decimal("6.500"), Decimal("0")),
        (Decimal("-100.000"), Decimal("6.500"), Decimal("0.8500")),
        (Decimal("100.000"), Decimal("-6.500"), Decimal("0.8500")),
        (Decimal("100.000"), Decimal("6.500"), Decimal("-0.8500")),
    ],
)
def test_returns_none_for_null_zero_or_negative_inputs(
    dc_capacity_kwp: Decimal | None,
    clear_sky_poa_p90_kwh_m2: Decimal | None,
    baseline_median_performance_ratio: Decimal | None,
) -> None:
    assert (
        calculate_expected_daily_production(
            dc_capacity_kwp=dc_capacity_kwp,
            clear_sky_poa_p90_kwh_m2=clear_sky_poa_p90_kwh_m2,
            baseline_median_performance_ratio=baseline_median_performance_ratio,
        )
        is None
    )


def test_equivalent_to_former_frontend_formula() -> None:
    """Numeric equivalence with the removed `deriveExpectedDailyProduction`.

    The frontend (`photovoltaic-contracts.ts:274`, removed by ADR-068 Etapa
    C) computed `dcCapacityKwp * clearSkyPoaKwhM2 * performanceRatio` as a
    JS `number` with no rounding. This test reproduces that computation in
    Python `float` for the same representative payload used in the ADR
    example (section 3) and asserts the backend result matches within the
    `0.001` kWh quantization tolerance the ADR fixes (section "Validação",
    item 3, and Negativas).
    """
    dc_capacity_kwp = Decimal("45.200")
    clear_sky_poa_p90_kwh_m2 = Decimal("6.789")
    baseline_median_performance_ratio = Decimal("0.8123")

    result = calculate_expected_daily_production(
        dc_capacity_kwp=dc_capacity_kwp,
        clear_sky_poa_p90_kwh_m2=clear_sky_poa_p90_kwh_m2,
        baseline_median_performance_ratio=baseline_median_performance_ratio,
    )
    assert result is not None

    frontend_equivalent = (
        float(dc_capacity_kwp) * float(clear_sky_poa_p90_kwh_m2)
        * float(baseline_median_performance_ratio)
    )

    assert abs(float(result.expected_daily_production_kwh) - frontend_equivalent) <= 0.001


def test_rounding_difference_does_not_change_severity_classification() -> None:
    """A 0.001 kWh rounding difference must not flip the anomaly severity.

    `assess_daily_performance` is the same classifier
    `analyze_recent_persisted_anomalies` (`intelligence/anomaly_service.py`)
    calls per day with `expected_daily_production_kwh`. This proves that
    quantizing the expectation to `0.001` kWh (ADR-068 section 3) cannot, by
    itself, move a day across a severity boundary, except exactly at the
    threshold — the case enumerated explicitly below.
    """
    actual = Decimal("85.000")

    # Comfortably inside NORMAL either way (deviation well above -15%).
    baseline_expected = Decimal("100.000")
    rounded_expected = baseline_expected + Decimal("0.001")
    baseline_level = assess_daily_performance(
        DailyPerformanceInput(
            actual_production_kwh=actual,
            expected_production_kwh=baseline_expected,
            irradiation_kwh_m2=None,
        )
    ).level
    rounded_level = assess_daily_performance(
        DailyPerformanceInput(
            actual_production_kwh=actual,
            expected_production_kwh=rounded_expected,
            irradiation_kwh_m2=None,
        )
    ).level
    assert baseline_level == rounded_level == AnomalyLevel.NORMAL

    # Exactly on the ATTENTION/ANOMALY threshold: this is the one case the
    # ADR calls out explicitly where a 0.001 kWh nudge of `expected` *does*
    # flip the classification, because the raw deviation lands exactly on
    # the ROUND_HALF_UP tie (-29.950% rounds away from zero to -30.0%, which
    # is ANOMALY since the comparison is `>` -30, not `>=`).
    actual = Decimal("70.050")
    on_threshold_expected = Decimal("100.000")
    on_threshold_level = assess_daily_performance(
        DailyPerformanceInput(
            actual_production_kwh=actual,
            expected_production_kwh=on_threshold_expected,
            irradiation_kwh_m2=None,
        )
    ).level
    assert on_threshold_level == AnomalyLevel.ANOMALY

    nudged_level = assess_daily_performance(
        DailyPerformanceInput(
            actual_production_kwh=actual,
            expected_production_kwh=on_threshold_expected - Decimal("0.001"),
            irradiation_kwh_m2=None,
        )
    ).level
    # deviation = 70.050 - 99.999 = -29.949 -> -29.9% quantized to 0.1,
    # which is on the ATTENTION side of the same boundary: a 0.001 kWh
    # change in `expected` is exactly what moves this day off the tie.
    assert nudged_level == AnomalyLevel.ATTENTION
