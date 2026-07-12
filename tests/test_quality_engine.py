from datetime import date
from decimal import Decimal

from mplacas.quality.engine import DataQualityEngine, QualityCode


def test_quality_accepts_valid_daily_energy() -> None:
    assessment = DataQualityEngine().assess_daily_energy(
        production_date=date(2026, 7, 12),
        energy_kwh=Decimal("21.450"),
        installed_power_kwp=Decimal("4.700"),
        today=date(2026, 7, 12),
    )

    assert assessment.accepted is True
    assert assessment.score == 100
    assert assessment.codes == (QualityCode.VALID,)


def test_quality_rejects_negative_energy() -> None:
    assessment = DataQualityEngine().assess_daily_energy(
        production_date=date(2026, 7, 12),
        energy_kwh=Decimal("-1"),
        installed_power_kwp=Decimal("4.700"),
        today=date(2026, 7, 12),
    )

    assert assessment.accepted is False
    assert QualityCode.NEGATIVE_ENERGY in assessment.codes
