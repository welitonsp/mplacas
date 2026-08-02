from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.db.models import Plant
from mplacas.photovoltaic.db_models import (
    DailyPvLossAssessmentRecord,
    DailyPvPerformanceRecord,
    SeasonalPvBaselineRecord,
)
from mplacas.photovoltaic.loss_taxonomy import (
    LOSS_TAXONOMY_MODEL_VERSION,
    DailyLossTaxonomyInput,
    classify_daily_losses,
)
from mplacas.photovoltaic.performance import PERFORMANCE_MODEL_VERSION
from mplacas.photovoltaic.seasonal_baseline import BASELINE_MODEL_VERSION


@dataclass(frozen=True, slots=True)
class LossTaxonomyComputationSummary:
    inserted: int
    updated: int
    unchanged: int
    skipped: int
    skip_reason: str | None = None


async def classify_and_persist_daily_losses(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    observation_date: date,
) -> LossTaxonomyComputationSummary:
    """Persist all taxonomy categories, including explicitly non-assessable ones."""
    plant = await session.get(Plant, plant_id)
    if plant is None:
        return LossTaxonomyComputationSummary(0, 0, 0, 1, "plant not found")

    performance_rows = (
        await session.scalars(
            select(DailyPvPerformanceRecord).where(
                DailyPvPerformanceRecord.plant_id == plant_id,
                DailyPvPerformanceRecord.observation_date == observation_date,
                DailyPvPerformanceRecord.performance_model_version
                == PERFORMANCE_MODEL_VERSION,
            )
        )
    ).all()
    if not performance_rows:
        return LossTaxonomyComputationSummary(0, 0, 0, 1, "performance result unavailable")
    if len(performance_rows) > 1:
        return LossTaxonomyComputationSummary(
            0, 0, 0, 1, "performance solar model version is ambiguous"
        )
    performance = performance_rows[0]
    baseline = await session.scalar(
        select(SeasonalPvBaselineRecord).where(
            SeasonalPvBaselineRecord.plant_id == plant_id,
            SeasonalPvBaselineRecord.observation_date == observation_date,
            SeasonalPvBaselineRecord.baseline_model_version == BASELINE_MODEL_VERSION,
        )
    )
    climate_rows = (
        await session.scalars(
            select(DailyClimateObservationRecord).where(
                DailyClimateObservationRecord.plant_id == plant_id,
                DailyClimateObservationRecord.observation_date
                >= observation_date - timedelta(days=29),
                DailyClimateObservationRecord.observation_date <= observation_date,
                DailyClimateObservationRecord.source == performance.climate_source,
                DailyClimateObservationRecord.precipitation_mm.is_not(None),
            )
        )
    ).all()
    dry_days = sum(
        1
        for row in climate_rows
        if row.precipitation_mm is not None and row.precipitation_mm <= 0.5
    )
    assessments = classify_daily_losses(
        DailyLossTaxonomyInput(
            performance_ratio=performance.performance_ratio,
            temperature_corrected_performance_ratio=(
                performance.temperature_corrected_performance_ratio
            ),
            reporting_availability_ratio=performance.reporting_availability_ratio,
            data_quality_status=performance.data_quality_status,
            measured_energy_kwh=performance.measured_energy_kwh,
            poa_irradiation_kwh_m2=performance.poa_irradiation_kwh_m2,
            dc_capacity_kwp=performance.dc_capacity_kwp,
            ac_capacity_kw=plant.ac_capacity_kw,
            baseline_median_performance_ratio=(
                baseline.baseline_median_performance_ratio if baseline is not None else None
            ),
            baseline_degradation_status=(
                baseline.degradation_status if baseline is not None else None
            ),
            baseline_degradation_percent=(
                baseline.degradation_percent if baseline is not None else None
            ),
            target_clear_sky_index=(
                baseline.target_clear_sky_index if baseline is not None else None
            ),
            precipitation_sample_days=len(climate_rows),
            dry_days=dry_days,
        )
    )
    existing_records = {
        row.category: row
        for row in (
            await session.scalars(
                select(DailyPvLossAssessmentRecord).where(
                    DailyPvLossAssessmentRecord.plant_id == plant_id,
                    DailyPvLossAssessmentRecord.observation_date == observation_date,
                    DailyPvLossAssessmentRecord.taxonomy_model_version
                    == LOSS_TAXONOMY_MODEL_VERSION,
                )
            )
        ).all()
    }
    inserted = updated = unchanged = 0
    for assessment in assessments:
        values = {
            "evidence_level": assessment.evidence_level.value,
            "performance_model_version": PERFORMANCE_MODEL_VERSION,
            "baseline_model_version": (
                BASELINE_MODEL_VERSION if baseline is not None else None
            ),
            "estimated_loss_percent": assessment.estimated_loss_percent,
            "evidence_codes": list(assessment.evidence_codes),
            "limitation": assessment.limitation,
            "assumptions_json": {
                "input_granularity": "DAILY",
                "technical_availability": "NOT_MEASURED",
                "interval_power": "UNAVAILABLE",
                "dry_day_precipitation_threshold_mm": "0.5",
            },
        }
        existing = existing_records.get(assessment.category.value)
        if existing is None:
            session.add(
                DailyPvLossAssessmentRecord(
                    plant_id=plant_id,
                    observation_date=observation_date,
                    category=assessment.category.value,
                    taxonomy_model_version=LOSS_TAXONOMY_MODEL_VERSION,
                    **values,
                )
            )
            inserted += 1
        elif all(getattr(existing, name) == value for name, value in values.items()):
            unchanged += 1
        else:
            for name, value in values.items():
                setattr(existing, name, value)
            updated += 1
    await session.flush()
    return LossTaxonomyComputationSummary(inserted, updated, unchanged, 0)
