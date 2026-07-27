from __future__ import annotations

import argparse
import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from opentelemetry.trace import Status, StatusCode

from mplacas.cloud_jobs import run_collection
from mplacas.core.config import get_settings
from mplacas.db.session import engine as database_engine
from mplacas.observability.context import bind_correlation_context, new_correlation_context
from mplacas.observability.tracing import configure_observability, traced_operation

logger = logging.getLogger(__name__)
_MAX_BACKFILL_DAYS = 31


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    correlation = new_correlation_context(request_id=f"weekly-backfill-{uuid.uuid4().hex}")
    observability = None

    with bind_correlation_context(correlation):
        try:
            settings = get_settings()
            observability = configure_observability(
                settings=settings,
                service_name="mplacas-job-weekly-backfill",
                engine=database_engine,
            )
            with traced_operation(
                "weekly_backfill",
                days=args.days,
                end_date=args.end_date or "yesterday",
            ) as span:
                try:
                    asyncio.run(
                        run_weekly_backfill(
                            days=args.days,
                            end_date=args.end_date,
                        )
                    )
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                    logger.error(
                        "weekly_backfill_failed",
                        extra={"error_code": type(exc).__name__},
                    )
                    return 1
            return 0
        except Exception as exc:
            logger.error(
                "weekly_backfill_bootstrap_failed",
                extra={"error_code": type(exc).__name__},
            )
            return 1
        finally:
            if observability is not None:
                observability.shutdown()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mplacas.weekly_backfill",
        description="Backfill an idempotent window of daily solar production.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="number of days to process, from 1 to 31 (default: 7)",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="last date in YYYY-MM-DD; defaults to yesterday in MPLACAS_TIMEZONE",
    )
    return parser


async def run_weekly_backfill(
    *,
    days: int = 7,
    end_date: str | None = None,
    now: datetime | None = None,
) -> tuple[date, ...]:
    if not 1 <= days <= _MAX_BACKFILL_DAYS:
        raise ValueError(f"days must be between 1 and {_MAX_BACKFILL_DAYS}")

    settings = get_settings()
    resolved_end = _resolve_end_date(
        end_date=end_date,
        timezone_name=settings.timezone,
        now=now,
    )
    dates = tuple(
        resolved_end - timedelta(days=offset)
        for offset in range(days - 1, -1, -1)
    )

    logger.info(
        "weekly_backfill_started",
        extra={
            "days": days,
            "start_date": dates[0].isoformat(),
            "end_date": dates[-1].isoformat(),
        },
    )
    for target_date in dates:
        await run_collection(target_date=target_date.isoformat(), now=now)
    logger.info(
        "weekly_backfill_completed",
        extra={
            "days": days,
            "start_date": dates[0].isoformat(),
            "end_date": dates[-1].isoformat(),
        },
    )
    return dates


def _resolve_end_date(
    *,
    end_date: str | None,
    timezone_name: str,
    now: datetime | None,
) -> date:
    if end_date is not None:
        return datetime.strptime(end_date, "%Y-%m-%d").date()
    timezone = ZoneInfo(timezone_name)
    current = now.astimezone(timezone) if now is not None else datetime.now(timezone)
    return (current - timedelta(days=1)).date()


if __name__ == "__main__":
    raise SystemExit(main())
