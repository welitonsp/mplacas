from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from mplacas.operations.repository import JobRunRepository
from mplacas.operations.slo import JobSample, evaluate_job_slo


async def build_operational_status(
    repository: JobRunRepository,
    *,
    limit: int = 100,
    now: datetime | None = None,
    target_percent: Decimal = Decimal("99.0"),
    stuck_after: timedelta = timedelta(minutes=30),
) -> dict[str, object]:
    runs = await repository.list_recent(limit)
    result = evaluate_job_slo(
        [
            JobSample(
                status=run.status.value,
                started_at=run.started_at,
                finished_at=run.finished_at,
            )
            for run in runs
        ],
        now=now or datetime.now(timezone.utc),
        target_percent=target_percent,
        stuck_after=stuck_after,
    )
    payload = asdict(result)
    payload["success_rate_percent"] = str(result.success_rate_percent)
    payload["target_percent"] = str(result.target_percent)
    payload["status"] = "healthy" if result.target_met else "degraded"
    payload["alerts"] = (
        [
            {
                "code": "JOB_STUCK",
                "severity": "CRITICAL",
                "count": result.stuck_runs,
                "recommended_action": "Verificar worker, banco e disponibilidade da NEPViewer.",
            }
        ]
        if result.stuck_runs
        else []
    )
    return payload
