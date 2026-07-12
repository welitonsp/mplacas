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
    total_runs: int
    successful_runs: int
    failed_runs: int
    running_runs: int
    stuck_runs: int
    success_rate_percent: Decimal
    target_percent: Decimal
    target_met: bool


def evaluate_job_slo(
    samples: list[JobSample],
    *,
    now: datetime | None = None,
    target_percent: Decimal = Decimal("99.0"),
    stuck_after: timedelta = timedelta(minutes=30),
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
    success_rate = (
        (Decimal(successful) / Decimal(completed) * Decimal("100"))
        if completed
        else Decimal("100")
    ).quantize(Decimal("0.1"))
    return SloResult(
        total_runs=len(samples),
        successful_runs=successful,
        failed_runs=failed,
        running_runs=running,
        stuck_runs=stuck,
        success_rate_percent=success_rate,
        target_percent=target_percent,
        target_met=success_rate >= target_percent and stuck == 0,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
