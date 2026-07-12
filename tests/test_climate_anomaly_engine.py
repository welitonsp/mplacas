from decimal import Decimal

import pytest

from mplacas.intelligence.anomaly_engine import (
    AnomalyLevel,
    DailyPerformanceInput,
    assess_daily_performance,
)


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
        )
    )

    assert result.level is AnomalyLevel.CRITICAL
    assert result.diagnostics[0].code == "LOW_PRODUCTION_WITH_LOW_IRRADIATION"


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
