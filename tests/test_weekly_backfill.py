from __future__ import annotations

from datetime import datetime

import pytest

import mplacas.weekly_backfill as weekly_backfill
from mplacas.core.config import get_settings


def test_weekly_backfill_processes_oldest_date_first(monkeypatch) -> None:
    get_settings.cache_clear()
    captured: list[str] = []

    async def fake_collection(*, target_date: str | None, now: datetime | None = None) -> None:
        assert now is not None
        captured.append(str(target_date))

    monkeypatch.setattr(weekly_backfill, "run_collection", fake_collection)
    now = datetime.fromisoformat("2026-07-27T00:30:00-03:00")

    dates = weekly_backfill.asyncio.run(
        weekly_backfill.run_weekly_backfill(days=7, end_date=None, now=now)
    )

    assert captured == [
        "2026-07-20",
        "2026-07-21",
        "2026-07-22",
        "2026-07-23",
        "2026-07-24",
        "2026-07-25",
        "2026-07-26",
    ]
    assert tuple(value.isoformat() for value in dates) == tuple(captured)
    get_settings.cache_clear()


def test_weekly_backfill_accepts_explicit_end_date(monkeypatch) -> None:
    get_settings.cache_clear()
    captured: list[str] = []

    async def fake_collection(*, target_date: str | None, now: datetime | None = None) -> None:
        captured.append(str(target_date))

    monkeypatch.setattr(weekly_backfill, "run_collection", fake_collection)

    weekly_backfill.asyncio.run(
        weekly_backfill.run_weekly_backfill(days=3, end_date="2026-07-15")
    )

    assert captured == ["2026-07-13", "2026-07-14", "2026-07-15"]
    get_settings.cache_clear()


@pytest.mark.parametrize("days", [0, 32])
def test_weekly_backfill_rejects_unsafe_window(days: int) -> None:
    with pytest.raises(ValueError, match="days must be between 1 and 31"):
        weekly_backfill.asyncio.run(
            weekly_backfill.run_weekly_backfill(days=days, end_date="2026-07-15")
        )


def test_weekly_backfill_stops_after_first_failed_day(monkeypatch) -> None:
    get_settings.cache_clear()
    captured: list[str] = []

    async def fake_collection(*, target_date: str | None, now: datetime | None = None) -> None:
        captured.append(str(target_date))
        if target_date == "2026-07-14":
            raise RuntimeError("synthetic collection failure")

    monkeypatch.setattr(weekly_backfill, "run_collection", fake_collection)

    with pytest.raises(RuntimeError, match="synthetic collection failure"):
        weekly_backfill.asyncio.run(
            weekly_backfill.run_weekly_backfill(days=3, end_date="2026-07-15")
        )

    assert captured == ["2026-07-13", "2026-07-14"]
    get_settings.cache_clear()


def test_weekly_backfill_help() -> None:
    with pytest.raises(SystemExit) as exc:
        weekly_backfill.main(["--help"])
    assert exc.value.code == 0
