"""Pure daily POA and module-temperature model.

The input radiation is daily GHI. Direct/diffuse components are estimated
with the daily Erbs correlation and transposed with an isotropic-sky model.
This is intentionally not called Performance Ratio: it contains no measured
energy or availability term.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal


MODEL_VERSION = "MPLACAS_POA_DAILY_ERBS_ISOTROPIC_V1"
GROUND_ALBEDO = Decimal("0.20")
NOCT_C = Decimal("45.0")
MODEL_ASSUMPTIONS = {
    "ground_albedo": "0.20",
    "noct_c": "45.0",
    "input_granularity": "DAILY",
    "decomposition": "ERBS_DAILY",
    "transposition": "ISOTROPIC_SKY",
}
_SOLAR_CONSTANT_KW_M2 = 1.367
_INTEGRATION_STEPS = 288

TEMPERATURE_COEFFICIENTS_PER_C: dict[str, Decimal] = {
    "MONOCRYSTALLINE_SILICON": Decimal("-0.0040"),
    "POLYCRYSTALLINE_SILICON": Decimal("-0.0041"),
    "THIN_FILM": Decimal("-0.0030"),
    "OTHER": Decimal("-0.0040"),
}


@dataclass(frozen=True, slots=True)
class DailySolarModelInput:
    observation_date: date
    latitude_degrees: Decimal
    ghi_kwh_m2: Decimal
    array_tilt_degrees: Decimal
    array_azimuth_degrees: Decimal
    module_technology: str
    climate_source: str
    ambient_temperature_c: Decimal | None = None


@dataclass(frozen=True, slots=True)
class DailySolarModelResult:
    observation_date: date
    climate_source: str
    model_version: str
    ghi_kwh_m2: Decimal
    poa_irradiation_kwh_m2: Decimal
    beam_horizontal_kwh_m2: Decimal
    diffuse_horizontal_kwh_m2: Decimal
    extraterrestrial_horizontal_kwh_m2: Decimal
    cell_temperature_c: Decimal | None
    temperature_coefficient_per_c: Decimal
    temperature_factor: Decimal | None
    temperature_adjusted_poa_equivalent_kwh_m2: Decimal | None
    quality_flags: tuple[str, ...]


def calculate_daily_solar_model(data: DailySolarModelInput) -> DailySolarModelResult:
    """Estimate daily plane-of-array irradiation and thermal derating."""
    _validate(data)
    latitude = math.radians(float(data.latitude_degrees))
    tilt = math.radians(float(data.array_tilt_degrees))
    azimuth = math.radians(float(data.array_azimuth_degrees))
    day_of_year = data.observation_date.timetuple().tm_yday
    declination = math.radians(23.45 * math.sin(2 * math.pi * (284 + day_of_year) / 365))

    extraterrestrial, daylight_hours = _extraterrestrial_daily(
        latitude, declination, day_of_year
    )
    ghi = float(data.ghi_kwh_m2)
    if extraterrestrial <= 0 and ghi > 0:
        raise ValueError("positive GHI is inconsistent with polar night geometry")

    clearness_index = min(max(ghi / extraterrestrial, 0.0), 1.0) if extraterrestrial else 0.0
    diffuse_fraction = _daily_diffuse_fraction(clearness_index)
    diffuse = ghi * diffuse_fraction
    beam = max(ghi - diffuse, 0.0)
    beam_ratio = _daily_beam_transposition_ratio(latitude, declination, tilt, azimuth)
    sky_factor = (1 + math.cos(tilt)) / 2
    ground_factor = (1 - math.cos(tilt)) / 2
    poa = beam * beam_ratio + diffuse * sky_factor + ghi * float(GROUND_ALBEDO) * ground_factor
    poa = max(poa, 0.0)

    coefficient = TEMPERATURE_COEFFICIENTS_PER_C[data.module_technology]
    cell_temperature: Decimal | None = None
    temperature_factor: Decimal | None = None
    corrected_poa: Decimal | None = None
    flags = ["DAILY_AGGREGATE", "DNI_DHI_ESTIMATED_ERBS", "ISOTROPIC_SKY"]
    if ghi > extraterrestrial * 1.05 and extraterrestrial > 0:
        flags.append("GHI_ABOVE_EXTRATERRESTRIAL")
    if data.ambient_temperature_c is None:
        flags.append("TEMPERATURE_UNAVAILABLE")
    else:
        average_daylight_poa_kw_m2 = (
            Decimal(str(poa / daylight_hours)) if daylight_hours else Decimal(0)
        )
        cell_temperature = data.ambient_temperature_c + (
            (NOCT_C - Decimal(20)) / Decimal("0.8") * average_daylight_poa_kw_m2
        )
        temperature_factor = Decimal(1) + coefficient * (cell_temperature - Decimal(25))
        if temperature_factor <= 0:
            raise ValueError("thermal correction factor is non-positive")
        corrected_poa = Decimal(str(poa)) * temperature_factor
        flags.extend(
            (
                "CELL_TEMPERATURE_NOCT_SIMPLIFIED",
                "AMBIENT_DAILY_MEAN",
                "WIND_UNAVAILABLE",
            )
        )

    return DailySolarModelResult(
        observation_date=data.observation_date,
        climate_source=data.climate_source.strip(),
        model_version=MODEL_VERSION,
        ghi_kwh_m2=_quantize(Decimal(str(ghi)), "0.001"),
        poa_irradiation_kwh_m2=_quantize(Decimal(str(poa)), "0.001"),
        beam_horizontal_kwh_m2=_quantize(Decimal(str(beam)), "0.001"),
        diffuse_horizontal_kwh_m2=_quantize(Decimal(str(diffuse)), "0.001"),
        extraterrestrial_horizontal_kwh_m2=_quantize(
            Decimal(str(extraterrestrial)), "0.001"
        ),
        cell_temperature_c=(
            _quantize(cell_temperature, "0.01") if cell_temperature is not None else None
        ),
        temperature_coefficient_per_c=coefficient,
        temperature_factor=(
            _quantize(temperature_factor, "0.0001")
            if temperature_factor is not None
            else None
        ),
        temperature_adjusted_poa_equivalent_kwh_m2=(
            _quantize(corrected_poa, "0.001") if corrected_poa is not None else None
        ),
        quality_flags=tuple(flags),
    )


def _validate(data: DailySolarModelInput) -> None:
    if not Decimal("-90") <= data.latitude_degrees <= Decimal("90"):
        raise ValueError("latitude must be between -90 and 90 degrees")
    if not Decimal(0) <= data.array_tilt_degrees <= Decimal(90):
        raise ValueError("array tilt must be between 0 and 90 degrees")
    if not Decimal(0) <= data.array_azimuth_degrees < Decimal(360):
        raise ValueError("array azimuth must be in [0, 360) degrees")
    if data.ghi_kwh_m2 < 0:
        raise ValueError("GHI cannot be negative")
    if data.module_technology not in TEMPERATURE_COEFFICIENTS_PER_C:
        raise ValueError("unsupported module technology")
    if not data.climate_source.strip():
        raise ValueError("climate source cannot be blank")
    if len(data.climate_source.strip()) > 40:
        raise ValueError("climate source is too long")
    if data.ambient_temperature_c is not None and not (
        Decimal("-90") <= data.ambient_temperature_c <= Decimal("60")
    ):
        raise ValueError("ambient temperature is outside the supported range")


def _extraterrestrial_daily(
    latitude: float, declination: float, day_of_year: int
) -> tuple[float, float]:
    sunset_argument = -math.tan(latitude) * math.tan(declination)
    if sunset_argument >= 1:
        sunset_hour_angle = 0.0
    elif sunset_argument <= -1:
        sunset_hour_angle = math.pi
    else:
        sunset_hour_angle = math.acos(sunset_argument)
    distance_factor = 1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)
    irradiation = (
        24
        / math.pi
        * _SOLAR_CONSTANT_KW_M2
        * distance_factor
        * (
            math.cos(latitude) * math.cos(declination) * math.sin(sunset_hour_angle)
            + sunset_hour_angle * math.sin(latitude) * math.sin(declination)
        )
    )
    return max(irradiation, 0.0), 24 * sunset_hour_angle / math.pi


def _daily_diffuse_fraction(clearness_index: float) -> float:
    if clearness_index <= 0.22:
        return 1 - 0.09 * clearness_index
    if clearness_index <= 0.8:
        kt = clearness_index
        return 0.9511 - 0.1604 * kt + 4.388 * kt**2 - 16.638 * kt**3 + 12.336 * kt**4
    return 0.165


def _daily_beam_transposition_ratio(
    latitude: float, declination: float, tilt: float, azimuth: float
) -> float:
    horizontal_sum = 0.0
    tilted_sum = 0.0
    for step in range(_INTEGRATION_STEPS):
        hour_angle = -math.pi + (step + 0.5) * 2 * math.pi / _INTEGRATION_STEPS
        east = -math.cos(declination) * math.sin(hour_angle)
        north = (
            math.cos(latitude) * math.sin(declination)
            - math.sin(latitude) * math.cos(declination) * math.cos(hour_angle)
        )
        up = (
            math.sin(latitude) * math.sin(declination)
            + math.cos(latitude) * math.cos(declination) * math.cos(hour_angle)
        )
        if up <= 0:
            continue
        incidence = (
            east * math.sin(tilt) * math.sin(azimuth)
            + north * math.sin(tilt) * math.cos(azimuth)
            + up * math.cos(tilt)
        )
        horizontal_sum += up
        tilted_sum += max(incidence, 0.0)
    return tilted_sum / horizontal_sum if horizontal_sum else 0.0


def _quantize(value: Decimal, quantum: str) -> Decimal:
    return value.quantize(Decimal(quantum), rounding=ROUND_HALF_UP)
