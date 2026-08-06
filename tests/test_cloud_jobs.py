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


def _fake_expected_production_resolver(by_plant: dict[uuid.UUID, Decimal | None]):
    """Build a ``resolve_expected_daily_production`` double keyed by plant.

    ``None`` for a plant means "unavailable" (the plant is skipped).
    """

    async def _resolve(_session, *, plant_id, today=None):
        value = by_plant[plant_id]
        if value is None:
            return SimpleNamespace(
                expected=None,
                unavailable_reason="NO_PERFORMANCE_HISTORY",
                reference_complete_on=None,
            )
        return SimpleNamespace(
            expected=SimpleNamespace(expected_daily_production_kwh=value),
            unavailable_reason=None,
            reference_complete_on=None,
        )

    return _resolve


def _set_daily_pipeline_env(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_TELEGRAM_BOT_TOKEN", "synthetic-token")
    monkeypatch.setenv("MPLACAS_TELEGRAM_ALERT_CHAT_ID", "synthetic-chat")
    get_settings.cache_clear()


def test_daily_pipeline_uses_yesterday_in_configured_timezone(monkeypatch) -> None:
    """Single-plant organization: unchanged behaviour (regression)."""
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000031")
    _set_daily_pipeline_env(monkeypatch)
    session = FakeSession()
    captured: dict[str, object] = {}

    async def fake_runtime(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    async def fake_list_plants(_organization_id):
        return [(plant_id, "Usina Caldas")]

    monkeypatch.setattr(cloud_jobs, "SessionFactory", lambda: session)
    monkeypatch.setattr(cloud_jobs, "run_ledger_backed_daily_pipeline", fake_runtime)
    monkeypatch.setattr(cloud_jobs, "_list_organization_plants", fake_list_plants)
    monkeypatch.setattr(
        cloud_jobs,
        "resolve_expected_daily_production",
        _fake_expected_production_resolver({plant_id: Decimal("12.5")}),
    )

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
    _set_daily_pipeline_env(monkeypatch)
    session = FakeSession()

    async def failing_runtime(*args, **kwargs):
        raise RuntimeError("pipeline failed after ledger update")

    async def fake_list_plants(_organization_id):
        return [(plant_id, "Usina Caldas")]

    monkeypatch.setattr(cloud_jobs, "SessionFactory", lambda: session)
    monkeypatch.setattr(cloud_jobs, "run_ledger_backed_daily_pipeline", failing_runtime)
    monkeypatch.setattr(cloud_jobs, "_list_organization_plants", fake_list_plants)
    monkeypatch.setattr(
        cloud_jobs,
        "resolve_expected_daily_production",
        _fake_expected_production_resolver({plant_id: Decimal("12.5")}),
    )

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


def test_daily_pipeline_requires_plants_in_organization(monkeypatch) -> None:
    _set_daily_pipeline_env(monkeypatch)

    async def fake_list_plants(_organization_id):
        return []

    monkeypatch.setattr(cloud_jobs, "_list_organization_plants", fake_list_plants)

    with pytest.raises(RuntimeError, match="no plants found"):
        cloud_jobs.asyncio.run(
            cloud_jobs.run_daily_pipeline(
                target_date="2026-07-15",
                now=datetime.fromisoformat("2026-07-16T00:30:00-03:00"),
            )
        )
    get_settings.cache_clear()


def test_daily_pipeline_runs_all_plants_and_survives_one_failure(monkeypatch) -> None:
    """ADR-069 § E9: 2-plant org, one fails, the other still runs; non-zero exit."""
    plant_a = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
    plant_b = uuid.UUID("00000000-0000-0000-0000-0000000000b2")
    _set_daily_pipeline_env(monkeypatch)

    calls: list[dict[str, object]] = []

    async def fake_runtime(*args, **kwargs):
        calls.append(kwargs)
        if kwargs["plant_id"] == plant_a:
            raise RuntimeError("provider unavailable for plant A")
        return SimpleNamespace()

    async def fake_list_plants(_organization_id):
        return [(plant_a, "Usina A"), (plant_b, "Usina B")]

    monkeypatch.setattr(cloud_jobs, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(cloud_jobs, "run_ledger_backed_daily_pipeline", fake_runtime)
    monkeypatch.setattr(cloud_jobs, "_list_organization_plants", fake_list_plants)
    monkeypatch.setattr(
        cloud_jobs,
        "resolve_expected_daily_production",
        # Distinct values per plant: proves there is no single env-derived
        # value shared across plants.
        _fake_expected_production_resolver(
            {plant_a: Decimal("10.0"), plant_b: Decimal("25.0")}
        ),
    )

    with pytest.raises(RuntimeError, match="Usina A"):
        cloud_jobs.asyncio.run(
            cloud_jobs.run_daily_pipeline(
                target_date="2026-07-15",
                now=datetime.fromisoformat("2026-07-16T00:30:00-03:00"),
            )
        )

    # Both plants were attempted, in deterministic order, each with its own
    # resolved expectation -- the failure of plant A did not skip plant B.
    assert len(calls) == 2
    assert calls[0]["plant_id"] == plant_a
    assert calls[0]["expected_daily_production_kwh"] == Decimal("10.0")
    assert calls[1]["plant_id"] == plant_b
    assert calls[1]["expected_daily_production_kwh"] == Decimal("25.0")
    get_settings.cache_clear()


def test_daily_pipeline_runs_plant_without_derivable_expectation_but_skips_alerts(
    monkeypatch,
) -> None:
    """ADR-069 § E9 correction.

    A plant with no derivable expectation (e.g. no seasonal baseline yet)
    must NOT be skipped entirely -- that would create a permanent deadlock:
    no baseline -> no expectation -> plant skipped -> performance/baseline
    step never runs -> no baseline forever. The plant must still go through
    ``run_ledger_backed_daily_pipeline`` (which runs climate/POA,
    performance and seasonal baseline); only alert dispatch is expected to
    be suppressed downstream (inside the pipeline runtime itself) via
    ``expected_daily_production_kwh=None``.
    """
    plant_a = uuid.UUID("00000000-0000-0000-0000-0000000000c3")
    plant_b = uuid.UUID("00000000-0000-0000-0000-0000000000d4")
    _set_daily_pipeline_env(monkeypatch)

    calls: list[dict[str, object]] = []

    async def fake_runtime(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace()

    async def fake_list_plants(_organization_id):
        return [(plant_a, "Usina Sem Historico"), (plant_b, "Usina Com Historico")]

    monkeypatch.setattr(cloud_jobs, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(cloud_jobs, "run_ledger_backed_daily_pipeline", fake_runtime)
    monkeypatch.setattr(cloud_jobs, "_list_organization_plants", fake_list_plants)
    monkeypatch.setattr(
        cloud_jobs,
        "resolve_expected_daily_production",
        _fake_expected_production_resolver({plant_a: None, plant_b: Decimal("9.0")}),
    )

    # No derivable expectation is not a failure: no exception, and both
    # plants are attempted -- the pipeline still runs for plant A.
    cloud_jobs.asyncio.run(
        cloud_jobs.run_daily_pipeline(
            target_date="2026-07-15",
            now=datetime.fromisoformat("2026-07-16T00:30:00-03:00"),
        )
    )

    assert len(calls) == 2
    assert calls[0]["plant_id"] == plant_a
    assert calls[0]["expected_daily_production_kwh"] is None
    assert calls[1]["plant_id"] == plant_b
    assert calls[1]["expected_daily_production_kwh"] == Decimal("9.0")
    get_settings.cache_clear()


def test_daily_pipeline_help() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["daily-pipeline", "--help"])
    assert exc.value.code == 0


def test_operational_watchdog_accepts_fresh_success(monkeypatch) -> None:
    """Single-plant organization: unchanged behaviour (regression)."""
    plant_id = uuid.uuid4()
    now = datetime(2026, 8, 2, 12, tzinfo=UTC)

    async def fake_list_plants(_organization_id):
        return [(plant_id, "Usina Watchdog")]

    async def fake_latest(*args, **kwargs):
        return SimpleNamespace(
            execution_id=uuid.uuid4(),
            status=PipelineExecutionStatus.SUCCEEDED,
            started_at=now - timedelta(hours=2),
            finished_at=now - timedelta(hours=1),
        )

    monkeypatch.setattr(cloud_jobs, "_list_organization_plants", fake_list_plants)
    monkeypatch.setattr(cloud_jobs, "get_latest_pipeline_execution", fake_latest)
    monkeypatch.setattr(cloud_jobs, "SessionFactory", lambda: FakeSession())

    cloud_jobs.asyncio.run(cloud_jobs.run_operational_watchdog(now=now))
    get_settings.cache_clear()


def test_operational_watchdog_requires_plants_in_organization(monkeypatch) -> None:
    async def fake_list_plants(_organization_id):
        return []

    monkeypatch.setattr(cloud_jobs, "_list_organization_plants", fake_list_plants)

    with pytest.raises(RuntimeError, match="no plants found"):
        cloud_jobs.asyncio.run(
            cloud_jobs.run_operational_watchdog(now=datetime(2026, 8, 2, 12, tzinfo=UTC))
        )
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
    plant_id = uuid.uuid4()

    async def fake_list_plants(_organization_id):
        return [(plant_id, "Usina Watchdog")]

    async def fake_latest(*args, **kwargs):
        return snapshot

    monkeypatch.setattr(cloud_jobs, "_list_organization_plants", fake_list_plants)
    monkeypatch.setattr(cloud_jobs, "get_latest_pipeline_execution", fake_latest)
    monkeypatch.setattr(cloud_jobs, "SessionFactory", lambda: FakeSession())

    with pytest.raises(RuntimeError, match=error):
        cloud_jobs.asyncio.run(
            cloud_jobs.run_operational_watchdog(
                now=datetime(2026, 8, 2, 12, tzinfo=UTC)
            )
        )
    get_settings.cache_clear()


def test_operational_watchdog_checks_all_plants_and_fails_non_zero(monkeypatch) -> None:
    """ADR-069 § E9: 2-plant org, one unhealthy plant does not skip the other."""
    plant_healthy = uuid.UUID("00000000-0000-0000-0000-0000000000e5")
    plant_unhealthy = uuid.UUID("00000000-0000-0000-0000-0000000000f6")
    now = datetime(2026, 8, 2, 12, tzinfo=UTC)

    async def fake_list_plants(_organization_id):
        return [(plant_healthy, "Usina Saudavel"), (plant_unhealthy, "Usina Doente")]

    checked: list[uuid.UUID] = []

    async def fake_latest(_session, *, plant_id):
        checked.append(plant_id)
        if plant_id == plant_unhealthy:
            return SimpleNamespace(
                execution_id=uuid.uuid4(),
                status=PipelineExecutionStatus.FAILED,
                started_at=now - timedelta(hours=2),
                finished_at=now - timedelta(hours=1),
            )
        return SimpleNamespace(
            execution_id=uuid.uuid4(),
            status=PipelineExecutionStatus.SUCCEEDED,
            started_at=now - timedelta(hours=2),
            finished_at=now - timedelta(hours=1),
        )

    monkeypatch.setattr(cloud_jobs, "_list_organization_plants", fake_list_plants)
    monkeypatch.setattr(cloud_jobs, "get_latest_pipeline_execution", fake_latest)
    monkeypatch.setattr(cloud_jobs, "SessionFactory", lambda: FakeSession())

    with pytest.raises(RuntimeError, match="Usina Doente"):
        cloud_jobs.asyncio.run(cloud_jobs.run_operational_watchdog(now=now))

    # Both plants were checked; the unhealthy one did not stop the loop.
    assert set(checked) == {plant_healthy, plant_unhealthy}
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


def test_list_organization_plants_orders_by_name_then_id(monkeypatch) -> None:
    """ADR-069 § E9: the fan-out plant listing used by daily-pipeline/watchdog."""
    factory = cloud_jobs.asyncio.run(_sqlite_factory())
    monkeypatch.setattr(cloud_jobs, "SessionFactory", factory)

    low_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    high_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    other_org_id = uuid.uuid4()

    async def _seed() -> None:
        async with factory() as session:
            session.add(
                OrganizationRecord(
                    id=other_org_id, name="Other", slug="other-org", active=True
                )
            )
            await session.flush()
            session.add(Plant(id=high_id, organization_id=DEFAULT_ORGANIZATION_ID, name="Zulu"))
            session.add(Plant(id=low_id, organization_id=DEFAULT_ORGANIZATION_ID, name="Alpha"))
            session.add(
                Plant(id=uuid.uuid4(), organization_id=other_org_id, name="Not In Default Org")
            )
            await session.commit()

    cloud_jobs.asyncio.run(_seed())

    plants = cloud_jobs.asyncio.run(
        cloud_jobs._list_organization_plants(DEFAULT_ORGANIZATION_ID)
    )

    assert plants == [(low_id, "Alpha"), (high_id, "Zulu")]


def test_daily_pipeline_cli_exits_non_zero_on_partial_failure(monkeypatch) -> None:
    """The Cloud Scheduler / Cloud Run Job needs a non-zero exit to alert on."""

    async def failing_run(**_kwargs):
        raise RuntimeError("daily pipeline failed for plant(s): Usina B (...)")

    monkeypatch.setattr(cloud_jobs, "run_daily_pipeline", failing_run)

    assert main(["daily-pipeline"]) == 1
