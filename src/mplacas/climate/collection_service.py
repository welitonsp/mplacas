from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.climate.provider import ClimateProvider
from mplacas.climate.repository import ClimateObservationRepository, ClimateUpsertSummary
from mplacas.db.models import Plant


class ClimateCollectionError(ValueError):
    """Climate collection cannot proceed with the supplied plant or interval."""


@dataclass(frozen=True, slots=True)
class ClimateCollectionResult:
    plant_id: uuid.UUID
    start_date: date
    end_date: date
    received: int
    persistence: ClimateUpsertSummary


async def collect_and_persist_daily_climate(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    provider: ClimateProvider,
    start_date: date,
    end_date: date,
    maximum_days: int = 366,
) -> ClimateCollectionResult:
    if end_date < start_date:
        raise ClimateCollectionError("end date cannot be before start date")
    interval_days = (end_date - start_date).days + 1
    if maximum_days < 1 or interval_days > maximum_days:
        raise ClimateCollectionError("climate collection interval exceeds configured limit")

    plant = await session.get(Plant, plant_id)
    if plant is None:
        raise ClimateCollectionError("plant not found")
    if plant.latitude is None or plant.longitude is None:
        raise ClimateCollectionError("plant geographic coordinates are not configured")

    latitude = float(plant.latitude)
    longitude = float(plant.longitude)
    if not -90 <= latitude <= 90:
        raise ClimateCollectionError("plant latitude is outside the valid range")
    if not -180 <= longitude <= 180:
        raise ClimateCollectionError("plant longitude is outside the valid range")

    observations = await provider.daily_observations(
        latitude=latitude,
        longitude=longitude,
        start_date=start_date,
        end_date=end_date,
    )
    for observation in observations:
        if not start_date <= observation.observation_date <= end_date:
            raise ClimateCollectionError(
                "provider returned an observation outside the requested interval"
            )

    persistence = await ClimateObservationRepository(session).upsert_many(
        plant_id=plant_id,
        observations=observations,
    )
    return ClimateCollectionResult(
        plant_id=plant_id,
        start_date=start_date,
        end_date=end_date,
        received=len(observations),
        persistence=persistence,
    )
