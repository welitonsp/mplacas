from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from mplacas.photovoltaic.db_models import (
    DailyPvLossAssessmentRecord,
    DailyPvPerformanceRecord,
    SeasonalPvBaselineRecord,
)
from mplacas.photovoltaic.serialization import (
    BASELINE_UNITS,
    LOSS_UNITS,
    serialize_baseline,
    serialize_loss_assessment,
    serialize_performance,
)


def _performance_record(**overrides: object) -> DailyPvPerformanceRecord:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "plant_id": uuid.uuid4(),
        "observation_date": date(2026, 7, 1),
        "solar_model_version": "MPLACAS_POA_DAILY_ERBS_ISOTROPIC_V1",
        "performance_model_version": "MPLACAS_IEC61724_DAILY_PR_V1",
        "climate_source": "OPEN_METEO_ARCHIVE",
        "performance_ratio_nature": "IEC_61724_STYLE_AC_PR_MODELED_POA",
        "availability_nature": "CAPACITY_WEIGHTED_DAILY_REPORTING_PROXY",
        "uncertainty_percent": None,
        "uncertainty_nature": "NOT_QUANTIFIED_SENSOR_CLASSES_UNAVAILABLE",
        "measured_energy_kwh": Decimal("123.456"),
        "dc_capacity_kwp": Decimal("100.000"),
        "poa_irradiation_kwh_m2": Decimal("5.500"),
        "final_yield_kwh_per_kwp": Decimal("1.235"),
        "reference_yield_hours": Decimal("5.500"),
        "performance_ratio": Decimal("0.8500"),
        "temperature_corrected_performance_ratio": Decimal("0.8700"),
        "reporting_availability_ratio": Decimal("0.9800"),
        "reporting_device_count": 3,
        "configured_device_count": 3,
        "reporting_capacity_kwp": Decimal("100.000"),
        "configured_device_capacity_kwp": Decimal("100.000"),
        "data_quality_status": "FINAL",
        "quality_flags": ["POA_MODELED_NOT_MEASURED", "UNCERTAINTY_NOT_QUANTIFIED"],
        "units_json": {
            "measured_energy": "kWh_AC",
            "dc_capacity": "kWp_STC",
            "poa_irradiation": "kWh/m2",
            "final_yield": "kWh/kWp",
            "reference_yield": "h",
            "performance_ratio": "ratio",
            "availability": "ratio",
        },
        "assumptions_json": {"reference_irradiance_kw_m2": "1.000"},
        "calculated_at": datetime(2026, 7, 2, 3, 0, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return DailyPvPerformanceRecord(**values)


def _baseline_record(**overrides: object) -> SeasonalPvBaselineRecord:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "plant_id": uuid.uuid4(),
        "observation_date": date(2027, 7, 1),
        "baseline_model_version": "MPLACAS_SEASONAL_PR_BASELINE_V1",
        "performance_model_version": "MPLACAS_IEC61724_DAILY_PR_V1",
        "metric_nature": "TEMPERATURE_CORRECTED_PR_PREFERRED",
        "clear_sky_index_nature": "EMPIRICAL_SEASONAL_POA_P90",
        "season_key": "MONTH_07",
        "reference_start_date": date(2026, 7, 1),
        "reference_end_date": date(2027, 7, 1),
        "baseline_sample_count": 20,
        "baseline_excluded_count": 2,
        "comparison_start_date": date(2027, 7, 2),
        "comparison_sample_count": 10,
        "clear_sky_poa_p90_kwh_m2": Decimal("6.500"),
        "target_clear_sky_index": Decimal("0.9500"),
        "baseline_median_performance_ratio": Decimal("0.8500"),
        "baseline_mad": Decimal("0.0100"),
        "baseline_q10": Decimal("0.8300"),
        "baseline_q90": Decimal("0.8700"),
        "comparison_median_performance_ratio": Decimal("0.8000"),
        "degradation_percent": Decimal("-5.88"),
        "annualized_degradation_percent": Decimal("-5.90"),
        "degradation_status": "DEGRADED",
        "quality_flags": ["BASELINE_REFERENCE_WINDOW_FROZEN", "SEASONAL_MONTH_BUCKET"],
        "assumptions_json": {"reference_window_days": "366"},
        "calculated_at": datetime(2027, 7, 2, 3, 0, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return SeasonalPvBaselineRecord(**values)


def _loss_record(**overrides: object) -> DailyPvLossAssessmentRecord:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "plant_id": uuid.uuid4(),
        "observation_date": date(2026, 7, 1),
        "category": "SHADING",
        "evidence_level": "NOT_ASSESSABLE",
        "taxonomy_model_version": "MPLACAS_DAILY_LOSS_TAXONOMY_V1",
        "performance_model_version": "MPLACAS_IEC61724_DAILY_PR_V1",
        "baseline_model_version": None,
        "estimated_loss_percent": None,
        "evidence_codes": ["INTERVAL_POWER_AND_SOLAR_GEOMETRY_PROFILE_UNAVAILABLE"],
        "limitation": "daily aggregates cannot distinguish recurring geometric shading",
        "assumptions_json": {"input_granularity": "DAILY"},
        "calculated_at": datetime(2026, 7, 2, 3, 0, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return DailyPvLossAssessmentRecord(**values)


def test_serialize_performance_produces_expected_shape() -> None:
    record = _performance_record()
    payload = serialize_performance(record)

    assert payload == {
        "observation_date": "2026-07-01",
        "measured_energy_kwh": "123.456",
        "dc_capacity_kwp": "100.000",
        "poa_irradiation_kwh_m2": "5.500",
        "final_yield_kwh_per_kwp": "1.235",
        "reference_yield_hours": "5.500",
        "performance_ratio": "0.8500",
        "temperature_corrected_performance_ratio": "0.8700",
        "reporting_availability_ratio": "0.9800",
        "reporting_device_count": 3,
        "configured_device_count": 3,
        "reporting_capacity_kwp": "100.000",
        "configured_device_capacity_kwp": "100.000",
        "data_quality_status": "FINAL",
        "quality_flags": ["POA_MODELED_NOT_MEASURED", "UNCERTAINTY_NOT_QUANTIFIED"],
        "uncertainty_percent": None,
        "performance_ratio_nature": "IEC_61724_STYLE_AC_PR_MODELED_POA",
        "availability_nature": "CAPACITY_WEIGHTED_DAILY_REPORTING_PROXY",
        "uncertainty_nature": "NOT_QUANTIFIED_SENSOR_CLASSES_UNAVAILABLE",
        "climate_source": "OPEN_METEO_ARCHIVE",
        "solar_model_version": "MPLACAS_POA_DAILY_ERBS_ISOTROPIC_V1",
        "performance_model_version": "MPLACAS_IEC61724_DAILY_PR_V1",
        "units": {
            "measured_energy": "kWh_AC",
            "dc_capacity": "kWp_STC",
            "poa_irradiation": "kWh/m2",
            "final_yield": "kWh/kWp",
            "reference_yield": "h",
            "performance_ratio": "ratio",
            "availability": "ratio",
        },
        "calculated_at": "2026-07-02T03:00:00+00:00",
    }


def test_serialize_performance_keeps_nullable_fields_present_as_null() -> None:
    record = _performance_record(
        temperature_corrected_performance_ratio=None,
        reporting_availability_ratio=None,
        reporting_capacity_kwp=None,
        configured_device_capacity_kwp=None,
        uncertainty_percent=None,
    )
    payload = serialize_performance(record)

    assert payload["temperature_corrected_performance_ratio"] is None
    assert payload["reporting_availability_ratio"] is None
    assert payload["reporting_capacity_kwp"] is None
    assert payload["configured_device_capacity_kwp"] is None
    assert payload["uncertainty_percent"] is None
    assert "temperature_corrected_performance_ratio" in payload
    assert "reporting_availability_ratio" in payload


def test_serialize_performance_echoes_persisted_units_not_the_constant() -> None:
    record = _performance_record(units_json={"measured_energy": "OLD_UNIT_STRING"})
    payload = serialize_performance(record)
    assert payload["units"] == {"measured_energy": "OLD_UNIT_STRING"}


def test_serialize_baseline_produces_expected_shape() -> None:
    record = _baseline_record()
    payload = serialize_baseline(record)

    assert payload["observation_date"] == "2027-07-01"
    assert payload["season_key"] == "MONTH_07"
    assert payload["reference_start_date"] == "2026-07-01"
    assert payload["reference_end_date"] == "2027-07-01"
    assert payload["baseline_sample_count"] == 20
    assert payload["baseline_excluded_count"] == 2
    assert payload["comparison_start_date"] == "2027-07-02"
    assert payload["comparison_sample_count"] == 10
    assert payload["clear_sky_poa_p90_kwh_m2"] == "6.500"
    assert payload["target_clear_sky_index"] == "0.9500"
    assert payload["baseline_median_performance_ratio"] == "0.8500"
    assert payload["baseline_mad"] == "0.0100"
    assert payload["baseline_q10"] == "0.8300"
    assert payload["baseline_q90"] == "0.8700"
    assert payload["comparison_median_performance_ratio"] == "0.8000"
    assert payload["degradation_percent"] == "-5.88"
    assert payload["annualized_degradation_percent"] == "-5.90"
    assert payload["degradation_status"] == "DEGRADED"
    assert payload["metric_nature"] == "TEMPERATURE_CORRECTED_PR_PREFERRED"
    assert payload["clear_sky_index_nature"] == "EMPIRICAL_SEASONAL_POA_P90"
    assert payload["quality_flags"] == [
        "BASELINE_REFERENCE_WINDOW_FROZEN",
        "SEASONAL_MONTH_BUCKET",
    ]
    assert payload["assumptions"] == {"reference_window_days": "366"}
    assert payload["units"] == BASELINE_UNITS
    assert payload["calculated_at"] == "2027-07-02T03:00:00+00:00"


def test_serialize_baseline_keeps_nullable_annualized_degradation_present() -> None:
    record = _baseline_record(
        target_clear_sky_index=None, annualized_degradation_percent=None
    )
    payload = serialize_baseline(record)
    assert "target_clear_sky_index" in payload
    assert payload["target_clear_sky_index"] is None
    assert "annualized_degradation_percent" in payload
    assert payload["annualized_degradation_percent"] is None


def test_serialize_loss_assessment_produces_expected_shape() -> None:
    record = _loss_record()
    payload = serialize_loss_assessment(record)

    assert payload == {
        "category": "SHADING",
        "evidence_level": "NOT_ASSESSABLE",
        "estimated_loss_percent": None,
        "evidence_codes": ["INTERVAL_POWER_AND_SOLAR_GEOMETRY_PROFILE_UNAVAILABLE"],
        "limitation": "daily aggregates cannot distinguish recurring geometric shading",
        "taxonomy_model_version": "MPLACAS_DAILY_LOSS_TAXONOMY_V1",
        "baseline_model_version": None,
    }


def test_serialize_loss_assessment_survives_for_likely_category_with_estimate() -> None:
    record = _loss_record(
        category="COMMUNICATION",
        evidence_level="LIKELY",
        estimated_loss_percent=Decimal("12.34"),
        evidence_codes=["INCOMPLETE_DAILY_DEVICE_REPORTING", "CAPACITY_WEIGHTED_REPORTING_GAP"],
        limitation="estimated percentage is missing reporting capacity, not confirmed energy loss",
        baseline_model_version="MPLACAS_SEASONAL_PR_BASELINE_V1",
    )
    payload = serialize_loss_assessment(record)
    assert payload["estimated_loss_percent"] == "12.34"
    assert payload["evidence_codes"] == [
        "INCOMPLETE_DAILY_DEVICE_REPORTING",
        "CAPACITY_WEIGHTED_REPORTING_GAP",
    ]
    assert payload["limitation"] == (
        "estimated percentage is missing reporting capacity, not confirmed energy loss"
    )
    assert payload["baseline_model_version"] == "MPLACAS_SEASONAL_PR_BASELINE_V1"


def test_loss_units_static_block_has_percent_unit() -> None:
    assert LOSS_UNITS == {"estimated_loss": "percent"}
