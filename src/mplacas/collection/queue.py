from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.collection.db_models import CollectionTaskRecord, CollectionTaskStatus

_MAX_BACKOFF_SECONDS = 3600


@dataclass(frozen=True, slots=True)
class CollectionTask:
    id: uuid.UUID
    plant_id: uuid.UUID
    task_type: str
    target_date: str
    deduplication_key: str
    status: CollectionTaskStatus
    attempt_count: int
    available_at: datetime


@dataclass(frozen=True, slots=True)
class EnqueuedCollectionTask:
    task: CollectionTask
    created: bool


def deduplication_key(*, plant_id: uuid.UUID, task_type: str, target_date: str) -> str:
    return f"{task_type}:{plant_id}:{target_date}"


def _to_task(record: CollectionTaskRecord) -> CollectionTask:
    return CollectionTask(
        id=record.id,
        plant_id=record.plant_id,
        task_type=record.task_type,
        target_date=record.target_date,
        deduplication_key=record.deduplication_key,
        status=record.status,
        attempt_count=record.attempt_count,
        available_at=record.available_at,
    )


def _claimable(*, current_time: datetime, stale_before: datetime):
    return or_(
        and_(
            CollectionTaskRecord.status == CollectionTaskStatus.PENDING,
            CollectionTaskRecord.available_at <= current_time,
        ),
        and_(
            CollectionTaskRecord.status == CollectionTaskStatus.PROCESSING,
            CollectionTaskRecord.locked_at <= stale_before,
        ),
    )


def _required(value: str, label: str, maximum_length: int) -> str:
    cleaned = value.strip()
    if not cleaned or len(cleaned) > maximum_length:
        raise ValueError(f"invalid collection task {label}")
    return cleaned


class CollectionQueueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(
        self,
        *,
        plant_id: uuid.UUID,
        task_type: str,
        target_date: str,
    ) -> EnqueuedCollectionTask:
        task_type = _required(task_type, "type", 80)
        target_date = _required(target_date, "target date", 10)
        key = deduplication_key(
            plant_id=plant_id,
            task_type=task_type,
            target_date=target_date,
        )
        existing = await self._by_key(key)
        if existing is not None:
            return EnqueuedCollectionTask(task=existing, created=False)

        record_id = uuid.uuid4()
        values = {
            "id": record_id,
            "plant_id": plant_id,
            "task_type": task_type,
            "target_date": target_date,
            "deduplication_key": key,
            "status": CollectionTaskStatus.PENDING,
            "attempt_count": 0,
        }
        dialect = self._session.sync_session.get_bind().dialect.name
        if dialect == "postgresql":
            statement = (
                postgresql_insert(CollectionTaskRecord)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["deduplication_key"])
                .returning(CollectionTaskRecord.id)
            )
        elif dialect == "sqlite":
            statement = (
                sqlite_insert(CollectionTaskRecord)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["deduplication_key"])
                .returning(CollectionTaskRecord.id)
            )
        else:
            raise RuntimeError("collection queue requires PostgreSQL or SQLite")
        inserted_id = await self._session.scalar(statement)
        if inserted_id is None:
            concurrent = await self._by_key(key)
            if concurrent is None:
                raise RuntimeError("collection conflict did not resolve to an existing task")
            return EnqueuedCollectionTask(task=concurrent, created=False)
        record = await self._session.get(CollectionTaskRecord, inserted_id)
        if record is None:
            raise RuntimeError("inserted collection task could not be loaded")
        return EnqueuedCollectionTask(task=_to_task(record), created=True)

    async def due_ids(
        self,
        *,
        task_type: str,
        now: datetime | None = None,
        stale_after: timedelta = timedelta(minutes=15),
        limit: int = 100,
    ) -> tuple[uuid.UUID, ...]:
        if limit < 1 or limit > 1000:
            raise ValueError("collection batch limit must be between 1 and 1000")
        current_time = now or datetime.now(UTC)
        stale_before = current_time - stale_after
        rows = await self._session.scalars(
            select(CollectionTaskRecord.id)
            .where(
                CollectionTaskRecord.task_type == task_type,
                _claimable(current_time=current_time, stale_before=stale_before),
            )
            .order_by(CollectionTaskRecord.created_at, CollectionTaskRecord.id)
            .limit(limit)
        )
        return tuple(rows)

    async def claim(
        self,
        task_id: uuid.UUID,
        *,
        now: datetime | None = None,
        stale_after: timedelta = timedelta(minutes=15),
    ) -> CollectionTask | None:
        current_time = now or datetime.now(UTC)
        record = await self._session.scalar(
            select(CollectionTaskRecord)
            .where(
                CollectionTaskRecord.id == task_id,
                _claimable(
                    current_time=current_time,
                    stale_before=current_time - stale_after,
                ),
            )
            .with_for_update(skip_locked=True)
        )
        if record is None:
            return None
        record.status = CollectionTaskStatus.PROCESSING
        record.locked_at = current_time
        record.last_error_code = None
        await self._session.flush()
        return _to_task(record)

    async def mark_completed(
        self,
        task_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> None:
        record = await self._required_record(task_id)
        record.status = CollectionTaskStatus.COMPLETED
        record.processed_at = now or datetime.now(UTC)
        record.locked_at = None
        record.last_error_code = None
        await self._session.flush()

    async def reschedule(
        self,
        task_id: uuid.UUID,
        *,
        error_code: str,
        now: datetime | None = None,
        max_attempts: int = 10,
    ) -> CollectionTaskStatus:
        if max_attempts < 1:
            raise ValueError("collection max attempts must be positive")
        current_time = now or datetime.now(UTC)
        record = await self._required_record(task_id)
        record.attempt_count += 1
        record.locked_at = None
        record.last_error_code = _required(error_code.upper(), "error code", 80)
        if record.attempt_count >= max_attempts:
            record.status = CollectionTaskStatus.FAILED
            record.processed_at = current_time
        else:
            delay_seconds = min(
                _MAX_BACKOFF_SECONDS,
                60 * (2 ** (record.attempt_count - 1)),
            )
            record.status = CollectionTaskStatus.PENDING
            record.available_at = current_time + timedelta(seconds=delay_seconds)
        await self._session.flush()
        return record.status

    async def by_id(self, task_id: uuid.UUID) -> CollectionTask | None:
        record = await self._session.get(CollectionTaskRecord, task_id)
        return _to_task(record) if record is not None else None

    async def _by_key(self, key: str) -> CollectionTask | None:
        record = await self._session.scalar(
            select(CollectionTaskRecord).where(
                CollectionTaskRecord.deduplication_key == key
            )
        )
        return _to_task(record) if record is not None else None

    async def _required_record(self, task_id: uuid.UUID) -> CollectionTaskRecord:
        record = await self._session.get(CollectionTaskRecord, task_id)
        if record is None:
            raise LookupError("collection task not found")
        return record
