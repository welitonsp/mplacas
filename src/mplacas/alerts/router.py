from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from mplacas.audit.repository import AuditEventRepository
from mplacas.alerts.models import AlertSeverity
from mplacas.alerts.operations import run_operational_alert_pipeline
from mplacas.alerts.telegram import TelegramAlertProvider
from mplacas.core.config import get_settings
from mplacas.core.security import require_operations_key
from mplacas.db.session import SessionFactory

router = APIRouter(
    prefix="/alerts",
    tags=["alerts"],
    dependencies=[Depends(require_operations_key)],
)


def _destination_ref(chat_id: str) -> str:
    digest = hashlib.sha256(chat_id.encode("utf-8")).hexdigest()[:16]
    return f"telegram:{digest}"


@router.post("/run", status_code=status.HTTP_200_OK)
async def run_alerts(
    request: Request,
    plant_id: uuid.UUID,
    expected_daily_production_kwh: Decimal = Query(gt=0),
    expected_cycle_production_kwh: Decimal | None = Query(default=None, gt=0),
    anomaly_days: int = Query(default=7, ge=1, le=90),
    minimum_severity: AlertSeverity = Query(default=AlertSeverity.WARNING),
) -> dict[str, object]:
    settings = get_settings()
    token = settings.telegram_bot_token
    chat_id = settings.telegram_alert_chat_id
    if token is None or not chat_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="telegram alert delivery is not configured",
        )

    provider = TelegramAlertProvider(
        bot_token=token.get_secret_value(),
        chat_id=chat_id,
        timeout_seconds=settings.request_timeout_seconds,
    )
    async with SessionFactory() as session:
        result = await run_operational_alert_pipeline(
            session,
            plant_id=plant_id,
            provider=provider,
            destination_ref=_destination_ref(chat_id),
            expected_daily_production_kwh=expected_daily_production_kwh,
            expected_cycle_production_kwh=expected_cycle_production_kwh,
            anomaly_days=anomaly_days,
            minimum_severity=minimum_severity,
            outbox_max_attempts=settings.outbox_max_attempts,
        )
        await AuditEventRepository(session).record(
            request,
            action="alerts.run",
            resource_type="plant",
            resource_id=str(result.plant_id),
            outcome="SUCCEEDED",
            details={
                "executive_available": result.executive_available,
                "anomaly_available": result.anomaly_available,
                "evaluated": result.metrics.evaluated,
                "sent": result.metrics.sent,
                "skipped": result.metrics.skipped,
                "failed": result.metrics.failed,
                "duplicates": result.metrics.duplicates,
                "below_minimum_severity": result.metrics.below_minimum_severity,
                "minimum_severity": minimum_severity.value,
            },
        )
        await session.commit()

    return {
        "plant_id": str(result.plant_id),
        "executive_available": result.executive_available,
        "anomaly_available": result.anomaly_available,
        "metrics": {
            "evaluated": result.metrics.evaluated,
            "sent": result.metrics.sent,
            "skipped": result.metrics.skipped,
            "failed": result.metrics.failed,
            "duplicates": result.metrics.duplicates,
            "below_minimum_severity": result.metrics.below_minimum_severity,
        },
        "results": [
            {
                "status": item.status.value,
                "fingerprint": item.fingerprint,
                "reason": item.reason,
            }
            for item in result.job.results
        ],
    }
