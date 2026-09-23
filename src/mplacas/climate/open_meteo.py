from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal
from typing import Any

import httpx

from mplacas.climate.models import DailyClimateObservation

logger = logging.getLogger(__name__)

# Teto para o tempo de espera respeitado a partir do cabeçalho ``Retry-After``
# de um 429 — evita que um provedor mal-comportado prenda a chamada por muito
# tempo. Custo zero: a espera é sempre dentro da mesma chamada HTTP, nunca vira
# um novo agendamento.
_MAX_RETRY_AFTER_SECONDS = 30.0


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
        max_attempts: int = 3,
        backoff_seconds: tuple[float, ...] = (2.0, 5.0),
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep

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
            "daily": (
                "shortwave_radiation_sum,cloud_cover_mean,precipitation_sum,"
                "temperature_2m_mean"
            ),
            "timezone": "auto",
        }
        payload = await self._fetch_with_retry(params)
        return self._parse_payload(payload)

    async def _fetch_with_retry(self, params: dict[str, str | float]) -> Any:
        """Busca o payload retentando apenas falhas transitórias.

        Retentável: timeout, erro de rede/transporte, HTTP 429 e 5xx — nesses
        casos o pedido provavelmente não chegou a ser processado de fato.
        Não retentável: demais 4xx (erro do cliente, repetir não ajuda) e
        payload inválido/JSON malformado (erro de contrato, não de rede).
        """
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._request(params)
                response.raise_for_status()
                payload = response.json()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if not self._is_retryable_status(status_code) or attempt >= self._max_attempts:
                    raise OpenMeteoProviderError("weather provider request failed") from exc
                delay = self._delay_for(
                    attempt, retry_after=self._retry_after_seconds(exc.response)
                )
                self._log_retry(attempt=attempt, delay=delay, reason=f"http_{status_code}")
                await self._sleep(delay)
                continue
            except httpx.TransportError as exc:
                if attempt >= self._max_attempts:
                    raise OpenMeteoProviderError("weather provider request failed") from exc
                delay = self._delay_for(attempt)
                self._log_retry(attempt=attempt, delay=delay, reason=type(exc).__name__)
                await self._sleep(delay)
                continue
            except (httpx.HTTPError, ValueError) as exc:
                raise OpenMeteoProviderError("weather provider request failed") from exc
            else:
                return payload
        # Inalcançável: o laço acima sempre retorna ou levanta antes de esgotar
        # as tentativas. Mantido para o mypy garantir que a função sempre
        # produz um resultado ou uma exceção.
        raise OpenMeteoProviderError("weather provider request failed")

    async def _request(self, params: dict[str, str | float]) -> httpx.Response:
        if self._client is not None:
            return await self._client.get(
                self._base_url,
                params=params,
                timeout=self._timeout_seconds,
            )
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            return await client.get(self._base_url, params=params)

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code == 429 or 500 <= status_code < 600

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> float | None:
        raw = response.headers.get("Retry-After")
        if raw is None:
            return None
        try:
            seconds = float(raw)
        except ValueError:
            # Formato HTTP-date não é suportado; cai para o backoff padrão.
            return None
        return seconds if seconds >= 0 else None

    def _delay_for(self, attempt: int, *, retry_after: float | None = None) -> float:
        if retry_after is not None:
            return min(retry_after, _MAX_RETRY_AFTER_SECONDS)
        base = self._backoff_seconds[min(attempt - 1, len(self._backoff_seconds) - 1)]
        jitter = random.uniform(0, base * 0.1)
        return base + jitter

    @staticmethod
    def _log_retry(*, attempt: int, delay: float, reason: str) -> None:
        logger.warning(
            "open_meteo_retry",
            extra={
                "attempt": attempt,
                "delay_seconds": delay,
                "reason": reason,
            },
        )

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
        if "temperature_2m_mean" in units and units.get("temperature_2m_mean") != "°C":
            raise OpenMeteoProviderError("unexpected temperature unit")

        dates = daily.get("time")
        radiation = daily.get("shortwave_radiation_sum")
        cloud_cover = daily.get("cloud_cover_mean")
        precipitation = daily.get("precipitation_sum")
        temperature = daily.get("temperature_2m_mean")
        if temperature is None:
            temperature = [None] * (len(dates) if isinstance(dates, list) else 0)
        if (
            not isinstance(dates, list)
            or not isinstance(radiation, list)
            or not isinstance(cloud_cover, list)
            or not isinstance(precipitation, list)
            or not isinstance(temperature, list)
        ):
            raise OpenMeteoProviderError("weather provider returned incomplete daily arrays")
        arrays = (dates, radiation, cloud_cover, precipitation, temperature)
        if len({len(item) for item in arrays}) != 1:
            raise OpenMeteoProviderError("weather provider returned misaligned daily arrays")

        observations: list[DailyClimateObservation] = []
        for raw_date, raw_radiation, raw_cloud, raw_precipitation, raw_temperature in zip(
            dates,
            radiation,
            cloud_cover,
            precipitation,
            temperature,
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
                    temperature_mean_c=(
                        Decimal(str(raw_temperature))
                        if raw_temperature is not None
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
