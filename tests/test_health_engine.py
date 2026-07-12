from decimal import Decimal

from mplacas.health.engine import HealthInputs, calculate_plant_health


def test_health_index_is_excellent_for_healthy_plant() -> None:
    result = calculate_plant_health(
        HealthInputs(
            availability_percent=Decimal("99"),
            performance_percent=Decimal("96"),
            communication_percent=Decimal("100"),
            data_quality_score=Decimal("98"),
        )
    )
    assert result.score == Decimal("98.1")
    assert result.classification == "EXCELLENT"


def test_health_index_applies_anomaly_penalties() -> None:
    result = calculate_plant_health(
        HealthInputs(
            availability_percent=Decimal("95"),
            performance_percent=Decimal("90"),
            communication_percent=Decimal("100"),
            data_quality_score=Decimal("100"),
            active_critical_anomalies=1,
            active_warning_anomalies=2,
        )
    )
    assert result.score == Decimal("77.2")
    assert result.classification == "GOOD"
    assert result.penalties["critical_anomalies"] == Decimal("12")


def test_health_index_bounds_invalid_percentages() -> None:
    result = calculate_plant_health(
        HealthInputs(
            availability_percent=Decimal("150"),
            performance_percent=Decimal("-5"),
            communication_percent=Decimal("100"),
            data_quality_score=Decimal("100"),
            active_critical_anomalies=20,
        )
    )
    assert result.score == Decimal("0.0")
    assert result.classification == "CRITICAL"
