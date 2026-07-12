from datetime import datetime, timedelta, timezone
from decimal import Decimal

from mplacas.anomalies.engine import AnomalyEngine, AnomalyType, Severity


def test_detects_communication_loss() -> None:
    now = datetime(2026, 7, 12, 15, 0, tzinfo=timezone.utc)
    anomaly = AnomalyEngine().detect_communication_loss(
        last_update=now - timedelta(hours=1),
        now=now,
    )

    assert anomaly is not None
    assert anomaly.anomaly_type is AnomalyType.COMMUNICATION_LOSS
    assert anomaly.severity is Severity.WARNING


def test_detects_zero_production_as_critical() -> None:
    anomaly = AnomalyEngine().detect_daily_yield(
        energy_kwh=Decimal("0"),
        installed_power_kwp=Decimal("4.700"),
    )

    assert anomaly is not None
    assert anomaly.anomaly_type is AnomalyType.ZERO_PRODUCTION
    assert anomaly.severity is Severity.CRITICAL
