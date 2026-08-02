from datetime import date
from decimal import Decimal

import pytest

from mplacas.photovoltaic.poa import (
    MODEL_VERSION,
    DailySolarModelInput,
    calculate_daily_solar_model,
)


def _input(**overrides) -> DailySolarModelInput:
    values = {
        "observation_date": date(2026, 6, 21),
        "latitude_degrees": Decimal("-17.744"),
        "ghi_kwh_m2": Decimal("5.100"),
        "array_tilt_degrees": Decimal("20"),
        "array_azimuth_degrees": Decimal("0"),
        "module_technology": "MONOCRYSTALLINE_SILICON",
        "climate_source": "OPEN_METEO",
        "ambient_temperature_c": Decimal("28.40"),
    }
    values.update(overrides)
    return DailySolarModelInput(**values)


def test_horizontal_plane_preserves_daily_ghi() -> None:
    result = calculate_daily_solar_model(
        _input(
            observation_date=date(2026, 3, 20),
            latitude_degrees=Decimal(0),
            ghi_kwh_m2=Decimal("5.000"),
            array_tilt_degrees=Decimal(0),
        )
    )

    assert result.model_version == MODEL_VERSION
    assert result.ghi_kwh_m2 == Decimal("5.000")
    assert result.poa_irradiation_kwh_m2 == Decimal("5.000")
    assert result.beam_horizontal_kwh_m2 + result.diffuse_horizontal_kwh_m2 == Decimal(
        "5.000"
    )


def test_north_facing_plane_wins_in_southern_hemisphere_winter() -> None:
    north = calculate_daily_solar_model(_input(array_azimuth_degrees=Decimal(0)))
    south = calculate_daily_solar_model(_input(array_azimuth_degrees=Decimal(180)))

    assert north.poa_irradiation_kwh_m2 == Decimal("6.508")
    assert south.poa_irradiation_kwh_m2 == Decimal("3.293")
    assert north.poa_irradiation_kwh_m2 > north.ghi_kwh_m2
    assert north.poa_irradiation_kwh_m2 > south.poa_irradiation_kwh_m2


def test_thermal_correction_is_explicit_and_reduces_hot_module_output() -> None:
    result = calculate_daily_solar_model(_input())

    assert result.cell_temperature_c == Decimal("47.00")
    assert result.temperature_coefficient_per_c == Decimal("-0.0040")
    assert result.temperature_factor == Decimal("0.9120")
    assert result.temperature_adjusted_poa_equivalent_kwh_m2 == Decimal("5.935")
    assert result.temperature_adjusted_poa_equivalent_kwh_m2 < result.poa_irradiation_kwh_m2
    assert "CELL_TEMPERATURE_NOCT_SIMPLIFIED" in result.quality_flags
    assert "AMBIENT_DAILY_MEAN" in result.quality_flags
    assert "WIND_UNAVAILABLE" in result.quality_flags


def test_missing_temperature_is_not_invented() -> None:
    result = calculate_daily_solar_model(_input(ambient_temperature_c=None))

    assert result.cell_temperature_c is None
    assert result.temperature_factor is None
    assert result.temperature_adjusted_poa_equivalent_kwh_m2 is None
    assert "TEMPERATURE_UNAVAILABLE" in result.quality_flags


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"ghi_kwh_m2": Decimal("-0.1")}, "GHI"),
        ({"array_tilt_degrees": Decimal("91")}, "tilt"),
        ({"array_azimuth_degrees": Decimal("360")}, "azimuth"),
        ({"module_technology": "UNKNOWN"}, "technology"),
        ({"climate_source": "   "}, "source"),
    ],
)
def test_invalid_model_inputs_fail_closed(overrides, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        calculate_daily_solar_model(_input(**overrides))
