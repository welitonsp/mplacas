from __future__ import annotations

import hashlib
import logging
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, Request, status

from mplacas.audit.repository import AuditEventRepository
from mplacas.alerts.models import AlertSeverity
from mplacas.alerts.telegram import TelegramAlertProvider
from mplacas.climate.open_meteo import OpenMeteoHistoricalProvider
from mplacas.core.config import get_settings
from mplacas.core.fanout import FanoutItem, error_detail, fanout_envelope, fetch_plant_name
from mplacas.core.tenancy import AdminPlantFanout
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_principal_context
from mplacas.orchestration.execution_repository import PipelineExecutionAlreadyRunningError
from mplacas.orchestration.runtime import run_ledger_backed_daily_pipeline
from mplacas.orchestration.status_service import get_latest_pipeline_execution
from mplacas.photovoltaic.read_service import resolve_expected_daily_production

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/pipeline",
    tags=["pipeline"],
)


def _destination_ref(chat_id: str) -> str:
    return f"telegram:{hashlib.sha256(chat_id.encode('utf-8')).hexdigest()[:16]}"


def _run_result_payload(result) -> dict[str, object]:
    return {
        "execution_id": str(result.execution_id),
        "target_date": result.target_date.isoformat(),
        "duration_ms": result.duration_ms,
        "climate_received": result.pipeline.climate.received,
        "solar_projection": {
            "inserted": result.pipeline.climate.solar_projection.inserted,
            "updated": result.pipeline.climate.solar_projection.updated,
            "unchanged": result.pipeline.climate.solar_projection.unchanged,
            "skipped": result.pipeline.climate.solar_projection.skipped,
            "skip_reason": result.pipeline.climate.solar_projection.skip_reason,
        },
        "performance": {
            "inserted": result.pipeline.performance.inserted,
            "updated": result.pipeline.performance.updated,
            "unchanged": result.pipeline.performance.unchanged,
            "skipped": result.pipeline.performance.skipped,
            "skip_reason": result.pipeline.performance.skip_reason,
        },
        "seasonal_baseline": {
            "inserted": result.pipeline.seasonal_baseline.inserted,
            "updated": result.pipeline.seasonal_baseline.updated,
            "unchanged": result.pipeline.seasonal_baseline.unchanged,
            "skipped": result.pipeline.seasonal_baseline.skipped,
            "skip_reason": result.pipeline.seasonal_baseline.skip_reason,
        },
        "loss_taxonomy": {
            "inserted": result.pipeline.loss_taxonomy.inserted,
            "updated": result.pipeline.loss_taxonomy.updated,
            "unchanged": result.pipeline.loss_taxonomy.unchanged,
            "skipped": result.pipeline.loss_taxonomy.skipped,
            "skip_reason": result.pipeline.loss_taxonomy.skip_reason,
        },
        "alerts": {
            "evaluated": result.pipeline.alerts.metrics.evaluated,
            "sent": result.pipeline.alerts.metrics.sent,
            "skipped": result.pipeline.alerts.metrics.skipped,
            "failed": result.pipeline.alerts.metrics.failed,
        },
    }


def _status_payload(snapshot) -> dict[str, object]:
    return {
        "execution_id": str(snapshot.execution_id),
        "target_date": snapshot.target_date.isoformat(),
        "status": snapshot.status.value,
        "attempt_count": snapshot.attempt_count,
        "stage": snapshot.stage,
        "error_code": snapshot.error_code,
        "started_at": snapshot.started_at.isoformat(),
        "finished_at": snapshot.finished_at.isoformat() if snapshot.finished_at else None,
    }


@router.post("/run", status_code=status.HTTP_200_OK)
async def run_pipeline(
    request: Request,
    scoped: AdminPlantFanout,
    target_date: date,
    expected_daily_production_kwh: Decimal | None = Query(default=None, gt=0),
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

    if len(scoped.plant_ids) > 1 and (
        expected_daily_production_kwh is not None
        or expected_cycle_production_kwh is not None
    ):
        # ADR-069 § E.11.5: a single expectation cannot describe N plants of
        # different sizes — request-level error, raised before touching any
        # plant, distinct from a per-plant failure. Ambiguity is judged by the
        # *resolved* set size, not ``scoped.explicit``: a static platform key
        # with exactly one plant is ``explicit=False`` but unambiguous (ADR-069
        # § E.11.3), so it must not be rejected here.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="expected_daily_production_kwh/expected_cycle_production_kwh "
            "require an explicit plant_id when more than one plant may be in scope",
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

    items: list[FanoutItem] = []
    for plant_id in scoped.plant_ids:
        scoped.principal.require_plant_access(plant_id)  # ADR-069 § E.11.4: defensive
        async with SessionFactory() as session:  # sessão nova por usina
            await set_principal_context(session, scoped.principal)
            plant_name = await fetch_plant_name(session, plant_id)

            per_plant_expected_daily = expected_daily_production_kwh
            if per_plant_expected_daily is None:
                # ADR-069 § E.11.5: derive the expectation for this plant
                # instead of requiring the caller to pass it.
                resolution = await resolve_expected_daily_production(
                    session, plant_id=plant_id
                )
                if resolution.expected is None:
                    if scoped.explicit:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"unavailable_reason": resolution.unavailable_reason},
                        )
                    items.append(
                        FanoutItem(
                            plant_id=plant_id,
                            plant_name=plant_name,
                            outcome="skipped",
                            error=None,
                            result={
                                "unavailable_reason": resolution.unavailable_reason
                            },
                        )
                    )
                    continue
                per_plant_expected_daily = (
                    resolution.expected.expected_daily_production_kwh
                )

            try:
                result = await run_ledger_backed_daily_pipeline(
                    session,
                    plant_id=plant_id,
                    target_date=target_date,
                    climate_provider=climate_provider,
                    alert_provider=alert_provider,
                    alert_destination_ref=_destination_ref(chat_id),
                    expected_daily_production_kwh=per_plant_expected_daily,
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
                if scoped.explicit:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="pipeline execution is already running",
                    ) from exc
                message = "pipeline execution is already running"
                await AuditEventRepository(session).record(
                    request,
                    action="pipeline.run",
                    resource_type="pipeline_execution",
                    resource_id=None,
                    outcome="failure",
                    details={
                        "plant_id": str(plant_id),
                        "target_date": target_date.isoformat(),
                        "error_code": type(exc).__name__,
                    },
                )
                await session.commit()
                items.append(
                    FanoutItem(
                        plant_id=plant_id,
                        plant_name=plant_name,
                        outcome="failed",
                        error=error_detail(exc, message=message),
                        result=None,
                    )
                )
                continue
            except ValueError as exc:
                await session.rollback()
                message = str(exc)
                if scoped.explicit:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=message,
                    ) from exc
                await AuditEventRepository(session).record(
                    request,
                    action="pipeline.run",
                    resource_type="pipeline_execution",
                    resource_id=None,
                    outcome="failure",
                    details={
                        "plant_id": str(plant_id),
                        "target_date": target_date.isoformat(),
                        "error_code": type(exc).__name__,
                    },
                )
                await session.commit()
                items.append(
                    FanoutItem(
                        plant_id=plant_id,
                        plant_name=plant_name,
                        outcome="failed",
                        error=error_detail(exc, message=message),
                        result=None,
                    )
                )
                continue
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                execution_id = None
                latest = await get_latest_pipeline_execution(session, plant_id=plant_id)
                if latest is not None and latest.target_date == target_date:
                    execution_id = str(latest.execution_id)
                await AuditEventRepository(session).record(
                    request,
                    action="pipeline.run",
                    resource_type="pipeline_execution",
                    resource_id=execution_id,
                    outcome="failure",
                    details={
                        "plant_id": str(plant_id),
                        "target_date": target_date.isoformat(),
                        "error_code": type(exc).__name__,
                    },
                )
                await session.commit()
                message = "pipeline execution failed"
                if scoped.explicit:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=message,
                    ) from exc
                items.append(
                    FanoutItem(
                        plant_id=plant_id,
                        plant_name=plant_name,
                        outcome="failed",
                        error=error_detail(exc, message=message),
                        result=None,
                    )
                )
                continue
            else:
                items.append(
                    FanoutItem(
                        plant_id=plant_id,
                        plant_name=plant_name,
                        outcome="succeeded",
                        error=None,
                        result=_run_result_payload(result),
                    )
                )

    return fanout_envelope(items)


@router.get("/status/latest", status_code=status.HTTP_200_OK)
async def latest_pipeline_status(scoped: AdminPlantFanout) -> dict[str, object]:
    items: list[FanoutItem] = []
    for plant_id in scoped.plant_ids:
        scoped.principal.require_plant_access(plant_id)  # ADR-069 § E.11.4: defensive
        async with SessionFactory() as session:
            await set_principal_context(session, scoped.principal)
            plant_name = await fetch_plant_name(session, plant_id)
            snapshot = await get_latest_pipeline_execution(session, plant_id=plant_id)
        if snapshot is None:
            if scoped.explicit:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="pipeline execution not found",
                )
            items.append(
                FanoutItem(
                    plant_id=plant_id,
                    plant_name=plant_name,
                    outcome="skipped",
                    error=None,
                    result=None,
                )
            )
            continue
        items.append(
            FanoutItem(
                plant_id=plant_id,
                plant_name=plant_name,
                outcome="succeeded",
                error=None,
                result=_status_payload(snapshot),
            )
        )

    return fanout_envelope(items)
