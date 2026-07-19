from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
import subprocess
import sys
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from mplacas.alerts.job import AlertJobSummary
from mplacas.alerts.models import AlertSeverity
from mplacas.alerts.outbox import dispatch_due_alert_outbox
from mplacas.alerts.telegram import TelegramAlertProvider
from mplacas.climate.open_meteo import OpenMeteoHistoricalProvider
from mplacas.core.config import get_settings
from mplacas.db.session import SessionFactory
from mplacas.db.session import engine as database_engine
from mplacas.observability.context import (
    bind_correlation_context,
    new_correlation_context,
)
from mplacas.observability.tracing import configure_observability, traced_operation
from opentelemetry.trace import Status, StatusCode
from mplacas.orchestration.runtime import run_ledger_backed_daily_pipeline

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

    daily = subparsers.add_parser("daily-pipeline", help="run the daily operational pipeline")
    daily.add_argument("--target-date", default=None, help="YYYY-MM-DD; defaults to yesterday")
    daily.set_defaults(handler=_handle_daily_pipeline)

    outbox = subparsers.add_parser(
        "dispatch-outbox",
        help="deliver due transactional outbox events",
    )
    outbox.set_defaults(handler=_handle_outbox_dispatch)
    return parser


def _handle_migrate(_args: argparse.Namespace) -> int:
    return run_migrations()


def _handle_daily_pipeline(args: argparse.Namespace) -> int:
    target_date = args.target_date
    asyncio.run(run_daily_pipeline(target_date=target_date))
    return 0


def _handle_outbox_dispatch(_args: argparse.Namespace) -> int:
    asyncio.run(run_outbox_dispatch())
    return 0


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
    settings = get_settings()
    plant_id = _required_uuid(settings.cloud_job_plant_id, "MPLACAS_CLOUD_JOB_PLANT_ID")
    expected_daily = _required_decimal(
        settings.cloud_job_expected_daily_production_kwh,
        "MPLACAS_CLOUD_JOB_EXPECTED_DAILY_PRODUCTION_KWH",
    )
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

    logger.info(
        "cloud_job_daily_pipeline_started",
        extra={"plant_id": str(plant_id), "target_date": resolved_date.isoformat()},
    )
    async with SessionFactory() as session:
        try:
            await run_ledger_backed_daily_pipeline(
                session,
                plant_id=plant_id,
                target_date=resolved_date,
                climate_provider=climate_provider,
                alert_provider=alert_provider,
                alert_destination_ref=_destination_ref(chat_id),
                expected_daily_production_kwh=expected_daily,
                expected_cycle_production_kwh=settings.cloud_job_expected_cycle_production_kwh,
                anomaly_days=settings.cloud_job_anomaly_days,
                minimum_severity=AlertSeverity.WARNING,
                stale_lock_timeout_minutes=settings.pipeline_stale_lock_timeout_minutes,
                outbox_max_attempts=settings.outbox_max_attempts,
            )
            await session.commit()
        except Exception:
            await session.commit()
            raise
    logger.info(
        "cloud_job_daily_pipeline_completed",
        extra={"plant_id": str(plant_id), "target_date": resolved_date.isoformat()},
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


def _required_uuid(value: str | None, env_name: str) -> uuid.UUID:
    if value is None or not value.strip():
        raise RuntimeError(f"{env_name} is required")
    return uuid.UUID(value)


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
    sanitized = message
    if database_url:
        sanitized = sanitized.replace(database_url, "<database-url>")
    lowered = database_url.lower()
    if "@" in database_url and ":" in database_url.split("@", maxsplit=1)[0]:
        credentials = database_url.split("//", maxsplit=1)[-1].split("@", maxsplit=1)[0]
        sanitized = sanitized.replace(credentials, "<credentials>")
    if "password" in lowered:
        sanitized = sanitized.replace("password", "<redacted>")
    return sanitized


if __name__ == "__main__":
    raise SystemExit(main())
