from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.db.base import Base
from mplacas.operations.models import JobRun, JobStatus
from mplacas.operations.service import JobOutcome, ObservableJobRunner


@pytest.mark.asyncio
async def test_observable_job_records_success_metrics() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        runner = ObservableJobRunner(session)

        async def operation() -> tuple[str, JobOutcome]:
            return "ok", JobOutcome(
                records_seen=7,
                records_changed=3,
                metrics={"devices": 2},
            )

        result = await runner.run("nep_daily_collection", operation)
        assert result == "ok"
        run = (await session.execute(select(JobRun))).scalar_one()
        assert run.status is JobStatus.SUCCEEDED
        assert run.records_seen == 7
        assert run.records_changed == 3
        assert run.metrics == {"devices": 2}
        assert run.finished_at is not None
        assert run.duration_ms is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_observable_job_records_sanitized_failure() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        runner = ObservableJobRunner(session)

        async def operation() -> tuple[None, JobOutcome]:
            raise RuntimeError("provider unavailable")

        with pytest.raises(RuntimeError, match="provider unavailable"):
            await runner.run("nep_daily_collection", operation)

        run = (await session.execute(select(JobRun))).scalar_one()
        assert run.status is JobStatus.FAILED
        assert run.error_code == "RuntimeError"
        assert run.error_message == "provider unavailable"
        assert run.finished_at is not None

    await engine.dispose()
