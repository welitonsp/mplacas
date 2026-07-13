from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.orchestration.db_models import PipelineExecutionRecord, PipelineExecutionStatus


class PipelineExecutionAlreadyRunningError(RuntimeError):
    """A pipeline execution already owns the plant/date lock."""


class PipelineExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def acquire(
        self,
        *,
        plant_id: uuid.UUID,
        target_date: date,
        stale_after: timedelta | None = None,
        now: datetime | None = None,
    ) -> PipelineExecutionRecord:
        current_time = now or datetime.now(UTC)
        existing = await self._session.scalar(
            select(PipelineExecutionRecord).where(
                PipelineExecutionRecord.plant_id == plant_id,
                PipelineExecutionRecord.target_date == target_date,
            )
        )
        if existing is not None:
            if existing.status is PipelineExecutionStatus.RUNNING:
                started_at = existing.started_at
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=UTC)
                is_stale = stale_after is not None and current_time - started_at >= stale_after
                if not is_stale:
                    raise PipelineExecutionAlreadyRunningError("pipeline execution already running")
                existing.status = PipelineExecutionStatus.FAILED
                existing.stage = "STALE_LOCK_RECOVERED"
                existing.error_code = "STALE_LOCK_TIMEOUT"
                existing.finished_at = current_time
                await self._session.flush()

            existing.status = PipelineExecutionStatus.RUNNING
            existing.attempt_count += 1
            existing.stage = "STARTED"
            existing.error_code = None
            existing.started_at = current_time
            existing.finished_at = None
            await self._session.flush()
            return existing

        record = PipelineExecutionRecord(
            plant_id=plant_id,
            target_date=target_date,
            started_at=current_time,
        )
        self._session.add(record)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise PipelineExecutionAlreadyRunningError("pipeline execution lock conflict") from exc
        return record

    async def mark_stage(self, record: PipelineExecutionRecord, stage: str) -> None:
        cleaned = stage.strip().upper()
        if not cleaned or len(cleaned) > 40:
            raise ValueError("invalid pipeline execution stage")
        record.stage = cleaned
        await self._session.flush()

    async def succeed(self, record: PipelineExecutionRecord) -> None:
        record.status = PipelineExecutionStatus.SUCCEEDED
        record.stage = "COMPLETED"
        record.error_code = None
        record.finished_at = datetime.now(UTC)
        await self._session.flush()

    async def fail(self, record: PipelineExecutionRecord, *, error_code: str) -> None:
        cleaned = error_code.strip().upper()
        if not cleaned or len(cleaned) > 80:
            raise ValueError("invalid pipeline execution error code")
        record.status = PipelineExecutionStatus.FAILED
        record.error_code = cleaned
        record.finished_at = datetime.now(UTC)
        await self._session.flush()
