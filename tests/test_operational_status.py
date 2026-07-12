from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from mplacas.operations.status import build_operational_status


class FakeRepository:
    def __init__(self, runs: list[object]) -> None:
        self.runs = runs

    async def list_recent(self, limit: int = 100) -> list[object]:
        return self.runs[:limit]


@pytest.mark.asyncio
async def test_operational_status_is_healthy() -> None:
    now = datetime(2026, 7, 12, 20, 0, tzinfo=timezone.utc)
    runs = [
        SimpleNamespace(
            status=SimpleNamespace(value="SUCCEEDED"),
            started_at=now - timedelta(minutes=5),
            finished_at=now - timedelta(minutes=4),
        )
        for _ in range(10)
    ]
    result = await build_operational_status(FakeRepository(runs), now=now)  # type: ignore[arg-type]
    assert result["status"] == "healthy"
    assert result["success_rate_percent"] == "100.0"
    assert result["alerts"] == []


@pytest.mark.asyncio
async def test_operational_status_reports_stuck_job() -> None:
    now = datetime(2026, 7, 12, 20, 0, tzinfo=timezone.utc)
    runs = [
        SimpleNamespace(
            status=SimpleNamespace(value="RUNNING"),
            started_at=now - timedelta(hours=1),
            finished_at=None,
        )
    ]
    result = await build_operational_status(FakeRepository(runs), now=now)  # type: ignore[arg-type]
    assert result["status"] == "degraded"
    assert result["stuck_runs"] == 1
    alerts = result["alerts"]
    assert isinstance(alerts, list)
    assert alerts[0]["code"] == "JOB_STUCK"
