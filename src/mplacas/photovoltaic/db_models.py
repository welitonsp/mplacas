from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from mplacas.db.base import Base


class DailySolarModelResultRecord(Base):
    """Input snapshot of one versioned daily solar projection."""

    __tablename__ = "daily_solar_model_results"
    __table_args__ = (
        UniqueConstraint(
            "plant_id",
            "observation_date",
            "climate_source",
            "model_version",
            name="uq_daily_solar_model_result_identity",
        ),
        CheckConstraint("ghi_kwh_m2 >= 0", name="ck_solar_result_ghi_nonnegative"),
        CheckConstraint(
            "poa_irradiation_kwh_m2 >= 0", name="ck_solar_result_poa_nonnegative"
        ),
        CheckConstraint(
            "array_tilt_degrees >= 0 AND array_tilt_degrees <= 90",
            name="ck_solar_result_tilt_range",
        ),
        CheckConstraint(
            "array_azimuth_degrees >= 0 AND array_azimuth_degrees < 360",
            name="ck_solar_result_azimuth_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plants.id", ondelete="CASCADE"), index=True
    )
    observation_date: Mapped[date] = mapped_column(Date)
    climate_source: Mapped[str] = mapped_column(String(40))
    model_version: Mapped[str] = mapped_column(String(80))
    latitude_degrees: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    array_tilt_degrees: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    array_azimuth_degrees: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    module_technology: Mapped[str] = mapped_column(String(40))
    ghi_kwh_m2: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    poa_irradiation_kwh_m2: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    beam_horizontal_kwh_m2: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    diffuse_horizontal_kwh_m2: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    extraterrestrial_horizontal_kwh_m2: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    ambient_temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    cell_temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    temperature_coefficient_per_c: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    temperature_factor: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    temperature_adjusted_poa_equivalent_kwh_m2: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 3), nullable=True
    )
    quality_flags: Mapped[list[str]] = mapped_column(JSON)
    assumptions_json: Mapped[dict[str, str]] = mapped_column(JSON)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DailyPvPerformanceRecord(Base):
    """Versioned daily PR and reporting-availability result."""

    __tablename__ = "daily_pv_performance_results"
    __table_args__ = (
        UniqueConstraint(
            "plant_id",
            "observation_date",
            "solar_model_version",
            "performance_model_version",
            name="uq_daily_pv_performance_identity",
        ),
        CheckConstraint("measured_energy_kwh >= 0", name="ck_pv_performance_energy_nonnegative"),
        CheckConstraint("dc_capacity_kwp > 0", name="ck_pv_performance_dc_capacity_positive"),
        CheckConstraint("poa_irradiation_kwh_m2 > 0", name="ck_pv_performance_poa_positive"),
        CheckConstraint("performance_ratio >= 0", name="ck_pv_performance_pr_nonnegative"),
        CheckConstraint(
            "reporting_availability_ratio IS NULL OR "
            "(reporting_availability_ratio >= 0 AND reporting_availability_ratio <= 1)",
            name="ck_pv_performance_availability_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plants.id", ondelete="CASCADE"), index=True
    )
    observation_date: Mapped[date] = mapped_column(Date)
    solar_model_version: Mapped[str] = mapped_column(String(80))
    performance_model_version: Mapped[str] = mapped_column(String(80))
    climate_source: Mapped[str] = mapped_column(String(40))
    performance_ratio_nature: Mapped[str] = mapped_column(String(80))
    availability_nature: Mapped[str] = mapped_column(String(80))
    uncertainty_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    uncertainty_nature: Mapped[str] = mapped_column(String(80))
    measured_energy_kwh: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    dc_capacity_kwp: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    poa_irradiation_kwh_m2: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    final_yield_kwh_per_kwp: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    reference_yield_hours: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    performance_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    temperature_corrected_performance_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 4), nullable=True
    )
    reporting_availability_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 4), nullable=True
    )
    reporting_device_count: Mapped[int] = mapped_column()
    configured_device_count: Mapped[int] = mapped_column()
    reporting_capacity_kwp: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 3), nullable=True
    )
    configured_device_capacity_kwp: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 3), nullable=True
    )
    data_quality_status: Mapped[str] = mapped_column(String(24))
    quality_flags: Mapped[list[str]] = mapped_column(JSON)
    units_json: Mapped[dict[str, str]] = mapped_column(JSON)
    assumptions_json: Mapped[dict[str, str]] = mapped_column(JSON)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SeasonalPvBaselineRecord(Base):
    """Versioned seasonal reference and long-term degradation snapshot."""

    __tablename__ = "seasonal_pv_baseline_results"
    __table_args__ = (
        UniqueConstraint(
            "plant_id",
            "observation_date",
            "baseline_model_version",
            name="uq_seasonal_pv_baseline_identity",
        ),
        CheckConstraint(
            "baseline_sample_count > 0", name="ck_seasonal_baseline_samples_positive"
        ),
        CheckConstraint(
            "comparison_sample_count > 0",
            name="ck_seasonal_comparison_samples_positive",
        ),
        CheckConstraint(
            "clear_sky_poa_p90_kwh_m2 > 0",
            name="ck_seasonal_clear_sky_poa_positive",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plants.id", ondelete="CASCADE"), index=True
    )
    observation_date: Mapped[date] = mapped_column(Date)
    baseline_model_version: Mapped[str] = mapped_column(String(80))
    performance_model_version: Mapped[str] = mapped_column(String(80))
    metric_nature: Mapped[str] = mapped_column(String(80))
    clear_sky_index_nature: Mapped[str] = mapped_column(String(80))
    season_key: Mapped[str] = mapped_column(String(16))
    reference_start_date: Mapped[date] = mapped_column(Date)
    reference_end_date: Mapped[date] = mapped_column(Date)
    baseline_sample_count: Mapped[int] = mapped_column()
    baseline_excluded_count: Mapped[int] = mapped_column()
    comparison_start_date: Mapped[date] = mapped_column(Date)
    comparison_sample_count: Mapped[int] = mapped_column()
    clear_sky_poa_p90_kwh_m2: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    target_clear_sky_index: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 4), nullable=True
    )
    baseline_median_performance_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    baseline_mad: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    baseline_q10: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    baseline_q90: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    comparison_median_performance_ratio: Mapped[Decimal] = mapped_column(
        Numeric(8, 4)
    )
    degradation_percent: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    annualized_degradation_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 2), nullable=True
    )
    degradation_status: Mapped[str] = mapped_column(String(16))
    quality_flags: Mapped[list[str]] = mapped_column(JSON)
    assumptions_json: Mapped[dict[str, str]] = mapped_column(JSON)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DailyPvLossAssessmentRecord(Base):
    """One evidence-aware loss-category assessment for a plant-day."""

    __tablename__ = "daily_pv_loss_assessments"
    __table_args__ = (
        UniqueConstraint(
            "plant_id",
            "observation_date",
            "category",
            "taxonomy_model_version",
            name="uq_daily_pv_loss_assessment_identity",
        ),
        CheckConstraint(
            "estimated_loss_percent IS NULL OR estimated_loss_percent >= 0",
            name="ck_pv_loss_estimate_nonnegative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plants.id", ondelete="CASCADE"), index=True
    )
    observation_date: Mapped[date] = mapped_column(Date)
    category: Mapped[str] = mapped_column(String(24))
    evidence_level: Mapped[str] = mapped_column(String(24))
    taxonomy_model_version: Mapped[str] = mapped_column(String(80))
    performance_model_version: Mapped[str] = mapped_column(String(80))
    baseline_model_version: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )
    estimated_loss_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 2), nullable=True
    )
    evidence_codes: Mapped[list[str]] = mapped_column(JSON)
    limitation: Mapped[str | None] = mapped_column(String(240), nullable=True)
    assumptions_json: Mapped[dict[str, str]] = mapped_column(JSON)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
