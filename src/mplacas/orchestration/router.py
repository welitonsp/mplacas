from __future__ import annotations

import hashlib
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from mplacas.audit.repository import AuditEventRepository
from mplacas.alerts.models import AlertSeverity
from mplacas.alerts.telegram import TelegramAlertProvider
from mplacas.climate.open_meteo import OpenMeteoHistoricalProvider
from mplacas.core.config import get_settings
from mplacas.core.security import require_operations_key
from mplacas.db.session import SessionFactory
from mplacas.orchestration.execution_repository import PipelineExecutionAlreadyRunningError
from mplacas.orchestration.runtime import run_ledger_backed_daily_pipeline
from mplacas.orchestration.status_service import get_latest_pipeline_execution

router = APIRouter(
    prefix="/pipeline",
    tags=["pipeline"],
    dependencies=[Depends(require_operations_key)],
)


def _destination_ref(chat_id: str) -> str:
    return f"telegram:{hashlib.sha256(chat_id.encode('utf-8')).hexdigest()[:16]}"


@router.post("/run", status_code=status.HTTP_200_OK)
async def run_pipeline(
    request: Request,
    plant_id: uuid.UUID,
    target_date: date,
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

    climate_provider = OpenMeteoHistoricalProvider(
        base_url=str(settings.climate_archive_base_url),
        timeout_seconds=settings.request_timeout_seconds,
    )
    alert_provider = TelegramAlertProvider(
        bot_token=token.get_secret_value(),
        chat_id=chat_id,
        timeout_seconds=settings.request_timeout_seconds,
    )

    async with SessionFactory() as session:
        try:
            result = await run_ledger_backed_daily_pipeline(
                session,
                plant_id=plant_id,
                target_date=target_date,
                climate_provider=climate_provider,
                alert_provider=alert_provider,
                alert_destination_ref=_destination_ref(chat_id),
                expected_daily_production_kwh=expected_daily_production_kwh,
                expected_cycle_production_kwh=expected_cycle_production_kwh,
                anomaly_days=anomaly_days,
                minimum_severity=minimum_severity,
                stale_lock_timeout_minutes=settings.pipeline_stale_lock_timeout_minutes,
                outbox_max_attempts=settings.outbox_max_attempts,
            )
            await AuditEventRepository(session).record(
                request,
                action="pipeline.run",
                resource_type="pipeline_execution",
                resource_id=str(result.execution_id),
                outcome="SUCCEEDED",
                details={
                    "plant_id": str(result.plant_id),
                    "target_date": result.target_date.isoformat(),
                    "alerts_sent": result.pipeline.alerts.metrics.sent,
                    "alerts_failed": result.pipeline.alerts.metrics.failed,
                },
            )
            await session.commit()
        except PipelineExecutionAlreadyRunningError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="pipeline execution is already running",
            ) from exc
        except ValueError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            execution_id = None
            latest = await get_latest_pipeline_execution(session, plant_id=plant_id)
            if latest is not None and latest.target_date == target_date:
                execution_id = str(latest.execution_id)
            await AuditEventRepository(session).record(
                request,
                action="pipeline.run",
                resource_type="pipeline_execution",
                resource_id=execution_id,
                outcome="FAILED",
                details={
                    "plant_id": str(plant_id),
                    "target_date": target_date.isoformat(),
                    "error_code": type(exc).__name__,
                },
            )
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="pipeline execution failed",
            ) from exc

    return {
        "execution_id": str(result.execution_id),
        "plant_id": str(result.plant_id),
        "target_date": result.target_date.isoformat(),
        "duration_ms": result.duration_ms,
        "climate_received": result.pipeline.climate.received,
        "alerts": {
            "evaluated": result.pipeline.alerts.metrics.evaluated,
            "sent": result.pipeline.alerts.metrics.sent,
            "skipped": result.pipeline.alerts.metrics.skipped,
            "failed": result.pipeline.alerts.metrics.failed,
        },
    }


@router.get("/status/latest", status_code=status.HTTP_200_OK)
async def latest_pipeline_status(plant_id: uuid.UUID) -> dict[str, object]:
    async with SessionFactory() as session:
        snapshot = await get_latest_pipeline_execution(session, plant_id=plant_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="pipeline execution not found",
        )
    return {
        "execution_id": str(snapshot.execution_id),
        "plant_id": str(snapshot.plant_id),
        "target_date": snapshot.target_date.isoformat(),
        "status": snapshot.status.value,
        "attempt_count": snapshot.attempt_count,
        "stage": snapshot.stage,
        "error_code": snapshot.error_code,
        "started_at": snapshot.started_at.isoformat(),
        "finished_at": snapshot.finished_at.isoformat() if snapshot.finished_at else None,
    }
