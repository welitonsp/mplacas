from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.photovoltaic.db_models import (
    DailyPvLossAssessmentRecord,
    DailyPvPerformanceRecord,
    SeasonalPvBaselineRecord,
)
from mplacas.photovoltaic.loss_taxonomy import LOSS_TAXONOMY_MODEL_VERSION
from mplacas.photovoltaic.performance import PERFORMANCE_MODEL_VERSION
from mplacas.photovoltaic.poa import MODEL_VERSION as SOLAR_MODEL_VERSION
from mplacas.photovoltaic.read_service import (
    InvalidPerformanceWindowError,
    PhotovoltaicBaselineNotFoundError,
    PhotovoltaicLossAssessmentNotFoundError,
    PhotovoltaicPerformanceNotFoundError,
    get_latest_baseline,
    get_latest_losses,
    get_latest_performance,
    get_performance_series,
    get_summary,
)
from mplacas.photovoltaic.seasonal_baseline import (
    BASELINE_MODEL_VERSION,
    MINIMUM_REPORTING_AVAILABILITY,
    REFERENCE_WINDOW_DAYS,
)


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


def _performance_row(
    *,
    plant_id: uuid.UUID,
    observation_date: date,
    solar_model_version: str = SOLAR_MODEL_VERSION,
    performance_model_version: str = PERFORMANCE_MODEL_VERSION,
    data_quality_status: str = "FINAL",
    reporting_availability_ratio: Decimal | None = Decimal("0.9800"),
    performance_ratio: Decimal = Decimal("0.8500"),
) -> DailyPvPerformanceRecord:
    return DailyPvPerformanceRecord(
        plant_id=plant_id,
        observation_date=observation_date,
        solar_model_version=solar_model_version,
        performance_model_version=performance_model_version,
        climate_source="OPEN_METEO_ARCHIVE",
        performance_ratio_nature="IEC_61724_STYLE_AC_PR_MODELED_POA",
        availability_nature="CAPACITY_WEIGHTED_DAILY_REPORTING_PROXY",
        uncertainty_percent=None,
        uncertainty_nature="NOT_QUANTIFIED_SENSOR_CLASSES_UNAVAILABLE",
        measured_energy_kwh=Decimal("100.000"),
        dc_capacity_kwp=Decimal("100.000"),
        poa_irradiation_kwh_m2=Decimal("5.000"),
        final_yield_kwh_per_kwp=Decimal("1.000"),
        reference_yield_hours=Decimal("5.000"),
        performance_ratio=performance_ratio,
        temperature_corrected_performance_ratio=None,
        reporting_availability_ratio=reporting_availability_ratio,
        reporting_device_count=1,
        configured_device_count=1,
        reporting_capacity_kwp=Decimal("100.000"),
        configured_device_capacity_kwp=Decimal("100.000"),
        data_quality_status=data_quality_status,
        quality_flags=[],
        units_json={"performance_ratio": "ratio"},
        assumptions_json={},
    )


@pytest.mark.asyncio
async def test_get_latest_performance_returns_most_recent_matching_versions() -> None:
    factory, engine = await _factory()
    async with factory() as session:
        plant = Plant(name="Plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        session.add_all(
            [
                _performance_row(plant_id=plant.id, observation_date=date(2026, 7, 1)),
                _performance_row(plant_id=plant.id, observation_date=date(2026, 7, 2)),
                # Different solar_model_version: must be excluded from "latest".
                _performance_row(
                    plant_id=plant.id,
                    observation_date=date(2026, 7, 3),
                    solar_model_version="SOME_OTHER_SOLAR_MODEL",
                ),
            ]
        )
        await session.commit()

        result = await get_latest_performance(session, plant_id=plant.id)
        assert result.observation_date == date(2026, 7, 2)
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_latest_performance_raises_when_missing() -> None:
    factory, engine = await _factory()
    async with factory() as session:
        plant = Plant(name="Plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.commit()

        with pytest.raises(PhotovoltaicPerformanceNotFoundError):
            await get_latest_performance(session, plant_id=plant.id)
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_performance_series_returns_ordered_rows_in_window() -> None:
    factory, engine = await _factory()
    async with factory() as session:
        plant = Plant(name="Plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        session.add_all(
            [
                _performance_row(plant_id=plant.id, observation_date=date(2026, 7, 3)),
                _performance_row(plant_id=plant.id, observation_date=date(2026, 7, 1)),
                _performance_row(plant_id=plant.id, observation_date=date(2026, 7, 2)),
                _performance_row(plant_id=plant.id, observation_date=date(2026, 6, 30)),
            ]
        )
        await session.commit()

        results = await get_performance_series(
            session,
            plant_id=plant.id,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 3),
        )
        assert [row.observation_date for row in results] == [
            date(2026, 7, 1),
            date(2026, 7, 2),
            date(2026, 7, 3),
        ]
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_performance_series_returns_empty_tuple_when_no_data() -> None:
    factory, engine = await _factory()
    async with factory() as session:
        plant = Plant(name="Plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.commit()

        results = await get_performance_series(
            session,
            plant_id=plant.id,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 3),
        )
        assert results == ()
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_performance_series_rejects_inverted_window() -> None:
    factory, engine = await _factory()
    async with factory() as session:
        plant = Plant(name="Plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.commit()

        with pytest.raises(InvalidPerformanceWindowError):
            await get_performance_series(
                session,
                plant_id=plant.id,
                start_date=date(2026, 7, 3),
                end_date=date(2026, 7, 1),
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_performance_series_rejects_window_over_366_days() -> None:
    factory, engine = await _factory()
    async with factory() as session:
        plant = Plant(name="Plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.commit()

        with pytest.raises(InvalidPerformanceWindowError):
            await get_performance_series(
                session,
                plant_id=plant.id,
                start_date=date(2026, 1, 1),
                end_date=date(2027, 1, 3),
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_latest_baseline_returns_record_when_present() -> None:
    factory, engine = await _factory()
    async with factory() as session:
        plant = Plant(name="Plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        session.add(
            SeasonalPvBaselineRecord(
                plant_id=plant.id,
                observation_date=date(2027, 7, 1),
                baseline_model_version=BASELINE_MODEL_VERSION,
                performance_model_version=PERFORMANCE_MODEL_VERSION,
                metric_nature="TEMPERATURE_CORRECTED_PR_PREFERRED",
                clear_sky_index_nature="EMPIRICAL_SEASONAL_POA_P90",
                season_key="MONTH_07",
                reference_start_date=date(2026, 7, 1),
                reference_end_date=date(2027, 7, 1),
                baseline_sample_count=20,
                baseline_excluded_count=0,
                comparison_start_date=date(2027, 7, 2),
                comparison_sample_count=10,
                clear_sky_poa_p90_kwh_m2=Decimal("6.500"),
                target_clear_sky_index=Decimal("0.9500"),
                baseline_median_performance_ratio=Decimal("0.8500"),
                baseline_mad=Decimal("0.0100"),
                baseline_q10=Decimal("0.8300"),
                baseline_q90=Decimal("0.8700"),
                comparison_median_performance_ratio=Decimal("0.8000"),
                degradation_percent=Decimal("-5.88"),
                annualized_degradation_percent=Decimal("-5.90"),
                degradation_status="DEGRADED",
                quality_flags=[],
                assumptions_json={},
            )
        )
        await session.commit()

        result = await get_latest_baseline(session, plant_id=plant.id)
        assert result.observation_date == date(2027, 7, 1)
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_latest_baseline_reason_no_performance_history() -> None:
    factory, engine = await _factory()
    async with factory() as session:
        plant = Plant(name="Plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.commit()

        with pytest.raises(PhotovoltaicBaselineNotFoundError) as excinfo:
            await get_latest_baseline(session, plant_id=plant.id)
        assert excinfo.value.reason == "NO_PERFORMANCE_HISTORY"
        assert excinfo.value.reference_complete_on is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_latest_baseline_reason_reference_year_incomplete() -> None:
    factory, engine = await _factory()
    async with factory() as session:
        plant = Plant(name="Plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        first_observation = date(2026, 1, 1)
        session.add(
            _performance_row(plant_id=plant.id, observation_date=first_observation)
        )
        await session.commit()

        today = first_observation + timedelta(days=10)
        with pytest.raises(PhotovoltaicBaselineNotFoundError) as excinfo:
            await get_latest_baseline(session, plant_id=plant.id, today=today)
        assert excinfo.value.reason == "REFERENCE_YEAR_INCOMPLETE"
        expected_reference_complete_on = first_observation + timedelta(
            days=REFERENCE_WINDOW_DAYS
        )
        assert excinfo.value.reference_complete_on == expected_reference_complete_on
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_latest_baseline_reason_insufficient_seasonal_samples() -> None:
    factory, engine = await _factory()
    async with factory() as session:
        plant = Plant(name="Plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        first_observation = date(2026, 1, 1)
        session.add(
            _performance_row(plant_id=plant.id, observation_date=first_observation)
        )
        await session.commit()

        today = first_observation + timedelta(days=REFERENCE_WINDOW_DAYS + 30)
        with pytest.raises(PhotovoltaicBaselineNotFoundError) as excinfo:
            await get_latest_baseline(session, plant_id=plant.id, today=today)
        assert excinfo.value.reason == "INSUFFICIENT_SEASONAL_SAMPLES"
        assert excinfo.value.reference_complete_on is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_latest_baseline_ignores_ineligible_performance_rows() -> None:
    """Rows below the reporting-availability threshold do not count toward eligibility."""
    factory, engine = await _factory()
    async with factory() as session:
        plant = Plant(name="Plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        below_threshold = MINIMUM_REPORTING_AVAILABILITY - Decimal("0.10")
        session.add(
            _performance_row(
                plant_id=plant.id,
                observation_date=date(2026, 1, 1),
                reporting_availability_ratio=below_threshold,
            )
        )
        await session.commit()

        with pytest.raises(PhotovoltaicBaselineNotFoundError) as excinfo:
            await get_latest_baseline(session, plant_id=plant.id, today=date(2026, 6, 1))
        assert excinfo.value.reason == "NO_PERFORMANCE_HISTORY"
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_latest_losses_returns_fixed_category_order() -> None:
    factory, engine = await _factory()
    async with factory() as session:
        plant = Plant(name="Plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        # Insert in a scrambled order deliberately.
        categories = [
            "UNEXPLAINED",
            "COMMUNICATION",
            "DEGRADATION",
            "UNAVAILABILITY",
            "TEMPERATURE",
            "CLIPPING",
            "SHADING",
            "SOILING",
        ]
        for category in categories:
            session.add(
                DailyPvLossAssessmentRecord(
                    plant_id=plant.id,
                    observation_date=date(2026, 7, 1),
                    category=category,
                    evidence_level="NOT_DETECTED",
                    taxonomy_model_version=LOSS_TAXONOMY_MODEL_VERSION,
                    performance_model_version=PERFORMANCE_MODEL_VERSION,
                    baseline_model_version=None,
                    estimated_loss_percent=None,
                    evidence_codes=[],
                    limitation=None,
                    assumptions_json={},
                )
            )
        await session.commit()

        results = await get_latest_losses(session, plant_id=plant.id)
        assert [row.category for row in results] == [
            "COMMUNICATION",
            "UNAVAILABILITY",
            "CLIPPING",
            "SOILING",
            "SHADING",
            "TEMPERATURE",
            "DEGRADATION",
            "UNEXPLAINED",
        ]
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_latest_losses_raises_when_missing() -> None:
    factory, engine = await _factory()
    async with factory() as session:
        plant = Plant(name="Plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.commit()

        with pytest.raises(PhotovoltaicLossAssessmentNotFoundError):
            await get_latest_losses(session, plant_id=plant.id)
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_summary_returns_all_blocks_null_for_new_plant() -> None:
    factory, engine = await _factory()
    async with factory() as session:
        plant = Plant(name="Plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.commit()

        result = await get_summary(session, plant_id=plant.id)
        assert result.performance is None
        assert result.performance_unavailable_reason == "NO_PERFORMANCE_RESULTS"
        assert result.baseline is None
        assert result.baseline_unavailable_reason == "NO_PERFORMANCE_HISTORY"
        assert result.reference_complete_on is None
        assert result.losses is None
        assert result.losses_unavailable_reason == "NO_LOSS_ASSESSMENTS"
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_summary_returns_populated_blocks_when_available() -> None:
    factory, engine = await _factory()
    async with factory() as session:
        plant = Plant(name="Plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        session.add(_performance_row(plant_id=plant.id, observation_date=date(2026, 7, 1)))
        session.add(
            DailyPvLossAssessmentRecord(
                plant_id=plant.id,
                observation_date=date(2026, 7, 1),
                category="COMMUNICATION",
                evidence_level="NOT_DETECTED",
                taxonomy_model_version=LOSS_TAXONOMY_MODEL_VERSION,
                performance_model_version=PERFORMANCE_MODEL_VERSION,
                baseline_model_version=None,
                estimated_loss_percent=None,
                evidence_codes=[],
                limitation=None,
                assumptions_json={},
            )
        )
        await session.commit()

        result = await get_summary(session, plant_id=plant.id, today=date(2026, 7, 1))
        assert result.performance is not None
        assert result.performance_unavailable_reason is None
        assert result.baseline is None
        assert result.baseline_unavailable_reason == "REFERENCE_YEAR_INCOMPLETE"
        assert result.reference_complete_on is not None
        assert result.losses is not None
        assert result.losses_unavailable_reason is None
    await engine.dispose()
