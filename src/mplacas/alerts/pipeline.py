from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.alerts.candidates import anomaly_summary_to_alerts
from mplacas.alerts.job import AlertJobSummary, run_alert_dispatch_job
from mplacas.alerts.models import AlertSeverity
from mplacas.alerts.provider import AlertProvider
from mplacas.alerts.sql_ledger import SqlAlertDeliveryLedger
from mplacas.intelligence.anomaly_service import analyze_recent_persisted_anomalies

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AlertPipelineResult:
    plant_id: uuid.UUID
    anomaly_days: int
    candidates: int
    job: AlertJobSummary


async def run_anomaly_alert_pipeline(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    expected_daily_production_kwh: Decimal,
    provider: AlertProvider,
    provider_name: str,
    destination_ref: str,
    days: int = 7,
    minimum_severity: AlertSeverity = AlertSeverity.WARNING,
) -> AlertPipelineResult:
    """Analyze persisted energy data, derive alerts and dispatch them idempotently."""
    summary = await analyze_recent_persisted_anomalies(
        session,
        plant_id=plant_id,
        expected_daily_production_kwh=expected_daily_production_kwh,
        days=days,
    )
    alerts = anomaly_summary_to_alerts(summary)
    ledger = SqlAlertDeliveryLedger(
        session,
        provider=provider_name,
        destination_ref=destination_ref,
    )
    job = await run_alert_dispatch_job(
        alerts,
        provider=provider,
        ledger=ledger,
        minimum_severity=minimum_severity,
    )
    logger.info(
        "alert_pipeline_completed",
        extra={
            "plant_id": str(plant_id),
            "days_analyzed": summary.days_analyzed,
            "candidates": len(alerts),
            "sent": job.sent,
            "skipped": job.skipped,
            "failed": job.failed,
        },
    )
    return AlertPipelineResult(
        plant_id=plant_id,
        anomaly_days=summary.days_analyzed,
        candidates=len(alerts),
        job=job,
    )
