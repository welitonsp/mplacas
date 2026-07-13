from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.alerts.models import AlertSeverity
from mplacas.alerts.operations import AlertPipelineResult, run_operational_alert_pipeline
from mplacas.alerts.telegram import TelegramAlertProvider
from mplacas.climate.collection_service import (
    ClimateCollectionResult,
    collect_and_persist_daily_climate,
)
from mplacas.climate.provider import ClimateProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DailyEnergyPipelineResult:
    plant_id: uuid.UUID
    target_date: date
    climate: ClimateCollectionResult
    alerts: AlertPipelineResult


async def run_daily_energy_pipeline(
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
) -> DailyEnergyPipelineResult:
    """Collect climate data and dispatch alerts in one auditable execution.

    Persistence remains idempotent in the climate repository and alert ledger.
    The transaction is committed only by the caller, allowing an operational
    endpoint or scheduler to decide the final transaction boundary.
    """
    if expected_daily_production_kwh <= 0:
        raise ValueError("expected daily production must be positive")
    if expected_cycle_production_kwh is not None and expected_cycle_production_kwh <= 0:
        raise ValueError("expected cycle production must be positive")
    if not 1 <= anomaly_days <= 90:
        raise ValueError("anomaly days must be between 1 and 90")
    if not alert_destination_ref.strip():
        raise ValueError("alert destination reference is required")

    climate = await collect_and_persist_daily_climate(
        session,
        plant_id=plant_id,
        provider=climate_provider,
        start_date=target_date,
        end_date=target_date,
        maximum_days=1,
    )
    alerts = await run_operational_alert_pipeline(
        session,
        plant_id=plant_id,
        provider=alert_provider,
        destination_ref=alert_destination_ref,
        expected_daily_production_kwh=expected_daily_production_kwh,
        expected_cycle_production_kwh=expected_cycle_production_kwh,
        anomaly_days=anomaly_days,
        minimum_severity=minimum_severity,
    )
    logger.info(
        "daily_energy_pipeline_completed",
        extra={
            "plant_id": str(plant_id),
            "target_date": target_date.isoformat(),
            "climate_received": climate.received,
            "alerts_evaluated": alerts.metrics.evaluated,
            "alerts_sent": alerts.metrics.sent,
            "alerts_failed": alerts.metrics.failed,
        },
    )
    return DailyEnergyPipelineResult(
        plant_id=plant_id,
        target_date=target_date,
        climate=climate,
        alerts=alerts,
    )
