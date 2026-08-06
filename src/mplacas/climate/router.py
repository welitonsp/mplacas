from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Request, status

from mplacas.audit.repository import AuditEventRepository
from mplacas.climate.collection_service import (
    ClimateCollectionError,
    collect_and_persist_daily_climate,
)
from mplacas.climate.open_meteo import OpenMeteoHistoricalProvider, OpenMeteoProviderError
from mplacas.core.config import get_settings
from mplacas.core.fanout import FanoutItem, error_detail, fanout_envelope, fetch_plant_name
from mplacas.core.tenancy import AdminPlantFanout
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_principal_context

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/climate",
    tags=["climate"],
)


def _result_payload(result) -> dict[str, object]:
    return {
        "start_date": result.start_date,
        "end_date": result.end_date,
        "received": result.received,
        "persistence": {
            "inserted": result.persistence.inserted,
            "updated": result.persistence.updated,
            "unchanged": result.persistence.unchanged,
        },
        "solar_projection": {
            "inserted": result.solar_projection.inserted,
            "updated": result.solar_projection.updated,
            "unchanged": result.solar_projection.unchanged,
            "skipped": result.solar_projection.skipped,
            "skip_reason": result.solar_projection.skip_reason,
        },
        "provider": OpenMeteoHistoricalProvider.SOURCE,
    }


@router.post("/collect", status_code=status.HTTP_200_OK)
async def collect_climate(
    request: Request,
    scoped: AdminPlantFanout,
    start_date: date,
    end_date: date,
) -> dict[str, object]:
    settings = get_settings()
    provider = OpenMeteoHistoricalProvider(
        base_url=str(settings.climate_archive_base_url),
        timeout_seconds=settings.request_timeout_seconds,
    )

    items: list[FanoutItem] = []
    for plant_id in scoped.plant_ids:
        scoped.principal.require_plant_access(plant_id)  # ADR-069 § E.11.4: defensive
        async with SessionFactory() as session:  # sessão nova por usina
            await set_principal_context(session, scoped.principal)
            plant_name = await fetch_plant_name(session, plant_id)
            try:
                result = await collect_and_persist_daily_climate(
                    session,
                    plant_id=plant_id,
                    provider=provider,
                    start_date=start_date,
                    end_date=end_date,
                    maximum_days=settings.climate_maximum_backfill_days,
                )
                await AuditEventRepository(session).record(
                    request,
                    action="climate.collect",
                    resource_type="plant",
                    resource_id=str(result.plant_id),
                    outcome="SUCCEEDED",
                    details={
                        "start_date": result.start_date.isoformat(),
                        "end_date": result.end_date.isoformat(),
                        "provider": OpenMeteoHistoricalProvider.SOURCE,
                        "received": result.received,
                        "inserted": result.persistence.inserted,
                        "updated": result.persistence.updated,
                        "unchanged": result.persistence.unchanged,
                        "solar_projected": (
                            result.solar_projection.inserted
                            + result.solar_projection.updated
                        ),
                        "solar_skipped": result.solar_projection.skipped,
                    },
                )
                await session.commit()
            except ClimateCollectionError as exc:
                await session.rollback()
                logger.info(
                    "climate_collection_rejected",
                    extra={
                        "plant_id": str(plant_id),
                        "start_date": start_date.isoformat(),
                        "end_date": end_date.isoformat(),
                        "error_code": type(exc).__name__.upper(),
                    },
                )
                message = str(exc)
                if scoped.explicit:
                    raise HTTPException(status_code=422, detail=message) from exc
                await AuditEventRepository(session).record(
                    request,
                    action="climate.collect",
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
                        error=error_detail(exc, message=message),
                        result=None,
                    )
                )
                continue
            except OpenMeteoProviderError as exc:
                await session.rollback()
                logger.warning(
                    "climate_provider_failed",
                    extra={
                        "plant_id": str(plant_id),
                        "start_date": start_date.isoformat(),
                        "end_date": end_date.isoformat(),
                        "provider": OpenMeteoHistoricalProvider.SOURCE,
                        "error_code": type(exc).__name__.upper(),
                    },
                )
                message = "weather provider is unavailable or returned invalid data"
                if scoped.explicit:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY, detail=message
                    ) from exc
                await AuditEventRepository(session).record(
                    request,
                    action="climate.collect",
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
                        error=error_detail(exc, message=message),
                        result=None,
                    )
                )
                continue
            except Exception as exc:  # noqa: BLE001 - fan-out isolation, see ADR-069 § E.11.4
                await session.rollback()
                if scoped.explicit:
                    # Preserves today's behaviour: an unmapped exception was
                    # never caught here before, so it propagates unchanged.
                    raise
                logger.warning(
                    "climate_collection_failed_unexpected",
                    extra={
                        "plant_id": str(plant_id),
                        "error_code": type(exc).__name__.upper(),
                    },
                )
                await AuditEventRepository(session).record(
                    request,
                    action="climate.collect",
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
                logger.info(
                    "climate_collection_completed",
                    extra={
                        "plant_id": str(result.plant_id),
                        "start_date": result.start_date.isoformat(),
                        "end_date": result.end_date.isoformat(),
                        "provider": OpenMeteoHistoricalProvider.SOURCE,
                        "received": result.received,
                        "inserted": result.persistence.inserted,
                        "updated": result.persistence.updated,
                        "unchanged": result.persistence.unchanged,
                        "solar_projected": (
                            result.solar_projection.inserted
                            + result.solar_projection.updated
                        ),
                        "solar_skipped": result.solar_projection.skipped,
                    },
                )
                items.append(
                    FanoutItem(
                        plant_id=plant_id,
                        plant_name=plant_name,
                        outcome="succeeded",
                        error=None,
                        result=_result_payload(result),
                    )
                )

    return fanout_envelope(items)
