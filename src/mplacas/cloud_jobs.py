from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
import subprocess
import sys
import uuid
from urllib.parse import urlsplit, urlunsplit
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from mplacas.alerts.job import AlertJobSummary
from mplacas.alerts.models import AlertSeverity
from mplacas.alerts.outbox import dispatch_due_alert_outbox
from mplacas.alerts.telegram import TelegramAlertProvider
from mplacas.climate.open_meteo import OpenMeteoHistoricalProvider
from mplacas.collection.drain import drain_collection_queue
from mplacas.reports.drain import drain_report_exports
from mplacas.collection.job import run_solar_collection
from mplacas.core.config import get_settings
from mplacas.db.models import Plant
from mplacas.db.repositories.plant import PlantRepository
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID
from mplacas.db.session import SessionFactory
from mplacas.db.session import engine as database_engine
from mplacas.db.tenant_context import set_platform_context
from mplacas.retention.service import RetentionService, RetentionWindows
from mplacas.retention.timeseries_service import (
    TimeSeriesRetentionService,
    TimeSeriesRetentionWindows,
)
from mplacas.reports.daily_digest import send_daily_digest
from mplacas.observability.context import (
    bind_correlation_context,
    new_correlation_context,
)
from mplacas.observability.tracing import configure_observability, traced_operation
from opentelemetry.trace import Status, StatusCode
from mplacas.orchestration.runtime import run_ledger_backed_daily_pipeline
from mplacas.orchestration.db_models import PipelineExecutionStatus
from mplacas.orchestration.status_service import get_latest_pipeline_execution
from mplacas.photovoltaic.read_service import resolve_expected_daily_production

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[list[str], Mapping[str, str]], CommandResult]


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    observability = None
    correlation = new_correlation_context(request_id=f"job-{uuid.uuid4().hex}")
    with bind_correlation_context(correlation):
        try:
            settings = get_settings()
            observability = configure_observability(
                settings=settings,
                service_name=f"mplacas-job-{args.command}",
                engine=database_engine,
            )
            with traced_operation("cloud_job", command=args.command) as span:
                try:
                    return int(args.handler(args))
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                    logger.error(
                        "cloud_job_failed",
                        extra={
                            "command": args.command,
                            "error_code": type(exc).__name__,
                        },
                    )
                    print(f"error: {_sanitize(str(exc), '')}", file=sys.stderr)
                    return 1
        except Exception as exc:
            logger.error("cloud_job_bootstrap_failed", extra={"error_code": type(exc).__name__})
            print(f"error: {_sanitize(str(exc), '')}", file=sys.stderr)
            return 1
        finally:
            if observability is not None:
                observability.shutdown()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mplacas.cloud_jobs",
        description="Run Mplacas operational jobs without starting FastAPI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    migrate = subparsers.add_parser("migrate", help="run Alembic migrations")
    migrate.set_defaults(handler=_handle_migrate)

    smoke = subparsers.add_parser(
        "smoke",
        help="validate production configuration and database connectivity without mutations",
    )
    smoke.set_defaults(handler=_handle_smoke)

    daily = subparsers.add_parser("daily-pipeline", help="run the daily operational pipeline")
    daily.add_argument("--target-date", default=None, help="YYYY-MM-DD; defaults to yesterday")
    daily.set_defaults(handler=_handle_daily_pipeline)

    outbox = subparsers.add_parser(
        "dispatch-outbox",
        help="deliver due transactional outbox events",
    )
    outbox.set_defaults(handler=_handle_outbox_dispatch)

    collect = subparsers.add_parser(
        "collect",
        help="collect daily solar production from NEPViewer",
    )
    collect.add_argument("--target-date", default=None, help="YYYY-MM-DD; defaults to yesterday")
    collect.set_defaults(handler=_handle_collect)

    drain = subparsers.add_parser(
        "drain-collection",
        help="reprocess deferred solar collection tasks",
    )
    drain.set_defaults(handler=_handle_drain_collection)

    drain_exports = subparsers.add_parser(
        "drain-report-exports",
        help="process pending async report export tasks",
    )
    drain_exports.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="number of tasks to process per run (default: 10)",
    )
    drain_exports.set_defaults(handler=_handle_drain_report_exports)

    retention = subparsers.add_parser(
        "retention",
        help="purge terminal operational records past their retention window",
    )
    retention.set_defaults(handler=_handle_retention)

    digest = subparsers.add_parser(
        "daily-digest",
        help="build and send the informational daily production digest",
    )
    digest.add_argument("--target-date", default=None, help="YYYY-MM-DD; defaults to yesterday")
    digest.set_defaults(handler=_handle_daily_digest)

    watchdog = subparsers.add_parser(
        "operational-watchdog",
        help="fail when the daily pipeline ledger is absent, delayed, stuck or failed",
    )
    watchdog.set_defaults(handler=_handle_operational_watchdog)
    return parser


def _handle_migrate(_args: argparse.Namespace) -> int:
    return run_migrations()


def _handle_smoke(_args: argparse.Namespace) -> int:
    asyncio.run(run_smoke_check())
    return 0


def _handle_daily_pipeline(args: argparse.Namespace) -> int:
    target_date = args.target_date
    asyncio.run(run_daily_pipeline(target_date=target_date))
    return 0


def _handle_outbox_dispatch(_args: argparse.Namespace) -> int:
    asyncio.run(run_outbox_dispatch())
    return 0


def _handle_collect(args: argparse.Namespace) -> int:
    asyncio.run(run_collection(target_date=args.target_date))
    return 0


def _handle_drain_collection(_args: argparse.Namespace) -> int:
    asyncio.run(run_collection_drain())
    return 0


def _handle_drain_report_exports(args: argparse.Namespace) -> int:
    asyncio.run(run_report_export_drain(batch_size=args.batch_size))
    return 0


def _handle_retention(_args: argparse.Namespace) -> int:
    asyncio.run(run_retention())
    return 0


def _handle_daily_digest(args: argparse.Namespace) -> int:
    asyncio.run(run_daily_digest(target_date=args.target_date))
    return 0


def _handle_operational_watchdog(_args: argparse.Namespace) -> int:
    asyncio.run(run_operational_watchdog())
    return 0


async def run_operational_watchdog(*, now: datetime | None = None) -> None:
    """Fail closed when the daily pipeline heartbeat is unhealthy, for every plant.

    ADR-069 § E9: iterates every plant of ``DEFAULT_ORGANIZATION_ID`` instead
    of the single plant named by ``MPLACAS_CLOUD_JOB_PLANT_NAME``. One plant
    being unhealthy does not skip the health check of the others; the job
    still fails closed (non-zero exit) if any plant is unhealthy, after every
    plant has been checked.
    """
    current_time = now or datetime.now(UTC)
    plants = await _list_organization_plants(DEFAULT_ORGANIZATION_ID)
    if not plants:
        raise RuntimeError("no plants found for the default organization")

    problems: list[str] = []
    for plant_id, plant_name in plants:
        try:
            await _check_plant_pipeline_health(
                plant_id=plant_id, current_time=current_time
            )
        except RuntimeError as exc:
            logger.error(
                "cloud_job_operational_watchdog_plant_unhealthy",
                extra={
                    "plant_id": str(plant_id),
                    "plant_name": plant_name,
                    "error_code": type(exc).__name__,
                },
            )
            problems.append(f"{plant_name} ({plant_id}): {exc}")

    if problems:
        raise RuntimeError(
            "operational watchdog found unhealthy plant(s): " + "; ".join(problems)
        )


async def _check_plant_pipeline_health(
    *, plant_id: uuid.UUID, current_time: datetime
) -> None:
    async with SessionFactory() as session:
        await set_platform_context(session)
        latest = await get_latest_pipeline_execution(session, plant_id=plant_id)
    if latest is None:
        raise RuntimeError("daily pipeline has no execution history")
    if latest.status == PipelineExecutionStatus.FAILED:
        raise RuntimeError("latest daily pipeline execution failed")
    if latest.status == PipelineExecutionStatus.RUNNING:
        started_at = latest.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        if current_time - started_at > timedelta(minutes=30):
            raise RuntimeError("latest daily pipeline execution is stuck")
        logger.info(
            "cloud_job_operational_watchdog_running_pipeline",
            extra={"plant_id": str(plant_id), "execution_id": str(latest.execution_id)},
        )
        return
    finished_at = latest.finished_at
    if finished_at is None:
        raise RuntimeError("successful daily pipeline execution has no finish timestamp")
    if finished_at.tzinfo is None:
        finished_at = finished_at.replace(tzinfo=UTC)
    age = current_time - finished_at
    if age > timedelta(hours=26):
        raise RuntimeError("latest daily pipeline execution is delayed beyond 26 hours")
    logger.info(
        "cloud_job_operational_watchdog_healthy",
        extra={
            "plant_id": str(plant_id),
            "execution_id": str(latest.execution_id),
            "pipeline_age_seconds": max(0, int(age.total_seconds())),
        },
    )


async def run_collection(
    *,
    target_date: str | None,
    now: datetime | None = None,
) -> None:
    """Collect daily solar production from the single configured NEPViewer account.

    Deliberately **not** fanned out across the organization's plants (ADR-069
    § E9 scoped the fan-out to ``run_daily_pipeline`` and
    ``run_operational_watchdog``, which only read data already attributed to
    a plant in the database). Collection is different: ``list_devices()``
    returns the flat device list of one external NEPViewer account
    (``MPLACAS_NEP_ACCOUNT``/``MPLACAS_NEP_PASSWORD``, both singular settings
    with no per-plant credential), with no field distinguishing which
    physical plant a device belongs to (see ``providers.base.SolarDevice``).
    Looping this over every plant of the organization would not collect N
    independent telemetry streams -- it would write the same single
    account's devices and daily energy into every plant row once per
    iteration, corrupting production data for any plant that is not the one
    this account actually measures. ``MPLACAS_CLOUD_JOB_PLANT_NAME`` keeps
    naming that one physical plant, exactly as before.
    """
    settings = get_settings()
    plant_name = settings.cloud_job_plant_name
    if plant_name is None or not plant_name.strip():
        raise RuntimeError("MPLACAS_CLOUD_JOB_PLANT_NAME is required")
    plant_id = await _resolve_plant_id(plant_name)
    resolved_date = _resolve_target_date(
        target_date=target_date,
        timezone_name=settings.timezone,
        now=now,
    )
    logger.info(
        "cloud_job_collection_started",
        extra={"plant_id": str(plant_id), "target_date": resolved_date.isoformat()},
    )
    await run_solar_collection(
        target_date=resolved_date,
        plant_id=plant_id,
        plant_name=plant_name,
    )
    logger.info(
        "cloud_job_collection_completed",
        extra={"plant_id": str(plant_id), "target_date": resolved_date.isoformat()},
    )


async def run_retention() -> None:
    settings = get_settings()
    windows = RetentionWindows(
        job_runs_days=settings.retention_job_runs_days,
        pipeline_executions_days=settings.retention_pipeline_executions_days,
        outbox_events_days=settings.retention_outbox_events_days,
        collection_tasks_days=settings.retention_collection_tasks_days,
        alert_delivery_records_days=settings.retention_alert_delivery_records_days,
        auth_sessions_days=settings.retention_auth_sessions_days,
        login_rate_limits_days=settings.retention_login_rate_limits_days,
        user_invitations_days=settings.retention_user_invitations_days,
    )
    ts_windows = TimeSeriesRetentionWindows(
        daily_energy_days=settings.retention_daily_energy_days,
        climate_observations_days=settings.retention_climate_observations_days,
    )
    logger.info("cloud_job_retention_started")
    async with SessionFactory() as session:
        await set_platform_context(session)
        report = await RetentionService(session).purge(windows=windows)
        energy_deleted, climate_deleted = await TimeSeriesRetentionService(session).purge(
            windows=ts_windows
        )
        await session.commit()
    logger.info(
        "cloud_job_retention_completed",
        extra={
            "total_deleted": report.total_deleted + energy_deleted + climate_deleted,
            "by_table": {
                **{o.table: o.deleted for o in report.outcomes},
                "daily_energy": energy_deleted,
                "daily_climate_observations": climate_deleted,
            },
        },
    )


async def run_smoke_check() -> None:
    """Fail fast when a deployed job cannot reach the configured database."""

    async with SessionFactory() as session:
        await set_platform_context(session)
        await session.execute(text("SELECT 1"))
    logger.info("cloud_job_smoke_completed")


async def run_report_export_drain(*, batch_size: int = 10) -> None:
    logger.info("cloud_job_report_export_drain_started")
    result = await drain_report_exports(batch_size=batch_size)
    logger.info(
        "cloud_job_report_export_drain_completed",
        extra={
            "claimed": result.claimed,
            "completed": result.completed,
            "failed": result.failed,
        },
    )
    if result.failed:
        raise RuntimeError(f"{result.failed} report export task(s) failed")


async def run_collection_drain() -> None:
    settings = get_settings()
    plant_name = settings.cloud_job_plant_name
    if plant_name is None or not plant_name.strip():
        raise RuntimeError("MPLACAS_CLOUD_JOB_PLANT_NAME is required")
    logger.info("cloud_job_collection_drain_started")
    result = await drain_collection_queue(plant_name=plant_name)
    logger.info(
        "cloud_job_collection_drain_completed",
        extra={
            "claimed": result.claimed,
            "completed": result.completed,
            "rescheduled": result.rescheduled,
            "failed": result.failed,
        },
    )


def run_migrations(
    *,
    runner: CommandRunner | None = None,
) -> int:
    settings = get_settings()
    command_runner = runner or _run_command
    logger.info("cloud_job_migration_started")
    result = command_runner(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        {"MPLACAS_DATABASE_URL": settings.database_url},
    )
    if result.returncode != 0:
        message = _sanitize(result.stderr.strip() or "migration failed", settings.database_url)
        logger.error("cloud_job_migration_failed", extra={"returncode": result.returncode})
        raise RuntimeError(message)
    logger.info("cloud_job_migration_completed")
    return 0


async def run_daily_pipeline(
    *,
    target_date: str | None,
    now: datetime | None = None,
) -> None:
    """Run the ledger-backed daily pipeline for every plant of the default org.

    ADR-069 § E9: no longer resolves a single plant from
    ``MPLACAS_CLOUD_JOB_PLANT_NAME``; iterates every plant belonging to
    ``DEFAULT_ORGANIZATION_ID`` instead, sequentially, one new session (and
    one commit/rollback boundary) per plant -- same discipline as the § E.11.4
    HTTP fan-out. A failure on one plant is logged and does not stop the
    others; the job exits non-zero at the end if any plant failed.

    ``MPLACAS_CLOUD_JOB_EXPECTED_DAILY_PRODUCTION_KWH`` is no longer read
    here: a single environment value cannot describe N differently-sized
    plants (ADR-068/ADR-069 § E.11.1 achado C). Each plant resolves its own
    expectation via ``resolve_expected_daily_production``.

    A plant without a derivable expectation is **not** skipped outright: the
    climate/POA collection, performance calculation and seasonal baseline
    steps still run for it (this is precisely how the baseline accumulates
    the history it needs to eventually exist). Only the alert dispatch step
    -- which requires the expectation to score anomaly severity -- is
    skipped for that plant; ``run_daily_energy_pipeline`` handles this
    itself when ``expected_daily_production_kwh`` is ``None``. Skipping the
    whole plant here would create a permanent deadlock for any plant that
    has never had a baseline: no baseline -> no expectation -> plant
    skipped -> performance/baseline step never runs -> no baseline forever
    (ADR-069 § E9 correction).
    """
    settings = get_settings()
    token = settings.telegram_bot_token
    chat_id = settings.telegram_alert_chat_id
    if token is None or not chat_id:
        raise RuntimeError("Telegram alert delivery must be configured for daily pipeline")

    resolved_date = _resolve_target_date(
        target_date=target_date,
        timezone_name=settings.timezone,
        now=now,
    )
    climate_provider = OpenMeteoHistoricalProvider(
        base_url=str(settings.climate_archive_base_url),
        timeout_seconds=settings.request_timeout_seconds,
    )
    alert_provider = TelegramAlertProvider(
        bot_token=token.get_secret_value(),
        chat_id=chat_id,
        timeout_seconds=settings.request_timeout_seconds,
    )

    plants = await _list_organization_plants(DEFAULT_ORGANIZATION_ID)
    if not plants:
        raise RuntimeError("no plants found for the default organization")

    failures: list[str] = []
    for plant_id, plant_name in plants:
        logger.info(
            "cloud_job_daily_pipeline_started",
            extra={
                "plant_id": str(plant_id),
                "plant_name": plant_name,
                "target_date": resolved_date.isoformat(),
            },
        )
        try:
            async with SessionFactory() as session:
                await set_platform_context(session)
                try:
                    resolution = await resolve_expected_daily_production(
                        session, plant_id=plant_id, today=resolved_date
                    )
                    expected_daily_production_kwh: Decimal | None
                    if resolution.expected is None:
                        # Do not skip the plant: only alert dispatch depends
                        # on the expectation. Climate/POA, performance and
                        # seasonal baseline must still run so the baseline
                        # can eventually form -- see docstring above.
                        expected_daily_production_kwh = None
                        logger.warning(
                            "cloud_job_daily_pipeline_alerts_skipped",
                            extra={
                                "plant_id": str(plant_id),
                                "plant_name": plant_name,
                                "reason": resolution.unavailable_reason,
                            },
                        )
                    else:
                        expected_daily_production_kwh = (
                            resolution.expected.expected_daily_production_kwh
                        )
                    await run_ledger_backed_daily_pipeline(
                        session,
                        plant_id=plant_id,
                        target_date=resolved_date,
                        climate_provider=climate_provider,
                        alert_provider=alert_provider,
                        alert_destination_ref=_destination_ref(chat_id),
                        expected_daily_production_kwh=expected_daily_production_kwh,
                        expected_cycle_production_kwh=(
                            settings.cloud_job_expected_cycle_production_kwh
                        ),
                        anomaly_days=settings.cloud_job_anomaly_days,
                        minimum_severity=AlertSeverity.WARNING,
                        stale_lock_timeout_minutes=(
                            settings.pipeline_stale_lock_timeout_minutes
                        ),
                        outbox_max_attempts=settings.outbox_max_attempts,
                    )
                    await session.commit()
                except Exception:
                    # Commit even on failure: the runtime may have already
                    # persisted a FAILED ledger row before raising, and that
                    # state must survive so the watchdog observes it.
                    await session.commit()
                    raise
            logger.info(
                "cloud_job_daily_pipeline_completed",
                extra={
                    "plant_id": str(plant_id),
                    "plant_name": plant_name,
                    "target_date": resolved_date.isoformat(),
                },
            )
        except Exception as exc:
            logger.error(
                "cloud_job_daily_pipeline_plant_failed",
                extra={
                    "plant_id": str(plant_id),
                    "plant_name": plant_name,
                    "target_date": resolved_date.isoformat(),
                    "error_code": type(exc).__name__,
                },
            )
            failures.append(f"{plant_name} ({plant_id}): {exc}")

    if failures:
        raise RuntimeError(
            "daily pipeline failed for plant(s): " + "; ".join(failures)
        )


async def run_daily_digest(
    *,
    target_date: str | None,
    now: datetime | None = None,
) -> None:
    settings = get_settings()
    plant_name = settings.cloud_job_plant_name
    if plant_name is None or not plant_name.strip():
        raise RuntimeError("MPLACAS_CLOUD_JOB_PLANT_NAME is required")
    plant_id = await _resolve_plant_id(plant_name)
    expected_daily = _required_decimal(
        settings.cloud_job_expected_daily_production_kwh,
        "MPLACAS_CLOUD_JOB_EXPECTED_DAILY_PRODUCTION_KWH",
    )
    token = settings.telegram_bot_token
    chat_id = settings.telegram_alert_chat_id
    if token is None or not chat_id:
        raise RuntimeError("Telegram alert delivery must be configured for daily digest")

    resolved_date = _resolve_target_date(
        target_date=target_date,
        timezone_name=settings.timezone,
        now=now,
    )
    provider = TelegramAlertProvider(
        bot_token=token.get_secret_value(),
        chat_id=chat_id,
        timeout_seconds=settings.request_timeout_seconds,
    )

    logger.info(
        "cloud_job_daily_digest_started",
        extra={"plant_id": str(plant_id), "target_date": resolved_date.isoformat()},
    )
    async with SessionFactory() as session:
        await set_platform_context(session)
        sent = await send_daily_digest(
            session,
            plant_id=plant_id,
            target_date=resolved_date,
            expected_daily_production_kwh=expected_daily,
            provider=provider,
        )
    logger.info(
        "cloud_job_daily_digest_completed",
        extra={
            "plant_id": str(plant_id),
            "target_date": resolved_date.isoformat(),
            "sent": sent,
        },
    )


async def run_outbox_dispatch() -> AlertJobSummary:
    settings = get_settings()
    token = settings.telegram_bot_token
    chat_id = settings.telegram_alert_chat_id
    if token is None or not chat_id:
        raise RuntimeError("Telegram alert delivery must be configured for outbox dispatch")
    provider = TelegramAlertProvider(
        bot_token=token.get_secret_value(),
        chat_id=chat_id,
        timeout_seconds=settings.request_timeout_seconds,
    )
    async with SessionFactory() as session:
        await set_platform_context(session)
        summary = await dispatch_due_alert_outbox(
            session,
            provider=provider,
            destination_ref=_destination_ref(chat_id),
            limit=settings.outbox_dispatch_batch_size,
            max_attempts=settings.outbox_max_attempts,
            stale_after=timedelta(minutes=settings.outbox_stale_lock_timeout_minutes),
        )
    logger.info(
        "cloud_job_outbox_dispatch_completed",
        extra={
            "evaluated": summary.evaluated,
            "sent": summary.sent,
            "skipped": summary.skipped,
            "failed": summary.failed,
        },
    )
    if summary.failed:
        raise RuntimeError("one or more outbox deliveries failed")
    return summary


def _resolve_target_date(
    *,
    target_date: str | None,
    timezone_name: str,
    now: datetime | None = None,
) -> date:
    if target_date is not None:
        return datetime.strptime(target_date, "%Y-%m-%d").date()
    timezone = ZoneInfo(timezone_name)
    current = now.astimezone(timezone) if now is not None else datetime.now(timezone)
    return (current - timedelta(days=1)).date()


async def _resolve_plant_id(plant_name: str) -> uuid.UUID:
    """Resolve o `Plant.id` real a partir do nome, criando a usina se necessário.

    Roda numa transação curta e isolada, com commit imediato, de forma que o
    `id` resultante já esteja persistido (e visível a outras transações) antes
    de ser usado para qualquer operação subsequente — em particular o
    enfileiramento de retries de coleta, que depende de uma FK válida para
    `plants.id`.
    """
    async with SessionFactory() as session:
        await set_platform_context(session)
        plant = await PlantRepository(session).get_or_create(
            plant_name, organization_id=DEFAULT_ORGANIZATION_ID
        )
        plant_id = plant.id
        await session.commit()
    return plant_id


async def _list_organization_plants(
    organization_id: uuid.UUID,
) -> list[tuple[uuid.UUID, str]]:
    """List every plant of ``organization_id``, ordered deterministically.

    Ordered by ``Plant.name`` then ``Plant.id`` -- same tie-break as the
    HTTP fan-out resolver (``core.tenancy.resolve_admin_plant_fanout``,
    ADR-069 § E.11.3) -- so job runs process plants in a stable order across
    executions. No cap on plant count: the Cloud Run Job runs with
    ``--task-timeout 30m`` (ADR-069 § E.11.1 achado B), unlike the 60s HTTP
    fan-out that needs ``fanout_max_plants``.
    """
    async with SessionFactory() as session:
        await set_platform_context(session)
        result = await session.execute(
            select(Plant.id, Plant.name)
            .where(Plant.organization_id == organization_id)
            .order_by(Plant.name, Plant.id)
        )
        return [(row[0], row[1]) for row in result.all()]


def _required_decimal(value: Decimal | None, env_name: str) -> Decimal:
    if value is None:
        raise RuntimeError(f"{env_name} is required")
    if value <= 0:
        raise RuntimeError(f"{env_name} must be positive")
    return value


def _destination_ref(chat_id: str) -> str:
    return f"telegram:{hashlib.sha256(chat_id.encode('utf-8')).hexdigest()[:16]}"


def _run_command(args: list[str], env: Mapping[str, str]) -> CommandResult:
    completed = subprocess.run(
        args,
        env={**os.environ, **env},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _sanitize(message: str, database_url: str) -> str:
    if not database_url:
        return message
    sanitized = message.replace(database_url, "<database-url>")
    try:
        parsed = urlsplit(database_url)
        if parsed.netloc:
            redacted = urlunsplit(parsed._replace(netloc="<redacted>"))
            sanitized = sanitized.replace(database_url, redacted)
            # Also replace un-normalized URL prefixes that normalize to this URL
            # (postgres:// / postgresql:// → postgresql+asyncpg://).
            for alt_prefix in ("postgres://", "postgresql://"):
                if database_url.startswith("postgresql+asyncpg://"):
                    alt = alt_prefix + database_url[len("postgresql+asyncpg://"):]
                    sanitized = sanitized.replace(alt, "<database-url>")
            # Redact the password directly as a final safety net.
            if parsed.password:
                sanitized = sanitized.replace(parsed.password, "<redacted>")
    except Exception:
        pass
    return sanitized


if __name__ == "__main__":
    raise SystemExit(main())
