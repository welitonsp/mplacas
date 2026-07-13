from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.orchestration.db_models import PipelineExecutionStatus
from mplacas.orchestration.execution_repository import (
    PipelineExecutionAlreadyRunningError,
    PipelineExecutionRepository,
)


@pytest.mark.asyncio
async def test_execution_lock_prevents_duplicate_running_pipeline() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Synthetic plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        repository = PipelineExecutionRepository(session)
        execution = await repository.acquire(plant_id=plant.id, target_date=date(2026, 7, 13))

        assert execution.status is PipelineExecutionStatus.RUNNING
        assert execution.attempt_count == 1
        with pytest.raises(PipelineExecutionAlreadyRunningError, match="already running"):
            await repository.acquire(plant_id=plant.id, target_date=date(2026, 7, 13))

    await engine.dispose()


@pytest.mark.asyncio
async def test_failed_execution_can_be_retried_and_completed() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Synthetic plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        repository = PipelineExecutionRepository(session)
        execution = await repository.acquire(plant_id=plant.id, target_date=date(2026, 7, 13))
        await repository.mark_stage(execution, "climate")
        await repository.fail(execution, error_code="provider_unavailable")

        assert execution.status is PipelineExecutionStatus.FAILED
        assert execution.error_code == "PROVIDER_UNAVAILABLE"

        retry = await repository.acquire(plant_id=plant.id, target_date=date(2026, 7, 13))
        assert retry.id == execution.id
        assert retry.attempt_count == 2
        assert retry.status is PipelineExecutionStatus.RUNNING
        await repository.succeed(retry)
        assert retry.status is PipelineExecutionStatus.SUCCEEDED
        assert retry.finished_at is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_stale_running_execution_is_recovered_after_timeout() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    first_start = datetime(2026, 7, 13, 8, 0, tzinfo=UTC)
    retry_time = first_start + timedelta(minutes=61)
    async with factory() as session:
        plant = Plant(name="Synthetic plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        repository = PipelineExecutionRepository(session)
        execution = await repository.acquire(
            plant_id=plant.id,
            target_date=date(2026, 7, 13),
            now=first_start,
        )
        retry = await repository.acquire(
            plant_id=plant.id,
            target_date=date(2026, 7, 13),
            stale_after=timedelta(minutes=60),
            now=retry_time,
        )

        assert retry.id == execution.id
        assert retry.status is PipelineExecutionStatus.RUNNING
        assert retry.attempt_count == 2
        assert retry.started_at == retry_time
        assert retry.error_code is None

    await engine.dispose()
