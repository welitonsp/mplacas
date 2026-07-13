from datetime import date
from decimal import Decimal

import httpx
import pytest

from mplacas.climate.open_meteo import (
    OpenMeteoHistoricalProvider,
    OpenMeteoProviderError,
)


@pytest.mark.asyncio
async def test_parses_daily_open_meteo_response_and_converts_radiation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["daily"] == (
            "shortwave_radiation_sum,cloud_cover_mean,precipitation_sum"
        )
        return httpx.Response(
            200,
            json={
                "daily_units": {
                    "shortwave_radiation_sum": "MJ/m²",
                    "cloud_cover_mean": "%",
                    "precipitation_sum": "mm",
                },
                "daily": {
                    "time": ["2026-07-10", "2026-07-11"],
                    "shortwave_radiation_sum": [3.6, 7.2],
                    "cloud_cover_mean": [40, 20],
                    "precipitation_sum": [1.5, 0],
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenMeteoHistoricalProvider(
            base_url="https://weather.example/v1/archive",
            client=client,
        )
        observations = await provider.daily_observations(
            latitude=-17.7,
            longitude=-48.6,
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 11),
        )

    assert len(observations) == 2
    assert observations[0].irradiation_kwh_m2 == Decimal("1.0")
    assert observations[0].cloud_cover_percent == Decimal("40")
    assert observations[0].precipitation_mm == Decimal("1.5")
    assert observations[0].source == "OPEN_METEO_ARCHIVE"


@pytest.mark.asyncio
async def test_rejects_misaligned_daily_arrays() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "daily_units": {"shortwave_radiation_sum": "MJ/m²"},
                "daily": {
                    "time": ["2026-07-10"],
                    "shortwave_radiation_sum": [3.6, 7.2],
                    "cloud_cover_mean": [40],
                    "precipitation_sum": [0],
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenMeteoHistoricalProvider(client=client)
        with pytest.raises(OpenMeteoProviderError, match="misaligned"):
            await provider.daily_observations(
                latitude=-17.7,
                longitude=-48.6,
                start_date=date(2026, 7, 10),
                end_date=date(2026, 7, 10),
            )
