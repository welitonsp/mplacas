from datetime import date
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy, DataStatus, Device, Plant
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord
from mplacas.photovoltaic.db_models import (
    DailyPvPerformanceRecord,
    DailySolarModelResultRecord,
)
from mplacas.photovoltaic.performance import (
    AVAILABILITY_NATURE,
    PERFORMANCE_MODEL_VERSION,
    DailyPerformanceInput,
    DeviceDailyPerformanceInput,
    calculate_daily_performance,
)
from mplacas.photovoltaic.performance_service import (
    calculate_and_persist_daily_performance,
)


def _device(
    device_id: str,
    *,
    capacity: str | None = "5.000",
    energy: str | None = "20.000",
    status: str | None = "CONSOLIDATED",
) -> DeviceDailyPerformanceInput:
    return DeviceDailyPerformanceInput(
        device_id=device_id,
        dc_capacity_kwp=Decimal(capacity) if capacity is not None else None,
        energy_kwh=Decimal(energy) if energy is not None else None,
        data_status=status,
    )


def _input(*devices: DeviceDailyPerformanceInput, **overrides) -> DailyPerformanceInput:
    values = {
        "plant_id": "plant-1",
        "observation_date": date(2026, 7, 15),
        "plant_dc_capacity_kwp": Decimal("10.000"),
        "poa_irradiation_kwh_m2": Decimal("5.000"),
        "temperature_adjusted_poa_equivalent_kwh_m2": Decimal("4.600"),
        "solar_model_version": "MPLACAS_POA_DAILY_ERBS_ISOTROPIC_V1",
        "climate_source": "OPEN_METEO",
        "devices": devices or (_device("A"), _device("B")),
    }
    values.update(overrides)
    return DailyPerformanceInput(**values)


def test_daily_pr_uses_final_yield_over_reference_yield() -> None:
    result = calculate_daily_performance(_input())

    assert PERFORMANCE_MODEL_VERSION == "MPLACAS_IEC61724_DAILY_PR_V1"
    assert result.measured_energy_kwh == Decimal("40.000")
    assert result.final_yield_kwh_per_kwp == Decimal("4.000")
    assert result.reference_yield_hours == Decimal("5.000")
    assert result.performance_ratio == Decimal("0.8000")
    assert result.temperature_corrected_performance_ratio == Decimal("0.8696")
    assert result.reporting_availability_ratio == Decimal("1.0000")
    assert result.data_quality_status == "FINAL"


def test_missing_inverter_is_incomplete_and_reduces_reporting_proxy() -> None:
    result = calculate_daily_performance(_input(_device("A"), _device("B", energy=None)))

    assert result.measured_energy_kwh == Decimal("20.000")
    assert result.reporting_availability_ratio == Decimal("0.5000")
    assert result.reporting_device_count == 1
    assert result.configured_device_count == 2
    assert result.data_quality_status == "INCOMPLETE"
    assert "ENERGY_DATA_INCOMPLETE" in result.quality_flags


def test_availability_is_unknown_without_per_device_capacity() -> None:
    result = calculate_daily_performance(
        _input(_device("A", capacity=None), _device("B", capacity=None))
    )

    assert result.reporting_availability_ratio is None
    assert result.reporting_capacity_kwp is None
    assert "REPORTING_AVAILABILITY_UNAVAILABLE_MISSING_DEVICE_CAPACITY" in (
        result.quality_flags
    )


def test_provisional_energy_keeps_pr_but_marks_quality() -> None:
    result = calculate_daily_performance(
        _input(_device("A", status="PROVISIONAL"), _device("B"))
    )

    assert result.performance_ratio == Decimal("0.8000")
    assert result.data_quality_status == "PROVISIONAL"
    assert "ENERGY_DATA_PROVISIONAL" in result.quality_flags


@pytest.mark.parametrize(
    "payload,error",
    [
        ({"plant_dc_capacity_kwp": Decimal(0)}, "DC capacity"),
        ({"poa_irradiation_kwh_m2": Decimal(0)}, "POA"),
        ({"devices": (_device("A", energy=None),)}, "measured energy"),
    ],
)
def test_performance_inputs_fail_closed(payload, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        calculate_daily_performance(_input(**payload))


def test_availability_nature_is_explicitly_a_reporting_proxy() -> None:
    assert AVAILABILITY_NATURE == "CAPACITY_WEIGHTED_DAILY_REPORTING_PROXY"


@pytest.mark.asyncio
async def test_performance_result_is_persisted_idempotently_with_metadata() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    target = date(2026, 7, 15)

    async with factory() as session:
        session.add(
            OrganizationRecord(
                id=DEFAULT_ORGANIZATION_ID,
                name="Default",
                slug=f"default-{uuid.uuid4().hex[:8]}",
                active=True,
            )
        )
        plant = Plant(name="Performance plant", installed_power_kwp=Decimal("10.000"))
        session.add(plant)
        await session.flush()
        devices = [
            Device(plant_id=plant.id, serial_number="A", dc_capacity_kwp=Decimal("5.000")),
            Device(plant_id=plant.id, serial_number="B", dc_capacity_kwp=Decimal("5.000")),
        ]
        session.add_all(devices)
        await session.flush()
        session.add_all(
            [
                DailyEnergy(
                    device_id=device.id,
                    production_date=target,
                    energy_kwh=Decimal("20.000"),
                    status=DataStatus.CONSOLIDATED,
                )
                for device in devices
            ]
        )
        session.add(
            DailySolarModelResultRecord(
                plant_id=plant.id,
                observation_date=target,
                climate_source="OPEN_METEO",
                model_version="MPLACAS_POA_DAILY_ERBS_ISOTROPIC_V1",
                latitude_degrees=Decimal("-17.744"),
                array_tilt_degrees=Decimal(20),
                array_azimuth_degrees=Decimal(0),
                module_technology="MONOCRYSTALLINE_SILICON",
                ghi_kwh_m2=Decimal("4.200"),
                poa_irradiation_kwh_m2=Decimal("5.000"),
                beam_horizontal_kwh_m2=Decimal("3.000"),
                diffuse_horizontal_kwh_m2=Decimal("1.200"),
                extraterrestrial_horizontal_kwh_m2=Decimal("7.000"),
                ambient_temperature_c=Decimal("28.00"),
                cell_temperature_c=Decimal("45.00"),
                temperature_coefficient_per_c=Decimal("-0.004"),
                temperature_factor=Decimal("0.9200"),
                temperature_adjusted_poa_equivalent_kwh_m2=Decimal("4.600"),
                quality_flags=["TEST"],
                assumptions_json={"test": "true"},
            )
        )
        await session.flush()

        first = await calculate_and_persist_daily_performance(
            session, plant_id=plant.id, observation_date=target
        )
        second = await calculate_and_persist_daily_performance(
            session, plant_id=plant.id, observation_date=target
        )
        await session.commit()

        assert first.inserted == 1
        assert second.unchanged == 1
        record = await session.scalar(select(DailyPvPerformanceRecord))
        assert record is not None
        assert record.performance_ratio == Decimal("0.8000")
        assert record.temperature_corrected_performance_ratio == Decimal("0.8696")
        assert record.reporting_availability_ratio == Decimal("1.0000")
        assert record.performance_ratio_nature == "IEC_61724_STYLE_AC_PR_MODELED_POA"
        assert record.availability_nature == "CAPACITY_WEIGHTED_DAILY_REPORTING_PROXY"
        assert record.uncertainty_percent is None
        assert record.uncertainty_nature == "NOT_QUANTIFIED_SENSOR_CLASSES_UNAVAILABLE"
        assert record.units_json["performance_ratio"] == "ratio"

    await engine.dispose()
