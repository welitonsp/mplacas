from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.collection.db_models import CollectionTaskStatus
from mplacas.collection.queue import CollectionQueueRepository, CollectionTask
from mplacas.observability.operations import observe_operation

logger = logging.getLogger(__name__)

TaskHandler = Callable[[AsyncSession, CollectionTask], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class WorkerResult:
    claimed: int
    completed: int
    rescheduled: int
    failed: int


class CollectionWorker:
    """Consome tarefas de coleta de um tipo, isolando a falha de cada uma.

    Uma tarefa que falha é reagendada com backoff (ou marcada como falha após
    o máximo de tentativas) sem impedir o processamento das demais. Cada tarefa
    roda em sua própria transação: o commit de uma não é desfeito pela falha
    de outra.
    """

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        *,
        task_type: str,
        handler: TaskHandler,
        max_attempts: int = 10,
    ) -> None:
        self._session_factory = session_factory
        self._task_type = task_type
        self._handler = handler
        self._max_attempts = max_attempts

    async def run_once(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
    ) -> WorkerResult:
        async with self._session_factory() as session:
            due_ids = await CollectionQueueRepository(session).due_ids(
                task_type=self._task_type,
                now=now,
                limit=limit,
            )

        claimed = 0
        completed = 0
        rescheduled = 0
        failed = 0
        for task_id in due_ids:
            outcome = await self._process_one(task_id, now=now)
            if outcome is None:
                continue
            claimed += 1
            if outcome is CollectionTaskStatus.COMPLETED:
                completed += 1
            elif outcome is CollectionTaskStatus.FAILED:
                failed += 1
            else:
                rescheduled += 1
        return WorkerResult(
            claimed=claimed,
            completed=completed,
            rescheduled=rescheduled,
            failed=failed,
        )

    async def _process_one(
        self,
        task_id: uuid.UUID,
        *,
        now: datetime | None,
    ) -> CollectionTaskStatus | None:
        async with self._session_factory() as session:
            repository = CollectionQueueRepository(session)
            task = await repository.claim(task_id, now=now)
            if task is None:
                await session.rollback()
                return None
            failure: Exception | None = None
            try:
                with observe_operation(
                    logger,
                    f"collection_worker.{self._task_type}",
                    plant_id=str(task.plant_id),
                    target_date=task.target_date,
                ):
                    await self._handler(session, task)
                await repository.mark_completed(task_id, now=now)
                await session.commit()
                return CollectionTaskStatus.COMPLETED
            except Exception as exc:  # noqa: BLE001 - isola falha por tarefa
                failure = exc
                await session.rollback()
        return await self._reschedule(task_id, exc=failure, now=now)

    async def _reschedule(
        self,
        task_id: uuid.UUID,
        *,
        exc: Exception | None,
        now: datetime | None,
    ) -> CollectionTaskStatus:
        error_code = type(exc).__name__ if exc is not None else "UnknownError"
        async with self._session_factory() as session:
            repository = CollectionQueueRepository(session)
            status = await repository.reschedule(
                task_id,
                error_code=error_code,
                now=now,
                max_attempts=self._max_attempts,
            )
            await session.commit()
        logger.warning(
            "collection_task_reschedule",
            extra={
                "task_id": str(task_id),
                "task_type": self._task_type,
                "error_code": error_code,
                "status": status.value,
            },
        )
        return status
