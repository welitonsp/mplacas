from decimal import Decimal

import pytest

from mplacas.intelligence.anomaly_engine import (
    AnomalyLevel,
    DailyPerformanceInput,
    assess_daily_performance,
    is_low_irradiation,
)


def test_is_low_irradiation_relative_to_median_real_caldas_novas_data() -> None:
    # 24/06: 2.79 kWh/m^2 against a 4.89 median (57%) — cloudy day.
    assert is_low_irradiation(Decimal("2.79"), Decimal("4.89"), 30) is True
    # 10/06: 4.75 kWh/m^2 against a 4.89 median (97%) — normal sun.
    assert is_low_irradiation(Decimal("4.75"), Decimal("4.89"), 30) is False


def test_is_low_irradiation_fails_toward_alerting_with_few_samples() -> None:
    assert (
        is_low_irradiation(
            Decimal("2.79"), Decimal("4.89"), 4, minimum_sample_days=5
        )
        is False
    )
    assert (
        is_low_irradiation(
            Decimal("2.79"), Decimal("4.89"), 5, minimum_sample_days=5
        )
        is True
    )


def test_is_low_irradiation_handles_missing_data() -> None:
    assert is_low_irradiation(None, Decimal("4.89"), 30) is False
    assert is_low_irradiation(Decimal("2.79"), None, 30) is False
    assert is_low_irradiation(Decimal("2.79"), Decimal("0"), 30) is False


def test_classifies_normal_performance() -> None:
    result = assess_daily_performance(
        DailyPerformanceInput(
            actual_production_kwh=Decimal("18"),
            expected_production_kwh=Decimal("20"),
            irradiation_kwh_m2=Decimal("5.4"),
        )
    )

    assert result.level is AnomalyLevel.NORMAL
    assert result.deviation_percent == Decimal("-10.0")
    assert result.diagnostics[0].code == "PERFORMANCE_WITHIN_EXPECTED_RANGE"


def test_distinguishes_low_irradiation_context() -> None:
    result = assess_daily_performance(
        DailyPerformanceInput(
            actual_production_kwh=Decimal("9"),
            expected_production_kwh=Decimal("20"),
            irradiation_kwh_m2=Decimal("1.2"),
            irradiation_median_kwh_m2=Decimal("5.0"),
            irradiation_sample_days=10,
        )
    )

    assert result.level is AnomalyLevel.CRITICAL
    assert result.diagnostics[0].code == "LOW_PRODUCTION_WITH_LOW_IRRADIATION"


def test_low_irradiation_needs_a_stable_median_to_explain_a_drop() -> None:
    """Too few historical days => the median cannot be trusted, so the

    engine must not claim the drop was explained by weather even though the
    day's irradiation is numerically far below the (unstable) median.
    """
    result = assess_daily_performance(
        DailyPerformanceInput(
            actual_production_kwh=Decimal("9"),
            expected_production_kwh=Decimal("20"),
            irradiation_kwh_m2=Decimal("1.2"),
            irradiation_median_kwh_m2=Decimal("5.0"),
            irradiation_sample_days=2,
        )
    )

    assert result.level is AnomalyLevel.CRITICAL
    assert result.diagnostics[0].code == "LOW_PRODUCTION_NOT_EXPLAINED_BY_LOW_IRRADIATION"


def test_irradiation_close_to_median_is_not_low() -> None:
    """A day at 97% of the local median is normal, not cloudy — regression

    guard for the real Caldas Novas/GO case where 4.75/4.89 must not be
    classified as low irradiation.
    """
    result = assess_daily_performance(
        DailyPerformanceInput(
            actual_production_kwh=Decimal("9"),
            expected_production_kwh=Decimal("20"),
            irradiation_kwh_m2=Decimal("4.75"),
            irradiation_median_kwh_m2=Decimal("4.89"),
            irradiation_sample_days=30,
        )
    )

    assert result.diagnostics[0].code == "LOW_PRODUCTION_NOT_EXPLAINED_BY_LOW_IRRADIATION"


def test_flags_drop_not_explained_by_low_irradiation() -> None:
    result = assess_daily_performance(
        DailyPerformanceInput(
            actual_production_kwh=Decimal("10"),
            expected_production_kwh=Decimal("20"),
            irradiation_kwh_m2=Decimal("5.8"),
        )
    )

    assert result.level is AnomalyLevel.CRITICAL
    assert result.deviation_kwh == Decimal("-10.000")
    assert result.diagnostics[0].code == "LOW_PRODUCTION_NOT_EXPLAINED_BY_LOW_IRRADIATION"


def test_does_not_invent_climate_context() -> None:
    result = assess_daily_performance(
        DailyPerformanceInput(
            actual_production_kwh=Decimal("12"),
            expected_production_kwh=Decimal("20"),
            irradiation_kwh_m2=None,
        )
    )

    assert result.level is AnomalyLevel.ANOMALY
    assert result.climate_context_available is False
    assert result.diagnostics[0].code == "LOW_PRODUCTION_WITHOUT_CLIMATE_CONTEXT"


def test_incomplete_data_blocks_conclusive_classification() -> None:
    result = assess_daily_performance(
        DailyPerformanceInput(
            actual_production_kwh=Decimal("0"),
            expected_production_kwh=Decimal("20"),
            irradiation_kwh_m2=Decimal("6"),
            data_complete=False,
        )
    )

    assert result.level is AnomalyLevel.ATTENTION
    assert result.deviation_percent is None
    assert result.diagnostics[0].code == "INCOMPLETE_INPUT_DATA"


def test_rejects_invalid_threshold_order() -> None:
    with pytest.raises(ValueError, match="ordered"):
        assess_daily_performance(
            DailyPerformanceInput(
                actual_production_kwh=Decimal("10"),
                expected_production_kwh=Decimal("20"),
                irradiation_kwh_m2=Decimal("4"),
            ),
            attention_threshold_percent=Decimal("40"),
            anomaly_threshold_percent=Decimal("20"),
        )
