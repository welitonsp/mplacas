from datetime import date
from decimal import Decimal

import httpx
import pytest

from mplacas.climate.open_meteo import (
    OpenMeteoHistoricalProvider,
    OpenMeteoProviderError,
)

_SUCCESS_PAYLOAD = {
    "daily_units": {
        "shortwave_radiation_sum": "MJ/m²",
        "cloud_cover_mean": "%",
        "precipitation_sum": "mm",
        "temperature_2m_mean": "°C",
    },
    "daily": {
        "time": ["2026-07-10"],
        "shortwave_radiation_sum": [3.6],
        "cloud_cover_mean": [40],
        "precipitation_sum": [1.5],
        "temperature_2m_mean": [28.4],
    },
}


class _SleepSpy:
    """Substituto para asyncio.sleep que registra as esperas sem dormir de verdade."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


@pytest.mark.asyncio
async def test_parses_daily_open_meteo_response_and_converts_radiation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["daily"] == (
            "shortwave_radiation_sum,cloud_cover_mean,precipitation_sum,"
            "temperature_2m_mean"
        )
        return httpx.Response(
            200,
            json={
                "daily_units": {
                    "shortwave_radiation_sum": "MJ/m²",
                    "cloud_cover_mean": "%",
                    "precipitation_sum": "mm",
                    "temperature_2m_mean": "°C",
                },
                "daily": {
                    "time": ["2026-07-10", "2026-07-11"],
                    "shortwave_radiation_sum": [3.6, 7.2],
                    "cloud_cover_mean": [40, 20],
                    "precipitation_sum": [1.5, 0],
                    "temperature_2m_mean": [28.4, 31.9],
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
    assert observations[0].temperature_mean_c == Decimal("28.4")
    assert observations[1].temperature_mean_c == Decimal("31.9")
    assert observations[0].source == "OPEN_METEO_ARCHIVE"


@pytest.mark.asyncio
async def test_parses_response_without_temperature_field() -> None:
    """Older/degraded payloads without temperature_2m_mean must not break collection."""

    def handler(_: httpx.Request) -> httpx.Response:
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
        provider = OpenMeteoHistoricalProvider(client=client)
        observations = await provider.daily_observations(
            latitude=-17.7,
            longitude=-48.6,
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 11),
        )

    assert len(observations) == 2
    assert observations[0].temperature_mean_c is None
    assert observations[1].temperature_mean_c is None
    assert observations[0].irradiation_kwh_m2 == Decimal("1.0")


@pytest.mark.asyncio
async def test_parses_response_with_null_temperature_for_a_single_day() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "daily_units": {
                    "shortwave_radiation_sum": "MJ/m²",
                    "cloud_cover_mean": "%",
                    "precipitation_sum": "mm",
                    "temperature_2m_mean": "°C",
                },
                "daily": {
                    "time": ["2026-07-10", "2026-07-11"],
                    "shortwave_radiation_sum": [3.6, 7.2],
                    "cloud_cover_mean": [40, 20],
                    "precipitation_sum": [1.5, 0],
                    "temperature_2m_mean": [None, 31.9],
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenMeteoHistoricalProvider(client=client)
        observations = await provider.daily_observations(
            latitude=-17.7,
            longitude=-48.6,
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 11),
        )

    assert observations[0].temperature_mean_c is None
    assert observations[1].temperature_mean_c == Decimal("31.9")


@pytest.mark.asyncio
async def test_rejects_unexpected_temperature_unit() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "daily_units": {
                    "shortwave_radiation_sum": "MJ/m²",
                    "temperature_2m_mean": "°F",
                },
                "daily": {
                    "time": ["2026-07-10"],
                    "shortwave_radiation_sum": [3.6],
                    "cloud_cover_mean": [40],
                    "precipitation_sum": [0],
                    "temperature_2m_mean": [82.0],
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenMeteoHistoricalProvider(client=client)
        with pytest.raises(OpenMeteoProviderError, match="temperature unit"):
            await provider.daily_observations(
                latitude=-17.7,
                longitude=-48.6,
                start_date=date(2026, 7, 10),
                end_date=date(2026, 7, 10),
            )


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


@pytest.mark.asyncio
async def test_retries_timeout_and_succeeds_on_second_attempt() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, json=_SUCCESS_PAYLOAD)

    sleep = _SleepSpy()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenMeteoHistoricalProvider(client=client, sleep=sleep)
        observations = await provider.daily_observations(
            latitude=-17.7,
            longitude=-48.6,
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 10),
        )

    assert len(observations) == 1
    assert attempts["count"] == 2
    assert len(sleep.calls) == 1


@pytest.mark.asyncio
async def test_exhausts_retries_after_repeated_timeouts() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        raise httpx.ReadTimeout("slow", request=request)

    sleep = _SleepSpy()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenMeteoHistoricalProvider(client=client, sleep=sleep)
        with pytest.raises(OpenMeteoProviderError, match="weather provider request failed"):
            await provider.daily_observations(
                latitude=-17.7,
                longitude=-48.6,
                start_date=date(2026, 7, 10),
                end_date=date(2026, 7, 10),
            )

    assert attempts["count"] == 3
    assert len(sleep.calls) == 2


@pytest.mark.asyncio
async def test_retries_503_and_succeeds_on_second_attempt() -> None:
    attempts = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(503, text="service unavailable")
        return httpx.Response(200, json=_SUCCESS_PAYLOAD)

    sleep = _SleepSpy()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenMeteoHistoricalProvider(client=client, sleep=sleep)
        observations = await provider.daily_observations(
            latitude=-17.7,
            longitude=-48.6,
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 10),
        )

    assert len(observations) == 1
    assert attempts["count"] == 2
    assert len(sleep.calls) == 1


@pytest.mark.asyncio
async def test_400_fails_immediately_without_retrying() -> None:
    attempts = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(400, text="bad request")

    sleep = _SleepSpy()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenMeteoHistoricalProvider(client=client, sleep=sleep)
        with pytest.raises(OpenMeteoProviderError, match="weather provider request failed"):
            await provider.daily_observations(
                latitude=-17.7,
                longitude=-48.6,
                start_date=date(2026, 7, 10),
                end_date=date(2026, 7, 10),
            )

    assert attempts["count"] == 1
    assert sleep.calls == []


@pytest.mark.asyncio
async def test_invalid_payload_fails_immediately_without_retrying() -> None:
    """Erros de parse/contrato não são transitórios: retentar não ajuda."""

    attempts = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(200, content=b"not json")

    sleep = _SleepSpy()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenMeteoHistoricalProvider(client=client, sleep=sleep)
        with pytest.raises(OpenMeteoProviderError, match="weather provider request failed"):
            await provider.daily_observations(
                latitude=-17.7,
                longitude=-48.6,
                start_date=date(2026, 7, 10),
                end_date=date(2026, 7, 10),
            )

    assert attempts["count"] == 1
    assert sleep.calls == []


@pytest.mark.asyncio
async def test_429_respects_retry_after_header() -> None:
    attempts = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"}, text="slow down")
        return httpx.Response(200, json=_SUCCESS_PAYLOAD)

    sleep = _SleepSpy()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenMeteoHistoricalProvider(client=client, sleep=sleep)
        observations = await provider.daily_observations(
            latitude=-17.7,
            longitude=-48.6,
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 10),
        )

    assert len(observations) == 1
    assert attempts["count"] == 2
    assert sleep.calls == [7.0]


@pytest.mark.asyncio
async def test_429_retry_after_is_capped_at_thirty_seconds() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "120"}, text="slow down")

    sleep = _SleepSpy()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenMeteoHistoricalProvider(client=client, sleep=sleep, max_attempts=2)
        with pytest.raises(OpenMeteoProviderError, match="weather provider request failed"):
            await provider.daily_observations(
                latitude=-17.7,
                longitude=-48.6,
                start_date=date(2026, 7, 10),
                end_date=date(2026, 7, 10),
            )

    assert sleep.calls == [30.0]
