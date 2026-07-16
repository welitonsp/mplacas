from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from mplacas.core.security import require_operations_read
from mplacas.db.session import SessionFactory
from mplacas.operations.repository import JobRunRepository
from mplacas.operations.status import build_operational_status

router = APIRouter(
    prefix="/operations",
    tags=["operational"],
    dependencies=[Depends(require_operations_read)],
)


@router.get("/jobs")
async def recent_jobs(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
    async with SessionFactory() as session:
        runs = await JobRunRepository(session).list_recent(limit)
    return {
        "count": len(runs),
        "items": [
            {
                "id": str(run.id),
                "job_name": run.job_name,
                "status": run.status.value,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "duration_ms": run.duration_ms,
                "records_seen": run.records_seen,
                "records_changed": run.records_changed,
                "metrics": run.metrics,
                "error_code": run.error_code,
            }
            for run in runs
        ],
    }


@router.get("/status")
async def operational_status(limit: int = Query(default=100, ge=1, le=100)) -> dict[str, object]:
    async with SessionFactory() as session:
        repository = JobRunRepository(session)
        return await build_operational_status(repository, limit=limit)
