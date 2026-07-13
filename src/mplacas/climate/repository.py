from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.climate.models import DailyClimateObservation
from mplacas.db.models import Plant


@dataclass(frozen=True, slots=True)
class ClimateUpsertSummary:
    inserted: int
    updated: int
    unchanged: int


class ClimateObservationRepository:
    """Persist daily climate observations with deterministic idempotency."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_many(
        self,
        *,
        plant_id: uuid.UUID,
        observations: tuple[DailyClimateObservation, ...],
    ) -> ClimateUpsertSummary:
        if await self._session.get(Plant, plant_id) is None:
            raise ValueError("plant not found")

        inserted = 0
        updated = 0
        unchanged = 0
        seen: set[tuple[object, str]] = set()

        for observation in observations:
            observation.validate()
            source = observation.source.strip()
            if not source:
                raise ValueError("climate observation source cannot be blank")
            if len(source) > 40:
                raise ValueError("climate observation source is too long")
            key = (observation.observation_date, source)
            if key in seen:
                raise ValueError("duplicate climate observation in collection batch")
            seen.add(key)

            existing = await self._session.scalar(
                select(DailyClimateObservationRecord).where(
                    DailyClimateObservationRecord.plant_id == plant_id,
                    DailyClimateObservationRecord.observation_date
                    == observation.observation_date,
                    DailyClimateObservationRecord.source == source,
                )
            )
            values = (
                observation.irradiation_kwh_m2,
                observation.cloud_cover_percent,
                observation.precipitation_mm,
            )
            if existing is None:
                self._session.add(
                    DailyClimateObservationRecord(
                        plant_id=plant_id,
                        observation_date=observation.observation_date,
                        irradiation_kwh_m2=values[0],
                        cloud_cover_percent=values[1],
                        precipitation_mm=values[2],
                        source=source,
                    )
                )
                inserted += 1
                continue

            current = (
                existing.irradiation_kwh_m2,
                existing.cloud_cover_percent,
                existing.precipitation_mm,
            )
            if current == values:
                unchanged += 1
                continue
            existing.irradiation_kwh_m2 = values[0]
            existing.cloud_cover_percent = values[1]
            existing.precipitation_mm = values[2]
            updated += 1

        await self._session.flush()
        return ClimateUpsertSummary(
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
        )
