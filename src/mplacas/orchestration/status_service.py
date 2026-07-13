from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.orchestration.db_models import PipelineExecutionRecord, PipelineExecutionStatus


@dataclass(frozen=True, slots=True)
class PipelineExecutionSnapshot:
    execution_id: uuid.UUID
    plant_id: uuid.UUID
    target_date: date
    status: PipelineExecutionStatus
    attempt_count: int
    stage: str
    error_code: str | None
    started_at: datetime
    finished_at: datetime | None


async def get_latest_pipeline_execution(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
) -> PipelineExecutionSnapshot | None:
    record = await session.scalar(
        select(PipelineExecutionRecord)
        .where(PipelineExecutionRecord.plant_id == plant_id)
        .order_by(desc(PipelineExecutionRecord.target_date), desc(PipelineExecutionRecord.started_at))
        .limit(1)
    )
    if record is None:
        return None
    return PipelineExecutionSnapshot(
        execution_id=record.id,
        plant_id=record.plant_id,
        target_date=record.target_date,
        status=record.status,
        attempt_count=record.attempt_count,
        stage=record.stage,
        error_code=record.error_code,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )
