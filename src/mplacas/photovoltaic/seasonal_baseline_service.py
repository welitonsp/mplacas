from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.photovoltaic.db_models import (
    DailyPvPerformanceRecord,
    DailySolarModelResultRecord,
    SeasonalPvBaselineRecord,
)
from mplacas.photovoltaic.performance import PERFORMANCE_MODEL_VERSION
from mplacas.photovoltaic.seasonal_baseline import (
    BASELINE_METRIC_NATURE,
    BASELINE_MODEL_VERSION,
    CLEAR_SKY_INDEX_NATURE,
    MAD_LIMIT,
    MINIMUM_BASELINE_SAMPLES,
    MINIMUM_CLEAR_SKY_INDEX,
    MINIMUM_COMPARISON_SAMPLES,
    MINIMUM_REPORTING_AVAILABILITY,
    REFERENCE_WINDOW_DAYS,
    InsufficientBaselineData,
    SeasonalPerformanceObservation,
    calculate_seasonal_baseline,
)


@dataclass(frozen=True, slots=True)
class SeasonalBaselineComputationSummary:
    inserted: int
    updated: int
    unchanged: int
    skipped: int
    skip_reason: str | None = None


async def calculate_and_persist_seasonal_baseline(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    observation_date: date,
) -> SeasonalBaselineComputationSummary:
    """Build an idempotent baseline snapshot from version-compatible daily PR rows."""
    rows = (
        await session.execute(
            select(DailyPvPerformanceRecord, DailySolarModelResultRecord)
            .join(
                DailySolarModelResultRecord,
                and_(
                    DailySolarModelResultRecord.plant_id
                    == DailyPvPerformanceRecord.plant_id,
                    DailySolarModelResultRecord.observation_date
                    == DailyPvPerformanceRecord.observation_date,
                    DailySolarModelResultRecord.model_version
                    == DailyPvPerformanceRecord.solar_model_version,
                    DailySolarModelResultRecord.climate_source
                    == DailyPvPerformanceRecord.climate_source,
                ),
            )
            .where(
                DailyPvPerformanceRecord.plant_id == plant_id,
                DailyPvPerformanceRecord.observation_date <= observation_date,
                DailyPvPerformanceRecord.performance_model_version
                == PERFORMANCE_MODEL_VERSION,
            )
            .order_by(DailyPvPerformanceRecord.observation_date)
        )
    ).all()
    observations = tuple(
        SeasonalPerformanceObservation(
            observation_date=performance.observation_date,
            poa_irradiation_kwh_m2=solar.poa_irradiation_kwh_m2,
            performance_ratio=performance.performance_ratio,
            temperature_corrected_performance_ratio=(
                performance.temperature_corrected_performance_ratio
            ),
            reporting_availability_ratio=performance.reporting_availability_ratio,
            data_quality_status=performance.data_quality_status,
            quality_flags=tuple(performance.quality_flags),
        )
        for performance, solar in rows
    )
    try:
        result = calculate_seasonal_baseline(
            observations,
            target_date=observation_date,
        )
    except InsufficientBaselineData as exc:
        return SeasonalBaselineComputationSummary(0, 0, 0, 1, str(exc))

    values = {
        "performance_model_version": PERFORMANCE_MODEL_VERSION,
        "metric_nature": BASELINE_METRIC_NATURE,
        "clear_sky_index_nature": CLEAR_SKY_INDEX_NATURE,
        "season_key": result.season_key,
        "reference_start_date": result.reference_start_date,
        "reference_end_date": result.reference_end_date,
        "baseline_sample_count": result.baseline_sample_count,
        "baseline_excluded_count": result.baseline_excluded_count,
        "comparison_start_date": result.comparison_start_date,
        "comparison_sample_count": result.comparison_sample_count,
        "clear_sky_poa_p90_kwh_m2": result.clear_sky_poa_p90_kwh_m2,
        "target_clear_sky_index": result.target_clear_sky_index,
        "baseline_median_performance_ratio": (
            result.baseline_median_performance_ratio
        ),
        "baseline_mad": result.baseline_mad,
        "baseline_q10": result.baseline_q10,
        "baseline_q90": result.baseline_q90,
        "comparison_median_performance_ratio": (
            result.comparison_median_performance_ratio
        ),
        "degradation_percent": result.degradation_percent,
        "annualized_degradation_percent": result.annualized_degradation_percent,
        "degradation_status": result.degradation_status,
        "quality_flags": list(result.quality_flags),
        "assumptions_json": {
            "reference_window_days": str(REFERENCE_WINDOW_DAYS),
            "minimum_baseline_samples": str(MINIMUM_BASELINE_SAMPLES),
            "minimum_comparison_samples": str(MINIMUM_COMPARISON_SAMPLES),
            "minimum_reporting_availability": str(MINIMUM_REPORTING_AVAILABILITY),
            "minimum_clear_sky_index": str(MINIMUM_CLEAR_SKY_INDEX),
            "mad_limit": str(MAD_LIMIT),
            "season_bucket": "CALENDAR_MONTH",
            "future_observations": "EXCLUDED",
        },
    }
    existing = await session.scalar(
        select(SeasonalPvBaselineRecord).where(
            SeasonalPvBaselineRecord.plant_id == plant_id,
            SeasonalPvBaselineRecord.observation_date == observation_date,
            SeasonalPvBaselineRecord.baseline_model_version == BASELINE_MODEL_VERSION,
        )
    )
    if existing is None:
        session.add(
            SeasonalPvBaselineRecord(
                plant_id=plant_id,
                observation_date=observation_date,
                baseline_model_version=BASELINE_MODEL_VERSION,
                **values,
            )
        )
        await session.flush()
        return SeasonalBaselineComputationSummary(1, 0, 0, 0)
    if all(getattr(existing, name) == value for name, value in values.items()):
        return SeasonalBaselineComputationSummary(0, 0, 1, 0)
    for name, value in values.items():
        setattr(existing, name, value)
    await session.flush()
    return SeasonalBaselineComputationSummary(0, 1, 0, 0)
