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
    expected_run_interval: timedelta = timedelta(days=1),
    freshness_grace: timedelta = timedelta(hours=2),
    minimum_completed_runs: int = 1,
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
        expected_run_interval=expected_run_interval,
        freshness_grace=freshness_grace,
        minimum_completed_runs=minimum_completed_runs,
    )
    payload = asdict(result)
    payload["success_rate_percent"] = str(result.success_rate_percent)
    payload["target_percent"] = str(result.target_percent)
    payload["status"] = "healthy" if result.target_met else "degraded"
    alert_contracts = {
        "no_history": (
            "JOB_NO_HISTORY",
            "CRITICAL",
            "Verificar Scheduler, IAM e criação das execuções operacionais.",
        ),
        "delayed": (
            "JOB_DELAYED",
            "CRITICAL",
            "Verificar atraso do Scheduler e a última execução do pipeline.",
        ),
        "stuck": (
            "JOB_STUCK",
            "CRITICAL",
            "Verificar worker, banco e disponibilidade da NEPViewer.",
        ),
        "failed": (
            "JOB_FAILED",
            "CRITICAL",
            "Inspecionar a última falha e executar o runbook do pipeline.",
        ),
        "insufficient_history": (
            "JOB_INSUFFICIENT_HISTORY",
            "WARNING",
            "Aguardar ou validar o mínimo de execuções concluídas esperado.",
        ),
    }
    contract = alert_contracts.get(result.state)
    payload["alerts"] = (
        [
            {
                "code": contract[0],
                "severity": contract[1],
                "count": result.stuck_runs if result.state == "stuck" else 1,
                "recommended_action": contract[2],
            }
        ]
        if contract is not None
        else []
    )
    return payload
