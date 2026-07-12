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


def test_no_completed_runs_do_not_create_false_failure() -> None:
    now = datetime(2026, 7, 12, 20, 0, tzinfo=timezone.utc)
    result = evaluate_job_slo([], now=now)
    assert result.success_rate_percent == Decimal("100.0")
    assert result.target_met is True
