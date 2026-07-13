from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.alerts.candidates import anomaly_alert_candidate, executive_alert_candidate
from mplacas.alerts.job import AlertJobSummary, run_alert_dispatch_job
from mplacas.alerts.models import AlertCandidate, AlertSeverity
from mplacas.alerts.provider import AlertProvider
from mplacas.alerts.sql_ledger import SqlAlertDeliveryLedger
from mplacas.intelligence.anomaly_service import (
    AnomalyDataNotFoundError,
    analyze_recent_persisted_anomalies,
)
from mplacas.intelligence.cycle_service import EnergyCycleNotFoundError
from mplacas.intelligence.executive_service import build_executive_dashboard

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OperationalAlertPipelineResult:
    plant_id: uuid.UUID
    generated: int
    executive_available: bool
    anomaly_available: bool
    dispatch: AlertJobSummary


async def run_operational_alert_pipeline(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    expected_daily_production_kwh: Decimal,
    provider: AlertProvider,
    destination_ref: str,
    minimum_severity: AlertSeverity = AlertSeverity.WARNING,
    anomaly_days: int = 7,
) -> OperationalAlertPipelineResult:
    if expected_daily_production_kwh <= 0:
        raise ValueError("expected daily production must be greater than zero")
    if not 1 <= anomaly_days <= 90:
        raise ValueError("anomaly_days must be between 1 and 90")

    candidates: list[AlertCandidate] = []
    executive_available = False
    anomaly_available = False

    try:
        dashboard = await build_executive_dashboard(session, plant_id=plant_id)
    except EnergyCycleNotFoundError:
        logger.info(
            "alert_pipeline_executive_unavailable",
            extra={"plant_id": str(plant_id)},
        )
    else:
        executive_available = True
        candidates.append(executive_alert_candidate(dashboard))

    try:
        anomaly_summary = await analyze_recent_persisted_anomalies(
            session,
            plant_id=plant_id,
            expected_daily_production_kwh=expected_daily_production_kwh,
            days=anomaly_days,
        )
    except AnomalyDataNotFoundError:
        logger.info(
            "alert_pipeline_anomaly_unavailable",
            extra={"plant_id": str(plant_id), "days": anomaly_days},
        )
    else:
        anomaly_available = True
        candidates.append(anomaly_alert_candidate(anomaly_summary))

    ledger = SqlAlertDeliveryLedger(
        session,
        provider="telegram",
        destination_ref=destination_ref,
    )
    dispatch = await run_alert_dispatch_job(
        candidates,
        provider=provider,
        ledger=ledger,
        minimum_severity=minimum_severity,
    )
    duplicate_count = sum(
        item.reason == "duplicate alert" for item in dispatch.results
    )
    logger.info(
        "alert_pipeline_completed",
        extra={
            "plant_id": str(plant_id),
            "generated": len(candidates),
            "evaluated": dispatch.evaluated,
            "sent": dispatch.sent,
            "skipped": dispatch.skipped,
            "failed": dispatch.failed,
            "duplicates": duplicate_count,
        },
    )
    return OperationalAlertPipelineResult(
        plant_id=plant_id,
        generated=len(candidates),
        executive_available=executive_available,
        anomaly_available=anomaly_available,
        dispatch=dispatch,
    )
