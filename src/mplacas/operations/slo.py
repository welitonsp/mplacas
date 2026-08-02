from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class JobSample:
    status: str
    started_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class SloResult:
    state: str
    total_runs: int
    successful_runs: int
    failed_runs: int
    running_runs: int
    stuck_runs: int
    success_rate_percent: Decimal
    target_percent: Decimal
    target_met: bool
    minimum_completed_runs: int
    latest_run_at: datetime | None


def evaluate_job_slo(
    samples: list[JobSample],
    *,
    now: datetime | None = None,
    target_percent: Decimal = Decimal("99.0"),
    stuck_after: timedelta = timedelta(minutes=30),
    expected_run_interval: timedelta = timedelta(days=1),
    freshness_grace: timedelta = timedelta(hours=2),
    minimum_completed_runs: int = 1,
) -> SloResult:
    """Calcula SLO operacional sem depender de banco ou IA."""
    current = now or datetime.now(timezone.utc)
    successful = sum(sample.status == "SUCCEEDED" for sample in samples)
    failed = sum(sample.status == "FAILED" for sample in samples)
    running = sum(sample.status == "RUNNING" for sample in samples)
    stuck = sum(
        sample.status == "RUNNING"
        and sample.finished_at is None
        and current - _as_utc(sample.started_at) > stuck_after
        for sample in samples
    )
    completed = successful + failed
    if minimum_completed_runs < 1:
        raise ValueError("minimum completed runs must be positive")
    if expected_run_interval <= timedelta(0) or freshness_grace < timedelta(0):
        raise ValueError("freshness intervals are invalid")

    success_rate = (
        (Decimal(successful) / Decimal(completed) * Decimal("100"))
        if completed
        else Decimal("0")
    ).quantize(Decimal("0.1"))
    latest = max(samples, key=lambda sample: _as_utc(sample.started_at)) if samples else None
    latest_run_at = _as_utc(latest.started_at) if latest is not None else None
    stale = (
        latest_run_at is not None
        and current - latest_run_at > expected_run_interval + freshness_grace
    )
    if not samples:
        state = "no_history"
    elif stuck:
        state = "stuck"
    elif stale:
        state = "delayed"
    elif latest is not None and latest.status == "FAILED":
        state = "failed"
    elif completed < minimum_completed_runs:
        state = "insufficient_history"
    elif success_rate < target_percent:
        state = "failed"
    else:
        state = "healthy"
    return SloResult(
        state=state,
        total_runs=len(samples),
        successful_runs=successful,
        failed_runs=failed,
        running_runs=running,
        stuck_runs=stuck,
        success_rate_percent=success_rate,
        target_percent=target_percent,
        target_met=state == "healthy",
        minimum_completed_runs=minimum_completed_runs,
        latest_run_at=latest_run_at,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
