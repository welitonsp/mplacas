from datetime import date, timedelta
from decimal import Decimal

import pytest

from mplacas.billing.production import DailyProductionPoint, summarize_cycle_production


def test_cycle_summary_is_inclusive_and_complete() -> None:
    start = date(2026, 5, 18)
    end = date(2026, 5, 20)
    points = [
        DailyProductionPoint(start + timedelta(days=offset), Decimal("10.500"))
        for offset in range(3)
    ]
    result = summarize_cycle_production(points, cycle_start=start, cycle_end=end)
    assert result.production_kwh == Decimal("31.500")
    assert result.expected_days == 3
    assert result.available_days == 3
    assert result.complete is True


def test_cycle_summary_reports_missing_and_provisional_days() -> None:
    start = date(2026, 5, 18)
    end = date(2026, 5, 20)
    result = summarize_cycle_production(
        [
            DailyProductionPoint(start, Decimal("8")),
            DailyProductionPoint(end, Decimal("9"), consolidated=False),
        ],
        cycle_start=start,
        cycle_end=end,
    )
    assert result.missing_dates == (date(2026, 5, 19),)
    assert result.provisional_dates == (end,)
    assert result.complete is False


def test_cycle_summary_rejects_duplicate_date() -> None:
    day = date(2026, 5, 18)
    with pytest.raises(ValueError, match="duplicate production date"):
        summarize_cycle_production(
            [DailyProductionPoint(day, Decimal("1")), DailyProductionPoint(day, Decimal("2"))],
            cycle_start=day,
            cycle_end=day,
        )
