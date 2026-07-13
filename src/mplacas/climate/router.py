from __future__ import annotations

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status

from mplacas.climate.collection_service import (
    ClimateCollectionError,
    collect_and_persist_daily_climate,
)
from mplacas.climate.open_meteo import OpenMeteoHistoricalProvider, OpenMeteoProviderError
from mplacas.core.config import get_settings
from mplacas.core.security import require_operations_key
from mplacas.db.session import SessionFactory

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/climate",
    tags=["climate"],
    dependencies=[Depends(require_operations_key)],
)


@router.post("/collect", status_code=status.HTTP_200_OK)
async def collect_climate(
    plant_id: uuid.UUID,
    start_date: date,
    end_date: date,
) -> dict[str, object]:
    settings = get_settings()
    provider = OpenMeteoHistoricalProvider(
        base_url=str(settings.climate_archive_base_url),
        timeout_seconds=settings.request_timeout_seconds,
    )
    try:
        async with SessionFactory() as session:
            result = await collect_and_persist_daily_climate(
                session,
                plant_id=plant_id,
                provider=provider,
                start_date=start_date,
                end_date=end_date,
                maximum_days=settings.climate_maximum_backfill_days,
            )
            await session.commit()
    except ClimateCollectionError as exc:
        logger.info(
            "climate_collection_rejected",
            extra={
                "plant_id": str(plant_id),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "error_code": type(exc).__name__.upper(),
            },
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OpenMeteoProviderError as exc:
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
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="weather provider is unavailable or returned invalid data",
        ) from exc

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
        },
    )
    return {
        "plant_id": str(result.plant_id),
        "start_date": result.start_date,
        "end_date": result.end_date,
        "received": result.received,
        "persistence": {
            "inserted": result.persistence.inserted,
            "updated": result.persistence.updated,
            "unchanged": result.persistence.unchanged,
        },
        "provider": OpenMeteoHistoricalProvider.SOURCE,
    }
