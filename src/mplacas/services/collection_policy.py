from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True, slots=True)
class CollectionWindow:
    start: date
    end: date
    consolidate_through: date | None
    reason: str


class CollectionPolicy:
    """Define janelas determinísticas para coleta diária e reconciliação histórica."""

    def __init__(self, *, backfill_days: int = 7) -> None:
        if backfill_days < 1:
            raise ValueError("backfill_days deve ser maior que zero")
        self._backfill_days = backfill_days

    def intraday(self, today: date) -> CollectionWindow:
        return CollectionWindow(
            start=today,
            end=today,
            consolidate_through=None,
            reason="intraday",
        )

    def d_plus_one(self, today: date) -> CollectionWindow:
        yesterday = today - timedelta(days=1)
        return CollectionWindow(
            start=yesterday,
            end=yesterday,
            consolidate_through=yesterday,
            reason="d_plus_one",
        )

    def weekly_backfill(self, today: date) -> CollectionWindow:
        end = today - timedelta(days=1)
        start = end - timedelta(days=self._backfill_days - 1)
        return CollectionWindow(
            start=start,
            end=end,
            consolidate_through=end,
            reason="weekly_backfill",
        )
