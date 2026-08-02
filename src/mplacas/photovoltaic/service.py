from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.climate.models import DailyClimateObservation
from mplacas.db.models import Plant
from mplacas.photovoltaic.db_models import DailySolarModelResultRecord
from mplacas.photovoltaic.poa import (
    MODEL_ASSUMPTIONS,
    DailySolarModelInput,
    DailySolarModelResult,
    calculate_daily_solar_model,
)


@dataclass(frozen=True, slots=True)
class SolarProjectionSummary:
    inserted: int
    updated: int
    unchanged: int
    skipped: int
    skip_reason: str | None = None


async def project_daily_climate_observations(
    session: AsyncSession,
    *,
    plant: Plant,
    observations: tuple[DailyClimateObservation, ...],
) -> SolarProjectionSummary:
    """Calculate and upsert projections when the plant has sufficient inputs."""
    missing_configuration = [
        name
        for name, value in (
            ("latitude", plant.latitude),
            ("array_tilt_degrees", plant.array_tilt_degrees),
            ("array_azimuth_degrees", plant.array_azimuth_degrees),
            ("module_technology", plant.module_technology),
        )
        if value is None
    ]
    if missing_configuration:
        return SolarProjectionSummary(
            inserted=0,
            updated=0,
            unchanged=0,
            skipped=len(observations),
            skip_reason="missing plant configuration: " + ", ".join(missing_configuration),
        )
    assert plant.latitude is not None
    assert plant.array_tilt_degrees is not None
    assert plant.array_azimuth_degrees is not None
    assert plant.module_technology is not None

    results: list[tuple[DailySolarModelResult, DailyClimateObservation]] = []
    skipped = 0
    for observation in observations:
        if observation.irradiation_kwh_m2 is None:
            skipped += 1
            continue
        result = calculate_daily_solar_model(
            DailySolarModelInput(
                observation_date=observation.observation_date,
                latitude_degrees=plant.latitude,
                ghi_kwh_m2=observation.irradiation_kwh_m2,
                array_tilt_degrees=plant.array_tilt_degrees,
                array_azimuth_degrees=plant.array_azimuth_degrees,
                module_technology=plant.module_technology,
                climate_source=observation.source,
                ambient_temperature_c=observation.temperature_mean_c,
            )
        )
        results.append((result, observation))

    if not results:
        return SolarProjectionSummary(0, 0, 0, skipped, "GHI unavailable")
    return await _upsert_results(
        session,
        plant_id=plant.id,
        latitude=plant.latitude,
        tilt=plant.array_tilt_degrees,
        azimuth=plant.array_azimuth_degrees,
        module_technology=plant.module_technology,
        results=results,
        skipped=skipped,
    )


async def _upsert_results(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    latitude,
    tilt,
    azimuth,
    module_technology: str,
    results: list[tuple[DailySolarModelResult, DailyClimateObservation]],
    skipped: int,
) -> SolarProjectionSummary:
    identities = {
        (result.observation_date, result.climate_source, result.model_version)
        for result, _observation in results
    }
    dates = {identity[0] for identity in identities}
    sources = {identity[1] for identity in identities}
    versions = {identity[2] for identity in identities}
    existing_rows = (
        await session.scalars(
            select(DailySolarModelResultRecord).where(
                DailySolarModelResultRecord.plant_id == plant_id,
                DailySolarModelResultRecord.observation_date.in_(dates),
                DailySolarModelResultRecord.climate_source.in_(sources),
                DailySolarModelResultRecord.model_version.in_(versions),
            )
        )
    ).all()
    existing = {
        (row.observation_date, row.climate_source, row.model_version): row
        for row in existing_rows
    }
    inserted = 0
    updated = 0
    unchanged = 0
    for result, observation in results:
        key = (result.observation_date, result.climate_source, result.model_version)
        values = _record_values(
            result,
            observation=observation,
            latitude=latitude,
            tilt=tilt,
            azimuth=azimuth,
            module_technology=module_technology,
        )
        record = existing.get(key)
        if record is None:
            session.add(DailySolarModelResultRecord(plant_id=plant_id, **values))
            inserted += 1
            continue
        if all(getattr(record, name) == value for name, value in values.items()):
            unchanged += 1
            continue
        for name, value in values.items():
            setattr(record, name, value)
        updated += 1
    await session.flush()
    return SolarProjectionSummary(inserted, updated, unchanged, skipped)


def _record_values(
    result: DailySolarModelResult,
    *,
    observation: DailyClimateObservation,
    latitude,
    tilt,
    azimuth,
    module_technology: str,
) -> dict:
    return {
        "observation_date": result.observation_date,
        "climate_source": result.climate_source,
        "model_version": result.model_version,
        "latitude_degrees": latitude,
        "array_tilt_degrees": tilt,
        "array_azimuth_degrees": azimuth,
        "module_technology": module_technology,
        "ghi_kwh_m2": result.ghi_kwh_m2,
        "poa_irradiation_kwh_m2": result.poa_irradiation_kwh_m2,
        "beam_horizontal_kwh_m2": result.beam_horizontal_kwh_m2,
        "diffuse_horizontal_kwh_m2": result.diffuse_horizontal_kwh_m2,
        "extraterrestrial_horizontal_kwh_m2": result.extraterrestrial_horizontal_kwh_m2,
        "ambient_temperature_c": observation.temperature_mean_c,
        "cell_temperature_c": result.cell_temperature_c,
        "temperature_coefficient_per_c": result.temperature_coefficient_per_c,
        "temperature_factor": result.temperature_factor,
        "temperature_adjusted_poa_equivalent_kwh_m2": (
            result.temperature_adjusted_poa_equivalent_kwh_m2
        ),
        "quality_flags": list(result.quality_flags),
        "assumptions_json": dict(MODEL_ASSUMPTIONS),
    }
