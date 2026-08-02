from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.alerts.db_models import AlertDeliveryRecord
from mplacas.auth.db_models import AuthSessionRecord, LoginRateLimitRecord
from mplacas.collection.db_models import CollectionTaskRecord, CollectionTaskStatus
from mplacas.db import models as _db_models  # noqa: F401  (registra tabelas base)
from mplacas.db.base import Base
from mplacas.events.db_models import OutboxEventRecord, OutboxEventStatus
from mplacas.operations.models import JobRun, JobStatus
from mplacas.orchestration.db_models import (
    PipelineExecutionRecord,
    PipelineExecutionStatus,
)
from mplacas.retention.service import RetentionService, RetentionWindows
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.organizations.invitation_db_models import UserInvitationRecord
from mplacas.credentials.db_models import OperationalUserRecord

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
PLANT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000ee")
_TEST_ENGINES = []


@pytest.fixture(autouse=True)
async def _dispose_test_engines():
    yield
    while _TEST_ENGINES:
        await _TEST_ENGINES.pop().dispose()


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _TEST_ENGINES.append(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_plant(session) -> None:
    from mplacas.db.models import Plant

    await session.execute(
        insert(Plant).values(id=PLANT_ID, name="Usina Ret", timezone="America/Sao_Paulo")
    )


async def _count(session, model) -> int:
    return await session.scalar(select(func.count()).select_from(model))


def _old() -> datetime:
    return NOW - timedelta(days=400)


def _recent() -> datetime:
    return NOW - timedelta(days=5)


@pytest.mark.asyncio
async def test_retention_deletes_only_terminal_and_old_job_runs() -> None:
    factory = await _factory()
    async with factory() as session:
        await session.execute(
            insert(JobRun).values(
                id=uuid.uuid4(),
                job_name="collect",
                status=JobStatus.SUCCEEDED,
                started_at=_old(),
                finished_at=_old(),
            )
        )
        await session.execute(
            insert(JobRun).values(
                id=uuid.uuid4(),
                job_name="collect",
                status=JobStatus.RUNNING,  # terminal? não -> preserva mesmo sendo antigo
                started_at=_old(),
            )
        )
        await session.execute(
            insert(JobRun).values(
                id=uuid.uuid4(),
                job_name="collect",
                status=JobStatus.SUCCEEDED,
                started_at=_recent(),  # terminal mas recente -> preserva
                finished_at=_recent(),
            )
        )
        await session.commit()

    async with factory() as session:
        report = await RetentionService(session).purge(now=NOW)
        await session.commit()

    async with factory() as session:
        remaining = await _count(session, JobRun)
    assert remaining == 2  # apagou só o terminal-e-antigo
    job_outcome = next(o for o in report.outcomes if o.table == "job_runs")
    assert job_outcome.deleted == 1


@pytest.mark.asyncio
async def test_retention_preserves_running_pipeline_and_pending_tasks() -> None:
    factory = await _factory()
    async with factory() as session:
        await _seed_plant(session)
        await session.execute(
            insert(PipelineExecutionRecord).values(
                id=uuid.uuid4(),
                plant_id=PLANT_ID,
                target_date=NOW.date(),
                status=PipelineExecutionStatus.RUNNING,
                attempt_count=1,
                started_at=_old(),
            )
        )
        await session.execute(
            insert(CollectionTaskRecord).values(
                id=uuid.uuid4(),
                plant_id=PLANT_ID,
                task_type="solar_daily",
                target_date="2025-01-01",
                deduplication_key="k-old-pending",
                status=CollectionTaskStatus.PENDING,  # não terminal
                attempt_count=0,
                available_at=_old(),
                created_at=_old(),
            )
        )
        await session.execute(
            insert(CollectionTaskRecord).values(
                id=uuid.uuid4(),
                plant_id=PLANT_ID,
                task_type="solar_daily",
                target_date="2025-01-02",
                deduplication_key="k-old-completed",
                status=CollectionTaskStatus.COMPLETED,  # terminal e antigo -> apaga
                attempt_count=1,
                available_at=_old(),
                created_at=_old(),
            )
        )
        await session.commit()

    async with factory() as session:
        await RetentionService(session).purge(now=NOW)
        await session.commit()

    async with factory() as session:
        assert await _count(session, PipelineExecutionRecord) == 1  # RUNNING preservado
        tasks = (await session.scalars(select(CollectionTaskRecord))).all()
    assert len(tasks) == 1
    assert tasks[0].status is CollectionTaskStatus.PENDING


@pytest.mark.asyncio
async def test_retention_alert_ledger_uses_conservative_window() -> None:
    factory = await _factory()
    async with factory() as session:
        # dentro de 365 dias -> preserva (evita reenvio de alerta ainda relevante)
        await session.execute(
            insert(AlertDeliveryRecord).values(
                id=uuid.uuid4(),
                fingerprint="fp-recent",
                provider="telegram",
                destination_ref="dest",
                sent_at=NOW - timedelta(days=200),
            )
        )
        # além de 365 dias -> apaga
        await session.execute(
            insert(AlertDeliveryRecord).values(
                id=uuid.uuid4(),
                fingerprint="fp-ancient",
                provider="telegram",
                destination_ref="dest",
                sent_at=NOW - timedelta(days=400),
            )
        )
        await session.commit()

    async with factory() as session:
        await RetentionService(session).purge(now=NOW)
        await session.commit()

    async with factory() as session:
        remaining = (await session.scalars(select(AlertDeliveryRecord))).all()
    assert len(remaining) == 1
    assert remaining[0].fingerprint == "fp-recent"


@pytest.mark.asyncio
async def test_retention_outbox_respects_window_and_status() -> None:
    factory = await _factory()
    async with factory() as session:
        await _seed_plant(session)
        common = dict(
            plant_id=PLANT_ID,
            event_type="alert",
            aggregate_type="alert",
            aggregate_id="a1",
            destination_ref="dest",
            payload_json="{}",
            payload_sha256="0" * 64,
            attempt_count=0,
        )
        await session.execute(
            insert(OutboxEventRecord).values(
                id=uuid.uuid4(),
                deduplication_key="ev-old-delivered",
                status=OutboxEventStatus.DELIVERED,
                created_at=_old(),
                available_at=_old(),
                **common,
            )
        )
        await session.execute(
            insert(OutboxEventRecord).values(
                id=uuid.uuid4(),
                deduplication_key="ev-old-pending",
                status=OutboxEventStatus.PENDING,  # não terminal -> preserva
                created_at=_old(),
                available_at=_old(),
                **common,
            )
        )
        await session.commit()

    async with factory() as session:
        await RetentionService(session).purge(now=NOW)
        await session.commit()

    async with factory() as session:
        rows = (await session.scalars(select(OutboxEventRecord))).all()
    assert len(rows) == 1
    assert rows[0].status is OutboxEventStatus.PENDING


def test_retention_windows_validate_positive() -> None:
    with pytest.raises(ValueError, match="job_runs_days"):
        RetentionWindows(job_runs_days=0)
    with pytest.raises(ValueError, match="alert_delivery_records_days"):
        RetentionWindows(alert_delivery_records_days=-1)


@pytest.mark.asyncio
async def test_retention_purges_only_terminal_or_expired_authentication_data() -> None:
    factory = await _factory()
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()
    old_session_id = uuid.uuid4()
    valid_session_id = uuid.uuid4()
    async with factory() as session:
        session.add(
            OrganizationRecord(
                id=organization_id,
                name="Retention Auth",
                slug=f"retention-{organization_id.hex}",
                active=True,
            )
        )
        session.add(
            OperationalUserRecord(
                id=user_id,
                organization_id=organization_id,
                name=f"retention-{user_id.hex}",
                role="READ",
                active=True,
            )
        )
        await session.flush()
        session.add_all(
            [
                AuthSessionRecord(
                    id=old_session_id,
                    user_id=user_id,
                    organization_id=organization_id,
                    family_id=old_session_id,
                    refresh_token_hash="a" * 64,
                    active=False,
                    expires_at=_old(),
                    revoked_at=_old(),
                ),
                AuthSessionRecord(
                    id=valid_session_id,
                    user_id=user_id,
                    organization_id=organization_id,
                    family_id=valid_session_id,
                    refresh_token_hash="b" * 64,
                    active=True,
                    expires_at=NOW + timedelta(days=1),
                ),
                LoginRateLimitRecord(
                    key="old-unlocked",
                    attempt_count=1,
                    first_attempt_at=_old(),
                    locked_until=None,
                ),
                LoginRateLimitRecord(
                    key="active-lock",
                    attempt_count=10,
                    first_attempt_at=_old(),
                    locked_until=NOW + timedelta(hours=1),
                ),
                UserInvitationRecord(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    username="expired@example.invalid",
                    role="READ",
                    token_hash="c" * 64,
                    created_at=_old(),
                    expires_at=_old(),
                ),
                UserInvitationRecord(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    username="valid@example.invalid",
                    role="READ",
                    token_hash="d" * 64,
                    created_at=_recent(),
                    expires_at=NOW + timedelta(days=1),
                ),
            ]
        )
        await session.commit()

    async with factory() as session:
        first = await RetentionService(session).purge(now=NOW)
        await session.commit()
        second = await RetentionService(session).purge(now=NOW)
        await session.commit()

    deleted = {outcome.table: outcome.deleted for outcome in first.outcomes}
    assert deleted["auth_sessions"] == 1
    assert deleted["login_rate_limits"] == 1
    assert deleted["user_invitations"] == 1
    assert second.total_deleted == 0
    async with factory() as session:
        assert await _count(session, AuthSessionRecord) == 1
        assert await _count(session, LoginRateLimitRecord) == 1
        assert await _count(session, UserInvitationRecord) == 1
