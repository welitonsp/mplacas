from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from mplacas.alerts.models import AlertSeverity
from mplacas.alerts.pipeline import run_operational_alert_pipeline
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
    plant_id: uuid.UUID,
    expected_daily_production_kwh: Decimal = Query(gt=0),
    anomaly_days: int = Query(default=7, ge=1, le=90),
    minimum_severity: AlertSeverity = Query(default=AlertSeverity.WARNING),
) -> dict[str, object]:
    settings = get_settings()
    if not settings.telegram_alerts_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="outbound Telegram alerts are not configured",
        )

    token = settings.telegram_bot_token
    chat = settings.telegram_alert_chat_id
    if token is None or chat is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="outbound Telegram alerts are not configured",
        )

    token_value = token.get_secret_value()
    chat_value = chat.get_secret_value()
    provider = TelegramAlertProvider(
        bot_token=token_value,
        chat_id=chat_value,
        timeout_seconds=settings.request_timeout_seconds,
    )

    async with SessionFactory() as session:
        result = await run_operational_alert_pipeline(
            session,
            plant_id=plant_id,
            expected_daily_production_kwh=expected_daily_production_kwh,
            provider=provider,
            destination_ref=_destination_ref(chat_value),
            minimum_severity=minimum_severity,
            anomaly_days=anomaly_days,
        )

    duplicate_count = sum(
        item.reason == "duplicate alert" for item in result.dispatch.results
    )
    return {
        "plant_id": str(result.plant_id),
        "generated": result.generated,
        "executive_available": result.executive_available,
        "anomaly_available": result.anomaly_available,
        "evaluated": result.dispatch.evaluated,
        "sent": result.dispatch.sent,
        "skipped": result.dispatch.skipped,
        "failed": result.dispatch.failed,
        "duplicates": duplicate_count,
        "results": [
            {
                "status": item.status.value,
                "fingerprint": item.fingerprint,
                "reason": item.reason,
            }
            for item in result.dispatch.results
        ],
    }
