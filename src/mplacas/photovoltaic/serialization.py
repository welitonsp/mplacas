"""Pure dict serialization for the photovoltaic read router (ADR-065).

No I/O here — every function takes an already-loaded ORM record and returns a
plain ``dict``. ``Decimal`` is serialized as ``str`` to avoid precision loss,
dates use ISO-8601, and nullable fields are always present in the output
(never omitted), even when their value is ``None``.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from mplacas.photovoltaic.db_models import (
    DailyPvLossAssessmentRecord,
    DailyPvPerformanceRecord,
    SeasonalPvBaselineRecord,
)

# `seasonal_pv_baseline_results` and `daily_pv_loss_assessments` do not carry a
# persisted `units_json` column (unlike `daily_pv_performance_results`, see
# `performance.py:PERFORMANCE_UNITS`), so the units they report are a static
# block defined here (ADR-065 section 3).
BASELINE_UNITS: dict[str, str] = {
    "clear_sky_poa": "kWh/m2",
    "target_clear_sky_index": "ratio",
    "baseline_median_performance_ratio": "ratio",
    "baseline_mad": "ratio",
    "baseline_q10": "ratio",
    "baseline_q90": "ratio",
    "comparison_median_performance_ratio": "ratio",
    "degradation": "percent",
    "annualized_degradation": "percent",
}

LOSS_UNITS: dict[str, str] = {
    "estimated_loss": "percent",
}


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _datetime(value: datetime) -> str:
    return value.isoformat()


def serialize_performance(record: DailyPvPerformanceRecord) -> dict[str, object]:
    """Serialize one ``DailyPvPerformanceRecord`` per ADR-065 section 4.

    ``units`` echoes the record's own ``units_json`` — not the
    ``PERFORMANCE_UNITS`` constant — so an old record keeps describing the
    unit set it was persisted with.
    """
    return {
        "observation_date": _date(record.observation_date),
        "measured_energy_kwh": _decimal(record.measured_energy_kwh),
        "dc_capacity_kwp": _decimal(record.dc_capacity_kwp),
        "poa_irradiation_kwh_m2": _decimal(record.poa_irradiation_kwh_m2),
        "final_yield_kwh_per_kwp": _decimal(record.final_yield_kwh_per_kwp),
        "reference_yield_hours": _decimal(record.reference_yield_hours),
        "performance_ratio": _decimal(record.performance_ratio),
        "temperature_corrected_performance_ratio": _decimal(
            record.temperature_corrected_performance_ratio
        ),
        "reporting_availability_ratio": _decimal(record.reporting_availability_ratio),
        "reporting_device_count": record.reporting_device_count,
        "configured_device_count": record.configured_device_count,
        "reporting_capacity_kwp": _decimal(record.reporting_capacity_kwp),
        "configured_device_capacity_kwp": _decimal(record.configured_device_capacity_kwp),
        "data_quality_status": record.data_quality_status,
        "quality_flags": list(record.quality_flags),
        "uncertainty_percent": _decimal(record.uncertainty_percent),
        "performance_ratio_nature": record.performance_ratio_nature,
        "availability_nature": record.availability_nature,
        "uncertainty_nature": record.uncertainty_nature,
        "climate_source": record.climate_source,
        "solar_model_version": record.solar_model_version,
        "performance_model_version": record.performance_model_version,
        "units": dict(record.units_json),
        "calculated_at": _datetime(record.calculated_at),
    }


def serialize_baseline(record: SeasonalPvBaselineRecord) -> dict[str, object]:
    """Serialize one ``SeasonalPvBaselineRecord`` per ADR-065 section 4."""
    return {
        "observation_date": _date(record.observation_date),
        "season_key": record.season_key,
        "reference_start_date": _date(record.reference_start_date),
        "reference_end_date": _date(record.reference_end_date),
        "baseline_sample_count": record.baseline_sample_count,
        "baseline_excluded_count": record.baseline_excluded_count,
        "comparison_start_date": _date(record.comparison_start_date),
        "comparison_sample_count": record.comparison_sample_count,
        "clear_sky_poa_p90_kwh_m2": _decimal(record.clear_sky_poa_p90_kwh_m2),
        "target_clear_sky_index": _decimal(record.target_clear_sky_index),
        "baseline_median_performance_ratio": _decimal(
            record.baseline_median_performance_ratio
        ),
        "baseline_mad": _decimal(record.baseline_mad),
        "baseline_q10": _decimal(record.baseline_q10),
        "baseline_q90": _decimal(record.baseline_q90),
        "comparison_median_performance_ratio": _decimal(
            record.comparison_median_performance_ratio
        ),
        "degradation_percent": _decimal(record.degradation_percent),
        "annualized_degradation_percent": _decimal(record.annualized_degradation_percent),
        "degradation_status": record.degradation_status,
        "metric_nature": record.metric_nature,
        "clear_sky_index_nature": record.clear_sky_index_nature,
        "quality_flags": list(record.quality_flags),
        "assumptions": dict(record.assumptions_json),
        "units": dict(BASELINE_UNITS),
        "calculated_at": _datetime(record.calculated_at),
    }


def serialize_loss_assessment(record: DailyPvLossAssessmentRecord) -> dict[str, object]:
    """Serialize one ``DailyPvLossAssessmentRecord`` per ADR-065 section 4.

    ``limitation`` and ``evidence_codes`` are always included, never omitted —
    they carry the epistemic caveat even for ``NOT_ASSESSABLE`` categories.
    """
    return {
        "category": record.category,
        "evidence_level": record.evidence_level,
        "estimated_loss_percent": _decimal(record.estimated_loss_percent),
        "evidence_codes": list(record.evidence_codes),
        "limitation": record.limitation,
        "taxonomy_model_version": record.taxonomy_model_version,
        "baseline_model_version": record.baseline_model_version,
    }
