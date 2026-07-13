from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import httpx

from mplacas.climate.models import DailyClimateObservation


class OpenMeteoProviderError(RuntimeError):
    """Open-Meteo response could not be retrieved or validated."""


class OpenMeteoHistoricalProvider:
    SOURCE = "OPEN_METEO_ARCHIVE"

    def __init__(
        self,
        *,
        base_url: str = "https://archive-api.open-meteo.com/v1/archive",
        timeout_seconds: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout must be positive")
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def daily_observations(
        self,
        *,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
    ) -> tuple[DailyClimateObservation, ...]:
        params: dict[str, str | float] = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "daily": "shortwave_radiation_sum,cloud_cover_mean,precipitation_sum",
            "timezone": "auto",
        }
        try:
            if self._client is not None:
                response = await self._client.get(
                    self._base_url,
                    params=params,
                    timeout=self._timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.get(self._base_url, params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OpenMeteoProviderError("weather provider request failed") from exc

        return self._parse_payload(payload)

    def _parse_payload(self, payload: Any) -> tuple[DailyClimateObservation, ...]:
        if not isinstance(payload, dict):
            raise OpenMeteoProviderError("weather provider returned an invalid payload")
        if payload.get("error"):
            raise OpenMeteoProviderError("weather provider rejected the request")

        daily = payload.get("daily")
        units = payload.get("daily_units")
        if not isinstance(daily, dict) or not isinstance(units, dict):
            raise OpenMeteoProviderError("weather provider omitted daily data")
        if units.get("shortwave_radiation_sum") != "MJ/m²":
            raise OpenMeteoProviderError("unexpected solar radiation unit")

        dates = daily.get("time")
        radiation = daily.get("shortwave_radiation_sum")
        cloud_cover = daily.get("cloud_cover_mean")
        precipitation = daily.get("precipitation_sum")
        if (
            not isinstance(dates, list)
            or not isinstance(radiation, list)
            or not isinstance(cloud_cover, list)
            or not isinstance(precipitation, list)
        ):
            raise OpenMeteoProviderError("weather provider returned incomplete daily arrays")
        arrays = (dates, radiation, cloud_cover, precipitation)
        if len({len(item) for item in arrays}) != 1:
            raise OpenMeteoProviderError("weather provider returned misaligned daily arrays")

        observations: list[DailyClimateObservation] = []
        for raw_date, raw_radiation, raw_cloud, raw_precipitation in zip(
            dates,
            radiation,
            cloud_cover,
            precipitation,
            strict=True,
        ):
            try:
                observation = DailyClimateObservation(
                    observation_date=date.fromisoformat(str(raw_date)),
                    irradiation_kwh_m2=(
                        Decimal(str(raw_radiation)) / Decimal("3.6")
                        if raw_radiation is not None
                        else None
                    ),
                    cloud_cover_percent=(
                        Decimal(str(raw_cloud)) if raw_cloud is not None else None
                    ),
                    precipitation_mm=(
                        Decimal(str(raw_precipitation))
                        if raw_precipitation is not None
                        else None
                    ),
                    source=self.SOURCE,
                )
                observation.validate()
            except (ValueError, ArithmeticError) as exc:
                raise OpenMeteoProviderError(
                    "weather provider returned invalid daily values"
                ) from exc
            observations.append(observation)
        return tuple(observations)
