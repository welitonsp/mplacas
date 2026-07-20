from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

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

        seen: set[tuple[date, str]] = set()
        validated: list[tuple[DailyClimateObservation, str]] = []
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
            validated.append((observation, source))

        if not validated:
            return ClimateUpsertSummary(inserted=0, updated=0, unchanged=0)

        # Single query loads all existing records for the batch dates/sources.
        dates = [obs.observation_date for obs, _ in validated]
        sources = list({src for _, src in validated})
        existing_records = (
            await self._session.scalars(
                select(DailyClimateObservationRecord).where(
                    DailyClimateObservationRecord.plant_id == plant_id,
                    DailyClimateObservationRecord.observation_date.in_(dates),
                    DailyClimateObservationRecord.source.in_(sources),
                )
            )
        ).all()
        existing_map: dict[tuple[date, str], DailyClimateObservationRecord] = {
            (r.observation_date, r.source): r for r in existing_records
        }

        inserted = 0
        updated = 0
        unchanged = 0

        for observation, source in validated:
            new_values = (
                observation.irradiation_kwh_m2,
                observation.cloud_cover_percent,
                observation.precipitation_mm,
            )
            existing = existing_map.get((observation.observation_date, source))
            if existing is None:
                self._session.add(
                    DailyClimateObservationRecord(
                        plant_id=plant_id,
                        observation_date=observation.observation_date,
                        irradiation_kwh_m2=new_values[0],
                        cloud_cover_percent=new_values[1],
                        precipitation_mm=new_values[2],
                        source=source,
                    )
                )
                inserted += 1
                continue

            current_values = (
                existing.irradiation_kwh_m2,
                existing.cloud_cover_percent,
                existing.precipitation_mm,
            )
            if current_values == new_values:
                unchanged += 1
                continue
            existing.irradiation_kwh_m2 = new_values[0]
            existing.cloud_cover_percent = new_values[1]
            existing.precipitation_mm = new_values[2]
            updated += 1

        await self._session.flush()
        return ClimateUpsertSummary(inserted=inserted, updated=updated, unchanged=unchanged)
