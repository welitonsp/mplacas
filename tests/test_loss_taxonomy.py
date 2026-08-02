from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord
from mplacas.photovoltaic.db_models import (
    DailyPvLossAssessmentRecord,
    DailyPvPerformanceRecord,
)
from mplacas.photovoltaic.loss_taxonomy import (
    EvidenceLevel,
    LossCategory,
    DailyLossTaxonomyInput,
    classify_daily_losses,
)
from mplacas.photovoltaic.loss_taxonomy_service import (
    classify_and_persist_daily_losses,
)
from mplacas.photovoltaic.performance import PERFORMANCE_MODEL_VERSION
from mplacas.photovoltaic.poa import MODEL_VERSION as SOLAR_MODEL_VERSION


def _input(**overrides) -> DailyLossTaxonomyInput:
    values = {
        "performance_ratio": Decimal("0.7200"),
        "temperature_corrected_performance_ratio": Decimal("0.8000"),
        "reporting_availability_ratio": Decimal("1.0000"),
        "data_quality_status": "FINAL",
        "measured_energy_kwh": Decimal("40"),
        "poa_irradiation_kwh_m2": Decimal("6"),
        "dc_capacity_kwp": Decimal("10"),
        "ac_capacity_kw": Decimal("8"),
        "baseline_median_performance_ratio": Decimal("0.8500"),
        "baseline_degradation_status": "DEGRADED",
        "baseline_degradation_percent": Decimal("-5.50"),
        "target_clear_sky_index": Decimal("0.95"),
        "precipitation_sample_days": 30,
        "dry_days": 25,
    }
    values.update(overrides)
    return DailyLossTaxonomyInput(**values)


def _by_category(data: DailyLossTaxonomyInput):
    return {assessment.category: assessment for assessment in classify_daily_losses(data)}


def test_taxonomy_separates_evidence_for_all_required_loss_categories() -> None:
    result = _by_category(_input())

    assert set(result) == set(LossCategory)
    assert result[LossCategory.COMMUNICATION].evidence_level == EvidenceLevel.NOT_DETECTED
    assert result[LossCategory.CLIPPING].evidence_level == EvidenceLevel.POSSIBLE
    assert result[LossCategory.SOILING].evidence_level == EvidenceLevel.POSSIBLE
    assert result[LossCategory.SHADING].evidence_level == EvidenceLevel.NOT_ASSESSABLE
    assert result[LossCategory.TEMPERATURE].evidence_level == EvidenceLevel.LIKELY
    assert result[LossCategory.DEGRADATION].evidence_level == EvidenceLevel.LIKELY
    assert result[LossCategory.UNEXPLAINED].evidence_level == EvidenceLevel.NOT_DETECTED


def test_incomplete_reporting_is_communication_not_technical_unavailability() -> None:
    result = _by_category(
        _input(
            reporting_availability_ratio=Decimal("0.50"),
            data_quality_status="INCOMPLETE",
            measured_energy_kwh=Decimal("0"),
        )
    )

    assert result[LossCategory.COMMUNICATION].evidence_level == EvidenceLevel.LIKELY
    assert result[LossCategory.COMMUNICATION].estimated_loss_percent == Decimal("50.00")
    assert result[LossCategory.UNAVAILABILITY].evidence_level == EvidenceLevel.NOT_DETECTED


def test_zero_energy_with_complete_reporting_is_likely_unavailability_signal() -> None:
    result = _by_category(
        _input(
            measured_energy_kwh=Decimal("0"),
            performance_ratio=Decimal("0"),
            temperature_corrected_performance_ratio=None,
        )
    )

    unavailable = result[LossCategory.UNAVAILABILITY]
    assert unavailable.evidence_level == EvidenceLevel.LIKELY
    assert unavailable.estimated_loss_percent == Decimal("100.00")
    assert unavailable.limitation == "interval operating states are unavailable"


def test_missing_interval_and_weather_inputs_fail_to_not_assessable() -> None:
    result = _by_category(
        _input(
            ac_capacity_kw=None,
            temperature_corrected_performance_ratio=None,
            baseline_median_performance_ratio=None,
            baseline_degradation_status=None,
            baseline_degradation_percent=None,
            target_clear_sky_index=None,
            precipitation_sample_days=0,
            dry_days=0,
        )
    )

    assert result[LossCategory.CLIPPING].evidence_level == EvidenceLevel.NOT_ASSESSABLE
    assert result[LossCategory.SOILING].evidence_level == EvidenceLevel.NOT_ASSESSABLE
    assert result[LossCategory.TEMPERATURE].evidence_level == EvidenceLevel.NOT_ASSESSABLE
    assert result[LossCategory.DEGRADATION].evidence_level == EvidenceLevel.NOT_ASSESSABLE
    assert result[LossCategory.UNEXPLAINED].evidence_level == EvidenceLevel.NOT_ASSESSABLE


def _performance(plant_id, target: date) -> DailyPvPerformanceRecord:
    return DailyPvPerformanceRecord(
        plant_id=plant_id,
        observation_date=target,
        solar_model_version=SOLAR_MODEL_VERSION,
        performance_model_version=PERFORMANCE_MODEL_VERSION,
        climate_source="OPEN_METEO",
        performance_ratio_nature="TEST_PR",
        availability_nature="TEST_PROXY",
        uncertainty_percent=None,
        uncertainty_nature="NOT_QUANTIFIED",
        measured_energy_kwh=Decimal("40"),
        dc_capacity_kwp=Decimal("10"),
        poa_irradiation_kwh_m2=Decimal("6"),
        final_yield_kwh_per_kwp=Decimal("4"),
        reference_yield_hours=Decimal("5"),
        performance_ratio=Decimal("0.72"),
        temperature_corrected_performance_ratio=Decimal("0.80"),
        reporting_availability_ratio=Decimal("1"),
        reporting_device_count=1,
        configured_device_count=1,
        reporting_capacity_kwp=Decimal("10"),
        configured_device_capacity_kwp=Decimal("10"),
        data_quality_status="FINAL",
        quality_flags=[],
        units_json={"performance_ratio": "ratio"},
        assumptions_json={"test": "true"},
    )


@pytest.mark.asyncio
async def test_taxonomy_service_persists_eight_idempotent_assessments() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    target = date(2026, 7, 30)

    async with factory() as session:
        session.add(
            OrganizationRecord(
                id=DEFAULT_ORGANIZATION_ID,
                name="Default",
                slug="default-loss-taxonomy",
                active=True,
            )
        )
        plant = Plant(name="Loss plant", ac_capacity_kw=Decimal("8"))
        session.add(plant)
        await session.flush()
        session.add(_performance(plant.id, target))
        session.add_all(
            [
                DailyClimateObservationRecord(
                    plant_id=plant.id,
                    observation_date=target - timedelta(days=offset),
                    precipitation_mm=Decimal("0"),
                    source="OPEN_METEO",
                )
                for offset in range(30)
            ]
        )
        await session.flush()

        first = await classify_and_persist_daily_losses(
            session, plant_id=plant.id, observation_date=target
        )
        second = await classify_and_persist_daily_losses(
            session, plant_id=plant.id, observation_date=target
        )
        await session.commit()

        assert first.inserted == 8
        assert second.unchanged == 8
        records = (await session.scalars(select(DailyPvLossAssessmentRecord))).all()
        assert {record.category for record in records} == {
            category.value for category in LossCategory
        }
        shading = next(record for record in records if record.category == "SHADING")
        assert shading.evidence_level == "NOT_ASSESSABLE"
        assert shading.estimated_loss_percent is None

    await engine.dispose()
