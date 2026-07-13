from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from time import monotonic

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.alerts.models import AlertSeverity
from mplacas.alerts.telegram import TelegramAlertProvider
from mplacas.climate.provider import ClimateProvider
from mplacas.orchestration.daily_pipeline import DailyEnergyPipelineResult, run_daily_energy_pipeline
from mplacas.orchestration.execution_repository import PipelineExecutionRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OperationalPipelineResult:
    execution_id: uuid.UUID
    plant_id: uuid.UUID
    target_date: date
    duration_ms: int
    pipeline: DailyEnergyPipelineResult


def _error_code(exc: Exception) -> str:
    name = type(exc).__name__.upper()
    cleaned = "".join(character for character in name if character.isalnum() or character == "_")
    return (cleaned or "PIPELINE_ERROR")[:80]


async def run_ledger_backed_daily_pipeline(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    target_date: date,
    climate_provider: ClimateProvider,
    alert_provider: TelegramAlertProvider,
    alert_destination_ref: str,
    expected_daily_production_kwh: Decimal,
    expected_cycle_production_kwh: Decimal | None = None,
    anomaly_days: int = 7,
    minimum_severity: AlertSeverity = AlertSeverity.WARNING,
) -> OperationalPipelineResult:
    repository = PipelineExecutionRepository(session)
    execution = await repository.acquire(plant_id=plant_id, target_date=target_date)
    started = monotonic()
    try:
        await repository.mark_stage(execution, "CLIMATE_AND_ANALYSIS")
        result = await run_daily_energy_pipeline(
            session,
            plant_id=plant_id,
            target_date=target_date,
            climate_provider=climate_provider,
            alert_provider=alert_provider,
            alert_destination_ref=alert_destination_ref,
            expected_daily_production_kwh=expected_daily_production_kwh,
            expected_cycle_production_kwh=expected_cycle_production_kwh,
            anomaly_days=anomaly_days,
            minimum_severity=minimum_severity,
        )
        await repository.succeed(execution)
    except Exception as exc:
        await repository.fail(execution, error_code=_error_code(exc))
        logger.exception(
            "daily_pipeline_failed",
            extra={"plant_id": str(plant_id), "target_date": target_date.isoformat()},
        )
        raise

    duration_ms = max(0, round((monotonic() - started) * 1000))
    logger.info(
        "daily_pipeline_succeeded",
        extra={
            "plant_id": str(plant_id),
            "target_date": target_date.isoformat(),
            "execution_id": str(execution.id),
            "duration_ms": duration_ms,
        },
    )
    return OperationalPipelineResult(
        execution_id=execution.id,
        plant_id=plant_id,
        target_date=target_date,
        duration_ms=duration_ms,
        pipeline=result,
    )
