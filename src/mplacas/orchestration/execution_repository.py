from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.orchestration.db_models import PipelineExecutionRecord, PipelineExecutionStatus


class PipelineExecutionAlreadyRunningError(RuntimeError):
    """A pipeline execution already owns the plant/date lock."""


class PipelineExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def acquire(self, *, plant_id: uuid.UUID, target_date: date) -> PipelineExecutionRecord:
        existing = await self._session.scalar(
            select(PipelineExecutionRecord).where(
                PipelineExecutionRecord.plant_id == plant_id,
                PipelineExecutionRecord.target_date == target_date,
            )
        )
        if existing is not None:
            if existing.status is PipelineExecutionStatus.RUNNING:
                raise PipelineExecutionAlreadyRunningError("pipeline execution already running")
            existing.status = PipelineExecutionStatus.RUNNING
            existing.attempt_count += 1
            existing.stage = "STARTED"
            existing.error_code = None
            existing.started_at = datetime.now(UTC)
            existing.finished_at = None
            await self._session.flush()
            return existing

        record = PipelineExecutionRecord(plant_id=plant_id, target_date=target_date)
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
