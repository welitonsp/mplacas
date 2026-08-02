"""Pure IEC 61724-style daily performance indicators.

The standard performance ratio uses final yield divided by reference yield.
Availability here is deliberately a reporting proxy: daily energy rows do not
contain the interval state categories required for technical availability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal


PERFORMANCE_MODEL_VERSION = "MPLACAS_IEC61724_DAILY_PR_V1"
REFERENCE_IRRADIANCE_KW_M2 = Decimal("1.000")
PERFORMANCE_RATIO_NATURE = "IEC_61724_STYLE_AC_PR_MODELED_POA"
AVAILABILITY_NATURE = "CAPACITY_WEIGHTED_DAILY_REPORTING_PROXY"
UNCERTAINTY_NATURE = "NOT_QUANTIFIED_SENSOR_CLASSES_UNAVAILABLE"
PERFORMANCE_UNITS = {
    "measured_energy": "kWh_AC",
    "dc_capacity": "kWp_STC",
    "poa_irradiation": "kWh/m2",
    "final_yield": "kWh/kWp",
    "reference_yield": "h",
    "performance_ratio": "ratio",
    "availability": "ratio",
}


@dataclass(frozen=True, slots=True)
class DeviceDailyPerformanceInput:
    device_id: str
    dc_capacity_kwp: Decimal | None
    energy_kwh: Decimal | None
    data_status: str | None


@dataclass(frozen=True, slots=True)
class DailyPerformanceInput:
    plant_id: str
    observation_date: date
    plant_dc_capacity_kwp: Decimal
    poa_irradiation_kwh_m2: Decimal
    temperature_adjusted_poa_equivalent_kwh_m2: Decimal | None
    solar_model_version: str
    climate_source: str
    devices: tuple[DeviceDailyPerformanceInput, ...]


@dataclass(frozen=True, slots=True)
class DailyPerformanceResult:
    measured_energy_kwh: Decimal
    final_yield_kwh_per_kwp: Decimal
    reference_yield_hours: Decimal
    performance_ratio: Decimal
    temperature_corrected_performance_ratio: Decimal | None
    reporting_availability_ratio: Decimal | None
    reporting_device_count: int
    configured_device_count: int
    reporting_capacity_kwp: Decimal | None
    configured_device_capacity_kwp: Decimal | None
    data_quality_status: str
    quality_flags: tuple[str, ...]


def calculate_daily_performance(data: DailyPerformanceInput) -> DailyPerformanceResult:
    """Calculate daily yields, PR and an explicitly non-technical availability proxy."""
    if data.plant_dc_capacity_kwp <= 0:
        raise ValueError("plant DC capacity must be positive")
    if data.poa_irradiation_kwh_m2 <= 0:
        raise ValueError("POA irradiation must be positive")
    if not data.solar_model_version.strip():
        raise ValueError("solar model version cannot be blank")
    if not data.climate_source.strip():
        raise ValueError("climate source cannot be blank")
    if any(device.energy_kwh is not None and device.energy_kwh < 0 for device in data.devices):
        raise ValueError("device energy cannot be negative")

    reporting_devices = tuple(
        device
        for device in data.devices
        if device.energy_kwh is not None and device.data_status != "UNAVAILABLE"
    )
    if not any(device.energy_kwh is not None for device in data.devices):
        raise ValueError("at least one measured energy value is required")
    measured_energy = sum(
        (device.energy_kwh for device in data.devices if device.energy_kwh is not None),
        start=Decimal(0),
    )
    final_yield = measured_energy / data.plant_dc_capacity_kwp
    reference_yield = data.poa_irradiation_kwh_m2 / REFERENCE_IRRADIANCE_KW_M2
    performance_ratio = final_yield / reference_yield

    temperature_corrected_pr: Decimal | None = None
    if (
        data.temperature_adjusted_poa_equivalent_kwh_m2 is not None
        and data.temperature_adjusted_poa_equivalent_kwh_m2 > 0
    ):
        temperature_reference_yield = (
            data.temperature_adjusted_poa_equivalent_kwh_m2
            / REFERENCE_IRRADIANCE_KW_M2
        )
        temperature_corrected_pr = final_yield / temperature_reference_yield

    flags: list[str] = ["POA_MODELED_NOT_MEASURED", "UNCERTAINTY_NOT_QUANTIFIED"]
    device_capacities_known = bool(data.devices) and all(
        device.dc_capacity_kwp is not None and device.dc_capacity_kwp > 0
        for device in data.devices
    )
    reporting_availability: Decimal | None = None
    reporting_capacity: Decimal | None = None
    configured_capacity: Decimal | None = None
    if device_capacities_known:
        configured_capacity = sum(
            (device.dc_capacity_kwp for device in data.devices if device.dc_capacity_kwp),
            start=Decimal(0),
        )
        reporting_capacity = sum(
            (
                device.dc_capacity_kwp
                for device in reporting_devices
                if device.dc_capacity_kwp is not None
            ),
            start=Decimal(0),
        )
        reporting_availability = reporting_capacity / configured_capacity
        capacity_difference = abs(configured_capacity - data.plant_dc_capacity_kwp)
        if capacity_difference > data.plant_dc_capacity_kwp * Decimal("0.01"):
            flags.append("DEVICE_CAPACITY_SUM_DIFFERS_FROM_PLANT")
    else:
        flags.append("REPORTING_AVAILABILITY_UNAVAILABLE_MISSING_DEVICE_CAPACITY")

    missing_or_unavailable = any(
        device.energy_kwh is None or device.data_status == "UNAVAILABLE"
        for device in data.devices
    )
    statuses = {device.data_status for device in data.devices if device.data_status is not None}
    if missing_or_unavailable or "INCOMPLETE" in statuses:
        data_quality_status = "INCOMPLETE"
        flags.append("ENERGY_DATA_INCOMPLETE")
    elif "PROVISIONAL" in statuses:
        data_quality_status = "PROVISIONAL"
        flags.append("ENERGY_DATA_PROVISIONAL")
    else:
        data_quality_status = "FINAL"
    if performance_ratio > Decimal("1.20"):
        flags.append("PERFORMANCE_RATIO_ABOVE_EXPECTED_RANGE")

    return DailyPerformanceResult(
        measured_energy_kwh=_quantize(measured_energy, "0.001"),
        final_yield_kwh_per_kwp=_quantize(final_yield, "0.001"),
        reference_yield_hours=_quantize(reference_yield, "0.001"),
        performance_ratio=_quantize(performance_ratio, "0.0001"),
        temperature_corrected_performance_ratio=(
            _quantize(temperature_corrected_pr, "0.0001")
            if temperature_corrected_pr is not None
            else None
        ),
        reporting_availability_ratio=(
            _quantize(reporting_availability, "0.0001")
            if reporting_availability is not None
            else None
        ),
        reporting_device_count=len(reporting_devices),
        configured_device_count=len(data.devices),
        reporting_capacity_kwp=(
            _quantize(reporting_capacity, "0.001")
            if reporting_capacity is not None
            else None
        ),
        configured_device_capacity_kwp=(
            _quantize(configured_capacity, "0.001")
            if configured_capacity is not None
            else None
        ),
        data_quality_status=data_quality_status,
        quality_flags=tuple(flags),
    )


def _quantize(value: Decimal, quantum: str) -> Decimal:
    return value.quantize(Decimal(quantum), rounding=ROUND_HALF_UP)
