from datetime import date

import pytest

from mplacas.services.collection_policy import CollectionPolicy


def test_intraday_keeps_current_day_provisional() -> None:
    window = CollectionPolicy().intraday(date(2026, 7, 12))
    assert window.start == date(2026, 7, 12)
    assert window.end == date(2026, 7, 12)
    assert window.consolidate_through is None
    assert window.reason == "intraday"


def test_d_plus_one_consolidates_yesterday() -> None:
    window = CollectionPolicy().d_plus_one(date(2026, 7, 12))
    assert window.start == date(2026, 7, 11)
    assert window.end == date(2026, 7, 11)
    assert window.consolidate_through == date(2026, 7, 11)


def test_weekly_backfill_uses_seven_closed_days() -> None:
    window = CollectionPolicy(backfill_days=7).weekly_backfill(date(2026, 7, 12))
    assert window.start == date(2026, 7, 5)
    assert window.end == date(2026, 7, 11)
    assert window.consolidate_through == date(2026, 7, 11)


def test_backfill_days_must_be_positive() -> None:
    with pytest.raises(ValueError, match="maior que zero"):
        CollectionPolicy(backfill_days=0)
