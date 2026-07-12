from __future__ import annotations

from datetime import UTC, datetime
from time import monotonic

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.operations.models import JobRun, JobStatus


class JobRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def start(self, job_name: str) -> tuple[JobRun, float]:
        run = JobRun(job_name=job_name, status=JobStatus.RUNNING)
        self._session.add(run)
        await self._session.flush()
        return run, monotonic()

    async def succeed(
        self,
        run: JobRun,
        started_monotonic: float,
        *,
        records_seen: int = 0,
        records_changed: int = 0,
        metrics: dict[str, object] | None = None,
    ) -> JobRun:
        run.status = JobStatus.SUCCEEDED
        run.finished_at = datetime.now(UTC)
        run.duration_ms = max(0, int((monotonic() - started_monotonic) * 1000))
        run.records_seen = records_seen
        run.records_changed = records_changed
        run.metrics = metrics or {}
        await self._session.flush()
        return run

    async def fail(
        self,
        run: JobRun,
        started_monotonic: float,
        *,
        error_code: str,
        error_message: str,
    ) -> JobRun:
        run.status = JobStatus.FAILED
        run.finished_at = datetime.now(UTC)
        run.duration_ms = max(0, int((monotonic() - started_monotonic) * 1000))
        run.error_code = error_code[:80]
        run.error_message = error_message[:500]
        await self._session.flush()
        return run

    async def list_recent(self, limit: int = 20) -> list[JobRun]:
        result = await self._session.execute(
            select(JobRun).order_by(desc(JobRun.started_at)).limit(max(1, min(limit, 100)))
        )
        return list(result.scalars())
