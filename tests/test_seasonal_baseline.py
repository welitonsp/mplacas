from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord
from mplacas.photovoltaic.db_models import (
    DailyPvPerformanceRecord,
    DailySolarModelResultRecord,
    SeasonalPvBaselineRecord,
)
from mplacas.photovoltaic.performance import PERFORMANCE_MODEL_VERSION
from mplacas.photovoltaic.poa import MODEL_VERSION as SOLAR_MODEL_VERSION
from mplacas.photovoltaic.seasonal_baseline import (
    BASELINE_MODEL_VERSION,
    InsufficientBaselineData,
    SeasonalPerformanceObservation,
    calculate_seasonal_baseline,
)
from mplacas.photovoltaic.seasonal_baseline_service import (
    calculate_and_persist_seasonal_baseline,
)


def _row(
    day: date,
    *,
    poa: str = "6.000",
    pr: str = "0.8000",
    corrected_pr: str | None = None,
    availability: str | None = "1.0000",
    status: str = "FINAL",
) -> SeasonalPerformanceObservation:
    return SeasonalPerformanceObservation(
        observation_date=day,
        poa_irradiation_kwh_m2=Decimal(poa),
        performance_ratio=Decimal(pr),
        temperature_corrected_performance_ratio=(
            Decimal(corrected_pr) if corrected_pr is not None else None
        ),
        reporting_availability_ratio=(
            Decimal(availability) if availability is not None else None
        ),
        data_quality_status=status,
    )


def _two_julys() -> tuple[SeasonalPerformanceObservation, ...]:
    reference = [
        _row(date(2024, 7, day), poa=str(Decimal("5.5") + Decimal(day) / 100))
        for day in range(1, 32)
    ]
    comparison = [
        _row(date(2025, 7, day), poa="6.000", pr="0.7500")
        for day in range(2, 21)
    ]
    return tuple(reference + comparison)


def test_seasonal_baseline_detects_robust_long_term_degradation() -> None:
    observations = _two_julys() + (
        _row(date(2024, 7, 10), poa="1.000", pr="0.2000"),
        _row(date(2024, 7, 11), poa="6.000", pr="1.1900"),
    )

    result = calculate_seasonal_baseline(
        observations,
        target_date=date(2025, 7, 20),
    )

    assert BASELINE_MODEL_VERSION == "MPLACAS_SEASONAL_PR_BASELINE_V1"
    assert result.season_key == "MONTH_07"
    assert result.baseline_median_performance_ratio == Decimal("0.8000")
    assert result.comparison_median_performance_ratio == Decimal("0.7500")
    assert result.degradation_percent == Decimal("-6.25")
    assert result.degradation_status == "DEGRADED"
    assert result.baseline_excluded_count >= 2
    assert "BASELINE_REFERENCE_WINDOW_FROZEN" in result.quality_flags
    assert "LOW_IRRADIANCE_REFERENCE_DAYS_EXCLUDED" in result.quality_flags


def test_future_and_degraded_comparison_rows_cannot_contaminate_frozen_baseline() -> None:
    base = _two_julys()
    future = tuple(
        _row(date(2026, 7, day), pr="0.3000") for day in range(1, 21)
    )

    result = calculate_seasonal_baseline(
        base + future,
        target_date=date(2025, 7, 20),
    )

    assert result.baseline_median_performance_ratio == Decimal("0.8000")
    assert result.comparison_median_performance_ratio == Decimal("0.7500")


def test_corrected_pr_is_preferred_and_low_quality_rows_are_rejected() -> None:
    rows = list(_two_julys())
    rows = [
        _row(
            row.observation_date,
            poa=str(row.poa_irradiation_kwh_m2),
            pr="0.7000",
            corrected_pr=(
                "0.8000" if row.observation_date.year == 2024 else "0.7900"
            ),
        )
        for row in rows
    ]
    rows.extend(
        [
            _row(date(2024, 7, 15), pr="0.1000", availability="0.50"),
            _row(date(2024, 7, 16), pr="0.1000", status="PROVISIONAL"),
        ]
    )

    result = calculate_seasonal_baseline(tuple(rows), target_date=date(2025, 7, 20))

    assert result.baseline_median_performance_ratio == Decimal("0.8000")
    assert result.comparison_median_performance_ratio == Decimal("0.7900")


def test_baseline_fails_closed_before_reference_year_is_complete() -> None:
    with pytest.raises(InsufficientBaselineData, match="reference year"):
        calculate_seasonal_baseline(
            tuple(_row(date(2024, 7, day)) for day in range(1, 20)),
            target_date=date(2024, 7, 20),
        )


def _performance_record(plant_id, day: date, pr: str) -> DailyPvPerformanceRecord:
    return DailyPvPerformanceRecord(
        plant_id=plant_id,
        observation_date=day,
        solar_model_version=SOLAR_MODEL_VERSION,
        performance_model_version=PERFORMANCE_MODEL_VERSION,
        climate_source="OPEN_METEO",
        performance_ratio_nature="TEST_PR",
        availability_nature="TEST_PROXY",
        uncertainty_percent=None,
        uncertainty_nature="NOT_QUANTIFIED",
        measured_energy_kwh=Decimal("4"),
        dc_capacity_kwp=Decimal("1"),
        poa_irradiation_kwh_m2=Decimal("6"),
        final_yield_kwh_per_kwp=Decimal("4"),
        reference_yield_hours=Decimal("5"),
        performance_ratio=Decimal(pr),
        temperature_corrected_performance_ratio=Decimal(pr),
        reporting_availability_ratio=Decimal("1"),
        reporting_device_count=1,
        configured_device_count=1,
        reporting_capacity_kwp=Decimal("1"),
        configured_device_capacity_kwp=Decimal("1"),
        data_quality_status="FINAL",
        quality_flags=[],
        units_json={"performance_ratio": "ratio"},
        assumptions_json={"test": "true"},
    )


def _solar_record(plant_id, day: date) -> DailySolarModelResultRecord:
    return DailySolarModelResultRecord(
        plant_id=plant_id,
        observation_date=day,
        climate_source="OPEN_METEO",
        model_version=SOLAR_MODEL_VERSION,
        latitude_degrees=Decimal("-17.744"),
        array_tilt_degrees=Decimal("20"),
        array_azimuth_degrees=Decimal("0"),
        module_technology="MONOCRYSTALLINE_SILICON",
        ghi_kwh_m2=Decimal("5"),
        poa_irradiation_kwh_m2=Decimal("6"),
        beam_horizontal_kwh_m2=Decimal("3"),
        diffuse_horizontal_kwh_m2=Decimal("2"),
        extraterrestrial_horizontal_kwh_m2=Decimal("8"),
        ambient_temperature_c=Decimal("25"),
        cell_temperature_c=Decimal("40"),
        temperature_coefficient_per_c=Decimal("-0.004"),
        temperature_factor=Decimal("0.94"),
        temperature_adjusted_poa_equivalent_kwh_m2=Decimal("5.64"),
        quality_flags=[],
        assumptions_json={"test": "true"},
    )


@pytest.mark.asyncio
async def test_seasonal_baseline_service_persists_idempotent_snapshot() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    target = date(2025, 7, 20)

    async with factory() as session:
        session.add(
            OrganizationRecord(
                id=DEFAULT_ORGANIZATION_ID,
                name="Default",
                slug="default-seasonal-baseline",
                active=True,
            )
        )
        plant = Plant(name="Seasonal baseline plant")
        session.add(plant)
        await session.flush()
        dated_ratios = [
            (date(2024, 7, day), "0.8000") for day in range(1, 32)
        ] + [(date(2025, 7, day), "0.7600") for day in range(2, 21)]
        for day, ratio in dated_ratios:
            session.add_all(
                [_performance_record(plant.id, day, ratio), _solar_record(plant.id, day)]
            )
        await session.flush()

        first = await calculate_and_persist_seasonal_baseline(
            session, plant_id=plant.id, observation_date=target
        )
        second = await calculate_and_persist_seasonal_baseline(
            session, plant_id=plant.id, observation_date=target
        )
        await session.commit()

        assert first.inserted == 1
        assert second.unchanged == 1
        record = await session.scalar(select(SeasonalPvBaselineRecord))
        assert record is not None
        assert record.baseline_model_version == BASELINE_MODEL_VERSION
        assert record.baseline_median_performance_ratio == Decimal("0.8000")
        assert record.comparison_median_performance_ratio == Decimal("0.7600")
        assert record.degradation_percent == Decimal("-5.00")
        assert record.degradation_status == "DEGRADED"
        assert record.assumptions_json["future_observations"] == "EXCLUDED"

    await engine.dispose()
