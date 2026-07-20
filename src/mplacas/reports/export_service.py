"""ReportExportService — enqueue and query async export tasks."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.reports.db_models import ReportExportTask

_VALID_FORMATS = frozenset({"pdf", "xlsx"})


class InvalidExportFormat(ValueError):
    pass


class ReportExportService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(
        self,
        *,
        plant_id: uuid.UUID,
        reference_month: str,
        format: str,
    ) -> ReportExportTask:
        if format not in _VALID_FORMATS:
            raise InvalidExportFormat(
                f"format must be one of {sorted(_VALID_FORMATS)}, got {format!r}"
            )
        task = ReportExportTask(
            plant_id=plant_id,
            reference_month=reference_month,
            format=format,
            status="pending",
        )
        self._session.add(task)
        await self._session.flush()
        return task

    async def get(self, task_id: uuid.UUID) -> ReportExportTask | None:
        return await self._session.get(ReportExportTask, task_id)

    async def claim(self, task_id: uuid.UUID) -> bool:
        """Transition pending → processing. Returns True if claim succeeded."""
        stmt = (
            select(ReportExportTask)
            .where(
                ReportExportTask.id == task_id,
                ReportExportTask.status == "pending",
            )
            .with_for_update(skip_locked=True)
        )
        task = await self._session.scalar(stmt)
        if task is None:
            return False
        task.status = "processing"
        task.claimed_at = datetime.now(UTC)
        return True

    async def mark_completed(
        self,
        task_id: uuid.UUID,
        *,
        artifact_bytes: bytes | None,
        artifact_content_type: str,
        artifact_url: str | None,
    ) -> None:
        task = await self._session.get(ReportExportTask, task_id)
        if task is None:
            raise ValueError(f"export task {task_id} not found")
        task.status = "completed"
        task.artifact_bytes = artifact_bytes
        task.artifact_content_type = artifact_content_type
        task.artifact_url = artifact_url
        task.completed_at = datetime.now(UTC)

    async def mark_failed(self, task_id: uuid.UUID, *, error_message: str) -> None:
        task = await self._session.get(ReportExportTask, task_id)
        if task is None:
            raise ValueError(f"export task {task_id} not found")
        task.status = "failed"
        task.error_message = error_message
        task.completed_at = datetime.now(UTC)

    async def pending_ids(self, *, limit: int = 10) -> list[uuid.UUID]:
        """Return IDs of pending tasks, oldest first."""
        result = await self._session.execute(
            select(ReportExportTask.id)
            .where(ReportExportTask.status == "pending")
            .order_by(ReportExportTask.created_at)
            .limit(limit)
        )
        return list(result.scalars())
