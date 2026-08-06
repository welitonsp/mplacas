from __future__ import annotations

import hashlib
import logging
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, Request, status

from mplacas.audit.repository import AuditEventRepository
from mplacas.alerts.models import AlertSeverity
from mplacas.alerts.operations import run_operational_alert_pipeline
from mplacas.alerts.telegram import TelegramAlertProvider
from mplacas.core.config import get_settings
from mplacas.core.fanout import FanoutItem, error_detail, fanout_envelope, fetch_plant_name
from mplacas.core.tenancy import AdminPlantFanout
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_principal_context
from mplacas.photovoltaic.read_service import resolve_expected_daily_production

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/alerts",
    tags=["alerts"],
)


def _destination_ref(chat_id: str) -> str:
    digest = hashlib.sha256(chat_id.encode("utf-8")).hexdigest()[:16]
    return f"telegram:{digest}"


def _result_payload(result, *, minimum_severity: AlertSeverity) -> dict[str, object]:
    return {
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


@router.post("/run", status_code=status.HTTP_200_OK)
async def run_alerts(
    request: Request,
    scoped: AdminPlantFanout,
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

    provider = TelegramAlertProvider(
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
                result = await run_operational_alert_pipeline(
                    session,
                    plant_id=plant_id,
                    provider=provider,
                    destination_ref=_destination_ref(chat_id),
                    expected_daily_production_kwh=per_plant_expected_daily,
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
            except Exception as exc:  # noqa: BLE001 - fan-out isolation, ADR-069 § E.11.4
                await session.rollback()
                if scoped.explicit:
                    # Preserves today's behaviour: nothing was caught here
                    # before, so an unmapped exception propagates unchanged.
                    raise
                logger.warning(
                    "alerts_run_failed_unexpected",
                    extra={
                        "plant_id": str(plant_id),
                        "error_code": type(exc).__name__.upper(),
                    },
                )
                await AuditEventRepository(session).record(
                    request,
                    action="alerts.run",
                    resource_type="plant",
                    resource_id=str(plant_id),
                    outcome="failure",
                    details={"error_code": type(exc).__name__.upper()},
                )
                await session.commit()
                items.append(
                    FanoutItem(
                        plant_id=plant_id,
                        plant_name=plant_name,
                        outcome="failed",
                        error=error_detail(exc, message="unexpected error"),
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
                        result=_result_payload(
                            result, minimum_severity=minimum_severity
                        ),
                    )
                )

    return fanout_envelope(items)
