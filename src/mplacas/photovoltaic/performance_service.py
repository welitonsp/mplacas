from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.db.models import DailyEnergy, Device, Plant
from mplacas.photovoltaic.db_models import (
    DailyPvPerformanceRecord,
    DailySolarModelResultRecord,
)
from mplacas.photovoltaic.performance import (
    AVAILABILITY_NATURE,
    PERFORMANCE_MODEL_VERSION,
    PERFORMANCE_RATIO_NATURE,
    PERFORMANCE_UNITS,
    UNCERTAINTY_NATURE,
    DailyPerformanceInput,
    DeviceDailyPerformanceInput,
    calculate_daily_performance,
)
from mplacas.photovoltaic.poa import MODEL_VERSION as SOLAR_MODEL_VERSION


@dataclass(frozen=True, slots=True)
class PerformanceComputationSummary:
    inserted: int
    updated: int
    unchanged: int
    skipped: int
    skip_reason: str | None = None


async def calculate_and_persist_daily_performance(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    observation_date: date,
) -> PerformanceComputationSummary:
    """Build one auditable daily PR result from energy and versioned POA."""
    plant = await session.get(Plant, plant_id)
    if plant is None:
        return PerformanceComputationSummary(0, 0, 0, 1, "plant not found")
    if plant.installed_power_kwp is None or plant.installed_power_kwp <= 0:
        return PerformanceComputationSummary(0, 0, 0, 1, "plant DC capacity unavailable")

    solar_results = (
        await session.scalars(
            select(DailySolarModelResultRecord).where(
                DailySolarModelResultRecord.plant_id == plant_id,
                DailySolarModelResultRecord.observation_date == observation_date,
                DailySolarModelResultRecord.model_version == SOLAR_MODEL_VERSION,
            )
        )
    ).all()
    if not solar_results:
        return PerformanceComputationSummary(0, 0, 0, 1, "POA result unavailable")
    if len(solar_results) > 1:
        return PerformanceComputationSummary(0, 0, 0, 1, "POA climate source is ambiguous")
    solar = solar_results[0]
    if solar.poa_irradiation_kwh_m2 <= 0:
        return PerformanceComputationSummary(0, 0, 0, 1, "POA irradiation is zero")

    device_rows = (
        await session.execute(
            select(
                Device.id,
                Device.dc_capacity_kwp,
                DailyEnergy.energy_kwh,
                DailyEnergy.status,
            )
            .outerjoin(
                DailyEnergy,
                and_(
                    DailyEnergy.device_id == Device.id,
                    DailyEnergy.production_date == observation_date,
                ),
            )
            .where(Device.plant_id == plant_id)
            .order_by(Device.serial_number)
        )
    ).all()
    devices = tuple(
        DeviceDailyPerformanceInput(
            device_id=str(device_id),
            dc_capacity_kwp=dc_capacity,
            energy_kwh=energy,
            data_status=status.value if status is not None else None,
        )
        for device_id, dc_capacity, energy, status in device_rows
    )
    if not any(device.energy_kwh is not None for device in devices):
        return PerformanceComputationSummary(0, 0, 0, 1, "measured energy unavailable")

    result = calculate_daily_performance(
        DailyPerformanceInput(
            plant_id=str(plant_id),
            observation_date=observation_date,
            plant_dc_capacity_kwp=plant.installed_power_kwp,
            poa_irradiation_kwh_m2=solar.poa_irradiation_kwh_m2,
            temperature_adjusted_poa_equivalent_kwh_m2=(
                solar.temperature_adjusted_poa_equivalent_kwh_m2
            ),
            solar_model_version=solar.model_version,
            climate_source=solar.climate_source,
            devices=devices,
        )
    )
    values = {
        "climate_source": solar.climate_source,
        "performance_ratio_nature": PERFORMANCE_RATIO_NATURE,
        "availability_nature": AVAILABILITY_NATURE,
        "uncertainty_percent": None,
        "uncertainty_nature": UNCERTAINTY_NATURE,
        "measured_energy_kwh": result.measured_energy_kwh,
        "dc_capacity_kwp": plant.installed_power_kwp,
        "poa_irradiation_kwh_m2": solar.poa_irradiation_kwh_m2,
        "final_yield_kwh_per_kwp": result.final_yield_kwh_per_kwp,
        "reference_yield_hours": result.reference_yield_hours,
        "performance_ratio": result.performance_ratio,
        "temperature_corrected_performance_ratio": (
            result.temperature_corrected_performance_ratio
        ),
        "reporting_availability_ratio": result.reporting_availability_ratio,
        "reporting_device_count": result.reporting_device_count,
        "configured_device_count": result.configured_device_count,
        "reporting_capacity_kwp": result.reporting_capacity_kwp,
        "configured_device_capacity_kwp": result.configured_device_capacity_kwp,
        "data_quality_status": result.data_quality_status,
        "quality_flags": list(result.quality_flags),
        "units_json": dict(PERFORMANCE_UNITS),
        "assumptions_json": {
            "reference_irradiance_kw_m2": "1.000",
            "energy_boundary": "AC_DAILY_DEVICE_SUM",
            "availability_basis": AVAILABILITY_NATURE,
        },
    }
    existing = await session.scalar(
        select(DailyPvPerformanceRecord).where(
            DailyPvPerformanceRecord.plant_id == plant_id,
            DailyPvPerformanceRecord.observation_date == observation_date,
            DailyPvPerformanceRecord.solar_model_version == solar.model_version,
            DailyPvPerformanceRecord.performance_model_version
            == PERFORMANCE_MODEL_VERSION,
        )
    )
    if existing is None:
        session.add(
            DailyPvPerformanceRecord(
                plant_id=plant_id,
                observation_date=observation_date,
                solar_model_version=solar.model_version,
                performance_model_version=PERFORMANCE_MODEL_VERSION,
                **values,
            )
        )
        await session.flush()
        return PerformanceComputationSummary(1, 0, 0, 0)
    if all(getattr(existing, name) == value for name, value in values.items()):
        return PerformanceComputationSummary(0, 0, 1, 0)
    for name, value in values.items():
        setattr(existing, name, value)
    await session.flush()
    return PerformanceComputationSummary(0, 1, 0, 0)
