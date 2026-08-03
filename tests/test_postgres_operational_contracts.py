from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import Response
from sqlalchemy import delete, inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import mplacas.main as main_module
from mplacas.collection.db_models import CollectionTaskRecord
from mplacas.collection.queue import CollectionQueueRepository
from mplacas.db.models import Plant
from mplacas.events.db_models import OutboxEventRecord
from mplacas.events.outbox import OutboxRepository
from mplacas.organizations.db_models import OrganizationRecord


@pytest.fixture
async def postgres_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_url = os.getenv("MPLACAS_TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("MPLACAS_TEST_POSTGRES_URL is not configured")
    engine = create_async_engine(database_url, pool_size=4, max_overflow=0)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _seed_plant(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID]:
    organization_id = uuid.uuid4()
    plant_id = uuid.uuid4()
    async with factory() as session:
        session.add(
            OrganizationRecord(
                id=organization_id,
                name="PostgreSQL Operational Contract",
                slug=f"postgres-contract-{organization_id.hex}",
                active=True,
            )
        )
        await session.flush()
        session.add(
            Plant(
                id=plant_id,
                organization_id=organization_id,
                name="PostgreSQL Lock Plant",
            )
        )
        await session.commit()
    return organization_id, plant_id


async def _cleanup(
    factory: async_sessionmaker[AsyncSession],
    *,
    organization_id: uuid.UUID,
    plant_id: uuid.UUID,
) -> None:
    async with factory() as session:
        await session.execute(
            delete(CollectionTaskRecord).where(CollectionTaskRecord.plant_id == plant_id)
        )
        await session.execute(
            delete(OutboxEventRecord).where(OutboxEventRecord.plant_id == plant_id)
        )
        await session.execute(delete(Plant).where(Plant.id == plant_id))
        await session.execute(
            delete(OrganizationRecord).where(OrganizationRecord.id == organization_id)
        )
        await session.commit()


@pytest.mark.postgres_integration
@pytest.mark.asyncio
async def test_collection_and_outbox_claims_skip_rows_locked_by_another_worker(
    postgres_factory: async_sessionmaker[AsyncSession],
) -> None:
    organization_id, plant_id = await _seed_plant(postgres_factory)
    try:
        async with postgres_factory() as session:
            collection = await CollectionQueueRepository(session).enqueue(
                plant_id=plant_id,
                task_type="POSTGRES_LOCK_TEST",
                target_date="2026-08-02",
            )
            outbox = await OutboxRepository(session).enqueue(
                plant_id=plant_id,
                event_type="POSTGRES_LOCK_TEST",
                aggregate_type="plant",
                aggregate_id=str(plant_id),
                destination_ref="integration:test",
                deduplication_key=f"postgres-lock:{plant_id}",
                payload={"plant_id": str(plant_id)},
            )
            await session.commit()

        async with postgres_factory() as first, postgres_factory() as second:
            first_claim = await CollectionQueueRepository(first).claim(collection.task.id)
            second_claim = await asyncio.wait_for(
                CollectionQueueRepository(second).claim(collection.task.id),
                timeout=2,
            )
            assert first_claim is not None
            assert second_claim is None
            await second.rollback()
            await first.rollback()

        async with postgres_factory() as first, postgres_factory() as second:
            first_claim = await OutboxRepository(first).claim(outbox.event.id)
            second_claim = await asyncio.wait_for(
                OutboxRepository(second).claim(outbox.event.id),
                timeout=2,
            )
            assert first_claim is not None
            assert second_claim is None
            await second.rollback()
            await first.rollback()
    finally:
        await _cleanup(
            postgres_factory,
            organization_id=organization_id,
            plant_id=plant_id,
        )


@pytest.mark.postgres_integration
@pytest.mark.asyncio
async def test_migrated_schema_serves_real_readiness_contract(
    postgres_factory: async_sessionmaker[AsyncSession],
    monkeypatch,
) -> None:
    async with postgres_factory() as session:
        connection = await session.connection()
        tables = await connection.run_sync(
            lambda sync_connection: set(inspect(sync_connection).get_table_names())
        )
        revision = await session.scalar(text("SELECT version_num FROM alembic_version"))

    assert revision == "20260802_0040"
    assert {
        "auth_sessions",
        "collection_tasks",
        "outbox_events",
        "daily_pv_performance_results",
        "seasonal_pv_baseline_results",
        "daily_pv_loss_assessments",
    }.issubset(tables)

    monkeypatch.setattr(main_module, "SessionFactory", postgres_factory)
    response = Response()
    payload = await main_module.ready(response)

    assert response.status_code == 200
    assert payload["status"] == "ready"
    assert payload["database_ready"] is True
