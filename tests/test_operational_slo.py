from datetime import datetime, timedelta, timezone
from decimal import Decimal

from mplacas.operations.slo import JobSample, evaluate_job_slo


def test_slo_is_met_when_completed_runs_succeed() -> None:
    now = datetime(2026, 7, 12, 20, 0, tzinfo=timezone.utc)
    result = evaluate_job_slo(
        [
            JobSample("SUCCEEDED", now - timedelta(minutes=10), now - timedelta(minutes=9)),
            JobSample("SUCCEEDED", now - timedelta(minutes=5), now - timedelta(minutes=4)),
        ],
        now=now,
    )
    assert result.success_rate_percent == Decimal("100.0")
    assert result.target_met is True


def test_slo_detects_failure_and_stuck_run() -> None:
    now = datetime(2026, 7, 12, 20, 0, tzinfo=timezone.utc)
    result = evaluate_job_slo(
        [
            JobSample("SUCCEEDED", now - timedelta(hours=2), now - timedelta(hours=2)),
            JobSample("FAILED", now - timedelta(hours=1), now - timedelta(hours=1)),
            JobSample("RUNNING", now - timedelta(minutes=45), None),
        ],
        now=now,
        target_percent=Decimal("90"),
    )
    assert result.success_rate_percent == Decimal("50.0")
    assert result.stuck_runs == 1
    assert result.target_met is False


def test_no_runs_are_never_reported_as_healthy() -> None:
    now = datetime(2026, 7, 12, 20, 0, tzinfo=timezone.utc)
    result = evaluate_job_slo([], now=now)
    assert result.success_rate_percent == Decimal("0.0")
    assert result.state == "no_history"
    assert result.target_met is False


def test_stale_last_run_is_delayed_even_when_it_succeeded() -> None:
    now = datetime(2026, 7, 12, 20, 0, tzinfo=timezone.utc)
    result = evaluate_job_slo(
        [JobSample("SUCCEEDED", now - timedelta(hours=27), now - timedelta(hours=26))],
        now=now,
    )
    assert result.state == "delayed"
    assert result.target_met is False


def test_fresh_running_job_without_completed_minimum_is_insufficient() -> None:
    now = datetime(2026, 7, 12, 20, 0, tzinfo=timezone.utc)
    result = evaluate_job_slo(
        [JobSample("RUNNING", now - timedelta(minutes=5), None)],
        now=now,
    )
    assert result.state == "insufficient_history"
    assert result.target_met is False
