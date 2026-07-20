from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.collection.db_models import CollectionTaskStatus
from mplacas.collection.queue import (
    CollectionQueueRepository,
    CollectionTask,
    deduplication_key,
)
from mplacas.collection.worker import CollectionWorker
from mplacas.db.base import Base
from mplacas.db import models as _db_models  # noqa: F401  (registra tabela plants)

TASK_TYPE = "climate"
PLANT_A = uuid.UUID("00000000-0000-0000-0000-00000000000a")
PLANT_B = uuid.UUID("00000000-0000-0000-0000-00000000000b")


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_plant(session, plant_id: uuid.UUID) -> None:
    from mplacas.db.models import Plant

    await session.execute(
        insert(Plant).values(
            id=plant_id,
            name=f"Usina {plant_id}",
            timezone="America/Sao_Paulo",
        )
    )


@pytest.mark.asyncio
async def test_enqueue_is_idempotent_by_plant_type_and_date() -> None:
    factory = await _factory()
    async with factory() as session:
        await _seed_plant(session, PLANT_A)
        repository = CollectionQueueRepository(session)
        first = await repository.enqueue(
            plant_id=PLANT_A, task_type=TASK_TYPE, target_date="2026-07-19"
        )
        second = await repository.enqueue(
            plant_id=PLANT_A, task_type=TASK_TYPE, target_date="2026-07-19"
        )
        await session.commit()

    assert first.created is True
    assert second.created is False
    assert first.task.id == second.task.id
    assert first.task.deduplication_key == deduplication_key(
        plant_id=PLANT_A, task_type=TASK_TYPE, target_date="2026-07-19"
    )


@pytest.mark.asyncio
async def test_claim_is_exclusive_and_marks_processing() -> None:
    factory = await _factory()
    async with factory() as session:
        await _seed_plant(session, PLANT_A)
        repository = CollectionQueueRepository(session)
        enqueued = await repository.enqueue(
            plant_id=PLANT_A, task_type=TASK_TYPE, target_date="2026-07-19"
        )
        await session.commit()
        task_id = enqueued.task.id

    async with factory() as session:
        repository = CollectionQueueRepository(session)
        claimed = await repository.claim(task_id)
        assert claimed is not None
        assert claimed.status is CollectionTaskStatus.PROCESSING
        await session.commit()

    async with factory() as session:
        repository = CollectionQueueRepository(session)
        due = await repository.due_ids(task_type=TASK_TYPE)
        assert task_id not in due


@pytest.mark.asyncio
async def test_reschedule_applies_backoff_then_fails_after_max_attempts() -> None:
    factory = await _factory()
    async with factory() as session:
        await _seed_plant(session, PLANT_A)
        repository = CollectionQueueRepository(session)
        enqueued = await repository.enqueue(
            plant_id=PLANT_A, task_type=TASK_TYPE, target_date="2026-07-19"
        )
        await session.commit()
        task_id = enqueued.task.id

    base = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    async with factory() as session:
        repository = CollectionQueueRepository(session)
        status = await repository.reschedule(
            task_id, error_code="timeout", now=base, max_attempts=3
        )
        await session.commit()
    assert status is CollectionTaskStatus.PENDING

    async with factory() as session:
        task = await CollectionQueueRepository(session).by_id(task_id)
        assert task is not None
        # SQLite devolve datetime naive; normaliza para comparar o backoff.
        scheduled = task.available_at
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=UTC)
        assert scheduled > base

    async with factory() as session:
        repository = CollectionQueueRepository(session)
        await repository.reschedule(task_id, error_code="timeout", now=base, max_attempts=3)
        final = await repository.reschedule(
            task_id, error_code="timeout", now=base, max_attempts=3
        )
        await session.commit()
    assert final is CollectionTaskStatus.FAILED


@pytest.mark.asyncio
async def test_worker_isolates_failures_between_tasks() -> None:
    factory = await _factory()
    async with factory() as session:
        await _seed_plant(session, PLANT_A)
        await _seed_plant(session, PLANT_B)
        repository = CollectionQueueRepository(session)
        await repository.enqueue(
            plant_id=PLANT_A, task_type=TASK_TYPE, target_date="2026-07-19"
        )
        await repository.enqueue(
            plant_id=PLANT_B, task_type=TASK_TYPE, target_date="2026-07-19"
        )
        await session.commit()

    async def handler(session, task: CollectionTask) -> None:
        if task.plant_id == PLANT_B:
            raise RuntimeError("provider unavailable for plant B")

    worker = CollectionWorker(
        factory,
        task_type=TASK_TYPE,
        handler=handler,
        max_attempts=3,
    )
    result = await worker.run_once()

    assert result.claimed == 2
    assert result.completed == 1
    assert result.rescheduled == 1
    assert result.failed == 0

    async with factory() as session:
        repository = CollectionQueueRepository(session)
        due = await repository.due_ids(task_type=TASK_TYPE)
    # a usina A concluiu; a usina B foi reagendada para o futuro (nao esta due)
    assert due == ()


@pytest.mark.asyncio
async def test_worker_completes_all_healthy_tasks() -> None:
    factory = await _factory()
    processed: list[uuid.UUID] = []
    async with factory() as session:
        for plant_id in (PLANT_A, PLANT_B):
            await _seed_plant(session, plant_id)
            await CollectionQueueRepository(session).enqueue(
                plant_id=plant_id, task_type=TASK_TYPE, target_date="2026-07-19"
            )
        await session.commit()

    async def handler(session, task: CollectionTask) -> None:
        processed.append(task.plant_id)

    worker = CollectionWorker(factory, task_type=TASK_TYPE, handler=handler)
    result = await worker.run_once()

    assert result.completed == 2
    assert set(processed) == {PLANT_A, PLANT_B}


@pytest.mark.asyncio
async def test_stale_processing_task_is_reclaimable() -> None:
    factory = await _factory()
    async with factory() as session:
        await _seed_plant(session, PLANT_A)
        enqueued = await CollectionQueueRepository(session).enqueue(
            plant_id=PLANT_A, task_type=TASK_TYPE, target_date="2026-07-19"
        )
        await session.commit()
        task_id = enqueued.task.id

    from mplacas.collection.db_models import CollectionTaskRecord

    async with factory() as session:
        repository = CollectionQueueRepository(session)
        await repository.claim(task_id)
        record = await session.get(CollectionTaskRecord, task_id)
        assert record is not None
        record.locked_at = datetime.now(UTC) - timedelta(minutes=20)
        await session.commit()

    async with factory() as session:
        repository = CollectionQueueRepository(session)
        due = await repository.due_ids(
            task_type=TASK_TYPE, stale_after=timedelta(minutes=15)
        )
        assert task_id in due
        reclaimed = await repository.claim(
            task_id, stale_after=timedelta(minutes=15)
        )
        assert reclaimed is not None
