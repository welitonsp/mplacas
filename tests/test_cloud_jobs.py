from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.collection.job as job_module
from mplacas.cloud_jobs import CommandResult, main, run_migrations
from mplacas.collection.job import COLLECTION_TASK_TYPE
from mplacas.collection.queue import CollectionQueueRepository
from mplacas.core.config import get_settings
from mplacas.db import models as _db_models  # noqa: F401  (registra tabela plants)
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord
from mplacas.orchestration.db_models import PipelineExecutionStatus
from mplacas.providers.base import (
    DailyEnergy,
    DeviceOverview,
    ProviderUnavailableError,
    SolarDevice,
    SolarProvider,
)
import mplacas.cloud_jobs as cloud_jobs

_TEST_ENGINES = []


@pytest.fixture(autouse=True)
def _dispose_test_engines():
    yield
    while _TEST_ENGINES:
        cloud_jobs.asyncio.run(_TEST_ENGINES.pop().dispose())


class FakeSession:
    committed = False
    rolled_back = False

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def test_migrate_job_returns_zero(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_DATABASE_URL", "sqlite+aiosqlite:///./synthetic.db")
    get_settings.cache_clear()


def test_smoke_job_executes_read_only_database_probe(monkeypatch) -> None:
    statements: list[str] = []

    class SmokeSession(FakeSession):
        async def execute(self, statement) -> None:
            statements.append(str(statement))

    monkeypatch.setattr(cloud_jobs, "SessionFactory", SmokeSession)

    cloud_jobs.asyncio.run(cloud_jobs.run_smoke_check())

    assert statements == ["SELECT 1"]
    assert SmokeSession.committed is False
    calls: list[list[str]] = []

    def runner(args, env):
        calls.append(args)
        return CommandResult(returncode=0, stdout="", stderr="")

    assert run_migrations(runner=runner) == 0
    assert calls[0][-2:] == ["upgrade", "head"]
    get_settings.cache_clear()


def test_migrate_cli_returns_nonzero_on_failure(monkeypatch, capsys) -> None:
    monkeypatch.setenv("MPLACAS_DATABASE_URL", "postgresql://user:secret@db/mplacas")
    get_settings.cache_clear()

    def failing_runner(args, env):
        return CommandResult(
            returncode=1,
            stdout="",
            stderr="failed postgresql://user:secret@db/mplacas",
        )

    monkeypatch.setattr(cloud_jobs, "_run_command", failing_runner)

    assert main(["migrate"]) == 1
    captured = capsys.readouterr()
    assert "secret" not in captured.err
    assert "postgresql://" not in captured.err
    get_settings.cache_clear()


def test_daily_pipeline_uses_yesterday_in_configured_timezone(monkeypatch) -> None:
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000031")
    monkeypatch.setenv("MPLACAS_CLOUD_JOB_PLANT_NAME", "Usina Caldas")
    monkeypatch.setenv("MPLACAS_CLOUD_JOB_EXPECTED_DAILY_PRODUCTION_KWH", "12.5")
    monkeypatch.setenv("MPLACAS_TELEGRAM_BOT_TOKEN", "synthetic-token")
    monkeypatch.setenv("MPLACAS_TELEGRAM_ALERT_CHAT_ID", "synthetic-chat")
    get_settings.cache_clear()
    session = FakeSession()
    captured: dict[str, object] = {}

    async def fake_runtime(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    async def fake_resolve_plant_id(_name: str) -> uuid.UUID:
        return plant_id

    monkeypatch.setattr(cloud_jobs, "SessionFactory", lambda: session)
    monkeypatch.setattr(cloud_jobs, "run_ledger_backed_daily_pipeline", fake_runtime)
    monkeypatch.setattr(cloud_jobs, "_resolve_plant_id", fake_resolve_plant_id)

    now = datetime.fromisoformat("2026-07-13T00:30:00-03:00")
    cloud_jobs.asyncio.run(cloud_jobs.run_daily_pipeline(target_date=None, now=now))

    assert captured["plant_id"] == plant_id
    assert captured["target_date"].isoformat() == "2026-07-12"
    assert captured["expected_daily_production_kwh"] == Decimal("12.5")
    assert captured["outbox_max_attempts"] == 10
    assert session.committed is True
    get_settings.cache_clear()


def test_daily_pipeline_commits_failed_ledger_state(monkeypatch) -> None:
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000035")
    monkeypatch.setenv("MPLACAS_CLOUD_JOB_PLANT_NAME", "Usina Caldas")
    monkeypatch.setenv("MPLACAS_CLOUD_JOB_EXPECTED_DAILY_PRODUCTION_KWH", "12.5")
    monkeypatch.setenv("MPLACAS_TELEGRAM_BOT_TOKEN", "synthetic-token")
    monkeypatch.setenv("MPLACAS_TELEGRAM_ALERT_CHAT_ID", "synthetic-chat")
    get_settings.cache_clear()
    session = FakeSession()

    async def failing_runtime(*args, **kwargs):
        raise RuntimeError("pipeline failed after ledger update")

    async def fake_resolve_plant_id(_name: str) -> uuid.UUID:
        return plant_id

    monkeypatch.setattr(cloud_jobs, "SessionFactory", lambda: session)
    monkeypatch.setattr(cloud_jobs, "run_ledger_backed_daily_pipeline", failing_runtime)
    monkeypatch.setattr(cloud_jobs, "_resolve_plant_id", fake_resolve_plant_id)

    with pytest.raises(RuntimeError, match="pipeline failed"):
        cloud_jobs.asyncio.run(
            cloud_jobs.run_daily_pipeline(
                target_date="2026-07-15",
                now=datetime.fromisoformat("2026-07-16T00:30:00-03:00"),
            )
        )

    assert session.committed is True
    assert session.rolled_back is False
    get_settings.cache_clear()


def test_daily_pipeline_requires_plant_name(monkeypatch) -> None:
    monkeypatch.delenv("MPLACAS_CLOUD_JOB_PLANT_NAME", raising=False)
    monkeypatch.setenv("MPLACAS_CLOUD_JOB_EXPECTED_DAILY_PRODUCTION_KWH", "12.5")
    monkeypatch.setenv("MPLACAS_TELEGRAM_BOT_TOKEN", "synthetic-token")
    monkeypatch.setenv("MPLACAS_TELEGRAM_ALERT_CHAT_ID", "synthetic-chat")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="MPLACAS_CLOUD_JOB_PLANT_NAME"):
        cloud_jobs.asyncio.run(
            cloud_jobs.run_daily_pipeline(
                target_date="2026-07-15",
                now=datetime.fromisoformat("2026-07-16T00:30:00-03:00"),
            )
        )
    get_settings.cache_clear()


def test_daily_pipeline_help() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["daily-pipeline", "--help"])
    assert exc.value.code == 0


def test_operational_watchdog_accepts_fresh_success(monkeypatch) -> None:
    plant_id = uuid.uuid4()
    now = datetime(2026, 8, 2, 12, tzinfo=UTC)
    monkeypatch.setenv("MPLACAS_CLOUD_JOB_PLANT_NAME", "Usina Watchdog")
    get_settings.cache_clear()

    async def fake_resolve(_name: str) -> uuid.UUID:
        return plant_id

    async def fake_latest(*args, **kwargs):
        return SimpleNamespace(
            execution_id=uuid.uuid4(),
            status=PipelineExecutionStatus.SUCCEEDED,
            started_at=now - timedelta(hours=2),
            finished_at=now - timedelta(hours=1),
        )

    monkeypatch.setattr(cloud_jobs, "_find_plant_id", fake_resolve)
    monkeypatch.setattr(cloud_jobs, "get_latest_pipeline_execution", fake_latest)
    monkeypatch.setattr(cloud_jobs, "SessionFactory", lambda: FakeSession())

    cloud_jobs.asyncio.run(cloud_jobs.run_operational_watchdog(now=now))
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "snapshot,error",
    [
        (None, "no execution history"),
        (
            SimpleNamespace(
                execution_id=uuid.uuid4(),
                status=PipelineExecutionStatus.FAILED,
                started_at=datetime(2026, 8, 2, 8, tzinfo=UTC),
                finished_at=datetime(2026, 8, 2, 9, tzinfo=UTC),
            ),
            "execution failed",
        ),
        (
            SimpleNamespace(
                execution_id=uuid.uuid4(),
                status=PipelineExecutionStatus.RUNNING,
                started_at=datetime(2026, 8, 2, 10, tzinfo=UTC),
                finished_at=None,
            ),
            "execution is stuck",
        ),
        (
            SimpleNamespace(
                execution_id=uuid.uuid4(),
                status=PipelineExecutionStatus.SUCCEEDED,
                started_at=datetime(2026, 8, 1, 7, tzinfo=UTC),
                finished_at=datetime(2026, 8, 1, 8, tzinfo=UTC),
            ),
            "delayed beyond 26 hours",
        ),
    ],
)
def test_operational_watchdog_fails_closed(monkeypatch, snapshot, error: str) -> None:
    monkeypatch.setenv("MPLACAS_CLOUD_JOB_PLANT_NAME", "Usina Watchdog")
    get_settings.cache_clear()

    async def fake_resolve(_name: str) -> uuid.UUID:
        return uuid.uuid4()

    async def fake_latest(*args, **kwargs):
        return snapshot

    monkeypatch.setattr(cloud_jobs, "_find_plant_id", fake_resolve)
    monkeypatch.setattr(cloud_jobs, "get_latest_pipeline_execution", fake_latest)
    monkeypatch.setattr(cloud_jobs, "SessionFactory", lambda: FakeSession())

    with pytest.raises(RuntimeError, match=error):
        cloud_jobs.asyncio.run(
            cloud_jobs.run_operational_watchdog(
                now=datetime(2026, 8, 2, 12, tzinfo=UTC)
            )
        )
    get_settings.cache_clear()


def test_outbox_dispatch_uses_configured_retry_policy(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_TELEGRAM_BOT_TOKEN", "synthetic-token")
    monkeypatch.setenv("MPLACAS_TELEGRAM_ALERT_CHAT_ID", "synthetic-chat")
    monkeypatch.setenv("MPLACAS_OUTBOX_DISPATCH_BATCH_SIZE", "25")
    monkeypatch.setenv("MPLACAS_OUTBOX_MAX_ATTEMPTS", "7")
    monkeypatch.setenv("MPLACAS_OUTBOX_STALE_LOCK_TIMEOUT_MINUTES", "9")
    get_settings.cache_clear()
    captured: dict[str, object] = {}

    async def fake_dispatch(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(evaluated=2, sent=2, skipped=0, failed=0)

    monkeypatch.setattr(cloud_jobs, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(cloud_jobs, "dispatch_due_alert_outbox", fake_dispatch)

    summary = cloud_jobs.asyncio.run(cloud_jobs.run_outbox_dispatch())

    assert summary.sent == 2
    assert captured["limit"] == 25
    assert captured["max_attempts"] == 7
    assert captured["stale_after"].total_seconds() == 9 * 60
    assert captured["destination_ref"].startswith("telegram:")
    get_settings.cache_clear()


def test_outbox_dispatch_job_fails_when_delivery_is_rescheduled(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_TELEGRAM_BOT_TOKEN", "synthetic-token")
    monkeypatch.setenv("MPLACAS_TELEGRAM_ALERT_CHAT_ID", "synthetic-chat")
    get_settings.cache_clear()

    async def fake_dispatch(*args, **kwargs):
        return SimpleNamespace(evaluated=1, sent=0, skipped=0, failed=1)

    monkeypatch.setattr(cloud_jobs, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(cloud_jobs, "dispatch_due_alert_outbox", fake_dispatch)

    with pytest.raises(RuntimeError, match="outbox deliveries failed"):
        cloud_jobs.asyncio.run(cloud_jobs.run_outbox_dispatch())
    get_settings.cache_clear()


class _FailingSolarProvider(SolarProvider):
    """Simula uma NEPViewer indisponível na primeira coleta de usina nova."""

    async def list_devices(self) -> list[SolarDevice]:
        raise ProviderUnavailableError("nepviewer down")

    async def get_overview(self, serial_number: str) -> DeviceOverview:
        raise NotImplementedError

    async def get_daily_energy(
        self,
        serial_number: str,
        start: date,
        end: date,
        *,
        expect_complete: bool = False,
    ) -> list[DailyEnergy]:
        return []


async def _sqlite_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _TEST_ENGINES.append(engine)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_fk_pragma(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            OrganizationRecord(
                id=DEFAULT_ORGANIZATION_ID,
                name="Default",
                slug="default",
                active=True,
            )
        )
        await session.commit()
    return factory


def test_run_collection_does_not_require_plant_id_env_var(monkeypatch) -> None:
    """MPLACAS_CLOUD_JOB_PLANT_ID não é mais exigido: a usina é resolvida pelo nome."""
    monkeypatch.delenv("MPLACAS_CLOUD_JOB_PLANT_ID", raising=False)
    monkeypatch.setenv("MPLACAS_CLOUD_JOB_PLANT_NAME", "Usina Nova")
    monkeypatch.setenv("MPLACAS_NEP_ACCOUNT", "operador")
    monkeypatch.setenv("MPLACAS_NEP_PASSWORD", "segredo-de-ambiente")
    get_settings.cache_clear()

    factory = cloud_jobs.asyncio.run(_sqlite_factory())
    monkeypatch.setattr(cloud_jobs, "SessionFactory", factory)
    monkeypatch.setattr(job_module, "SessionFactory", factory)

    def fake_build(**_kwargs):
        class _NoopClient:
            async def aclose(self) -> None:
                return None

        return _NoopClient(), _FailingSolarProvider()

    monkeypatch.setattr(job_module, "build_resilient_nepviewer", fake_build)

    now = datetime.fromisoformat("2026-07-19T00:30:00-03:00")
    # Não deve levantar exceção alguma: nem por falta da env var, nem por FK
    # ao enfileirar o retry da primeira coleta de uma usina que ainda não existe.
    cloud_jobs.asyncio.run(cloud_jobs.run_collection(target_date="2026-07-18", now=now))

    get_settings.cache_clear()


def test_run_collection_creates_plant_before_enqueueing_first_retry(monkeypatch) -> None:
    """Reproduz o bug de produção: primeira coleta de usina nova cai no retry.

    Antes da correção, `_enqueue_retry` usava um `plant_id` arbitrário (vindo
    de env var) que nunca correspondia ao `Plant.id` real gerado ao criar a
    usina pelo nome, violando a FK de `collection_tasks.plant_id`. Agora a
    usina é resolvida/criada e commitada isoladamente antes de qualquer
    tentativa de coleta, e esse `id` real é o único usado dali em diante.
    """
    monkeypatch.delenv("MPLACAS_CLOUD_JOB_PLANT_ID", raising=False)
    monkeypatch.setenv("MPLACAS_CLOUD_JOB_PLANT_NAME", "Usina Nova")
    monkeypatch.setenv("MPLACAS_NEP_ACCOUNT", "operador")
    monkeypatch.setenv("MPLACAS_NEP_PASSWORD", "segredo-de-ambiente")
    get_settings.cache_clear()

    factory = cloud_jobs.asyncio.run(_sqlite_factory())
    monkeypatch.setattr(cloud_jobs, "SessionFactory", factory)
    monkeypatch.setattr(job_module, "SessionFactory", factory)

    def fake_build(**_kwargs):
        class _NoopClient:
            async def aclose(self) -> None:
                return None

        return _NoopClient(), _FailingSolarProvider()

    monkeypatch.setattr(job_module, "build_resilient_nepviewer", fake_build)

    now = datetime.fromisoformat("2026-07-19T00:30:00-03:00")
    cloud_jobs.asyncio.run(cloud_jobs.run_collection(target_date="2026-07-18", now=now))

    async def _assert_state() -> None:
        async with factory() as session:
            plant = (
                await session.execute(select(Plant).where(Plant.name == "Usina Nova"))
            ).scalar_one()
            due = await CollectionQueueRepository(session).due_ids(
                task_type=COLLECTION_TASK_TYPE
            )
            assert len(due) == 1
            task = await CollectionQueueRepository(session).by_id(due[0])
            assert task is not None
            assert task.plant_id == plant.id
            assert task.target_date == "2026-07-18"

    cloud_jobs.asyncio.run(_assert_state())
    get_settings.cache_clear()
