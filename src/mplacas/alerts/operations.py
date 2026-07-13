from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.alerts.candidates import build_alert_candidates
from mplacas.alerts.job import AlertJobSummary, run_alert_dispatch_job
from mplacas.alerts.models import AlertSeverity
from mplacas.alerts.sql_ledger import SqlAlertDeliveryLedger
from mplacas.alerts.telegram import TelegramAlertProvider
from mplacas.intelligence.anomaly_service import (
    AnomalyDataNotFoundError,
    analyze_recent_persisted_anomalies,
)
from mplacas.intelligence.cycle_service import EnergyCycleNotFoundError
from mplacas.intelligence.executive_service import build_executive_dashboard

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AlertPipelineMetrics:
    evaluated: int
    sent: int
    skipped: int
    failed: int
    duplicates: int
    below_minimum_severity: int


@dataclass(frozen=True, slots=True)
class AlertPipelineResult:
    plant_id: uuid.UUID
    executive_available: bool
    anomaly_available: bool
    metrics: AlertPipelineMetrics
    job: AlertJobSummary


async def run_operational_alert_pipeline(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    provider: TelegramAlertProvider,
    destination_ref: str,
    expected_daily_production_kwh: Decimal,
    expected_cycle_production_kwh: Decimal | None = None,
    anomaly_days: int = 7,
    minimum_severity: AlertSeverity = AlertSeverity.WARNING,
) -> AlertPipelineResult:
    executive = None
    anomalies = None

    try:
        executive = await build_executive_dashboard(
            session,
            plant_id=plant_id,
            expected_production_kwh=expected_cycle_production_kwh,
        )
    except EnergyCycleNotFoundError:
        logger.info("alert_pipeline_executive_unavailable", extra={"plant_id": str(plant_id)})

    try:
        anomalies = await analyze_recent_persisted_anomalies(
            session,
            plant_id=plant_id,
            expected_daily_production_kwh=expected_daily_production_kwh,
            days=anomaly_days,
        )
    except AnomalyDataNotFoundError:
        logger.info("alert_pipeline_anomaly_unavailable", extra={"plant_id": str(plant_id)})

    candidates = build_alert_candidates(executive=executive, anomalies=anomalies)
    ledger = SqlAlertDeliveryLedger(
        session,
        provider="telegram",
        destination_ref=destination_ref,
    )
    job = await run_alert_dispatch_job(
        candidates,
        provider=provider,
        ledger=ledger,
        minimum_severity=minimum_severity,
    )
    duplicates = sum(item.reason == "duplicate alert" for item in job.results)
    below_minimum = sum(item.reason == "below minimum severity" for item in job.results)
    metrics = AlertPipelineMetrics(
        evaluated=job.evaluated,
        sent=job.sent,
        skipped=job.skipped,
        failed=job.failed,
        duplicates=duplicates,
        below_minimum_severity=below_minimum,
    )
    logger.info(
        "alert_pipeline_completed",
        extra={
            "plant_id": str(plant_id),
            "evaluated": metrics.evaluated,
            "sent": metrics.sent,
            "skipped": metrics.skipped,
            "failed": metrics.failed,
            "duplicates": metrics.duplicates,
        },
    )
    return AlertPipelineResult(
        plant_id=plant_id,
        executive_available=executive is not None,
        anomaly_available=anomalies is not None,
        metrics=metrics,
        job=job,
    )
