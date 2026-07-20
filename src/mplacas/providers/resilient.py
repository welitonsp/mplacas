from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date

from mplacas.providers.base import (
    DailyEnergy,
    DeviceOverview,
    ProviderIncompleteDataError,
    ProviderUnavailableError,
    SolarDevice,
    SolarProvider,
)

_TRANSIENT_ERRORS = (ProviderUnavailableError, ProviderIncompleteDataError)

logger = logging.getLogger(__name__)

_MAX_BACKOFF_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Política de retry para falhas transitórias do provedor.

    Aplica-se a falhas transitórias — ``ProviderUnavailableError`` (timeout,
    5xx) e ``ProviderIncompleteDataError`` (resposta sem os dados esperados).
    Falhas de autenticação e de esquema não são transitórias e devem falhar de
    imediato, sem mascarar um problema real de contrato ou credencial.
    """

    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds must be non-negative")
        if self.backoff_multiplier < 1:
            raise ValueError("backoff_multiplier must be at least 1")

    def delay_for(self, attempt: int) -> float:
        delay = self.base_delay_seconds * (self.backoff_multiplier ** (attempt - 1))
        return min(_MAX_BACKOFF_SECONDS, delay)


class ResilientSolarProvider(SolarProvider):
    """Envolve um ``SolarProvider`` com retry para indisponibilidade transitória.

    Preserva o contrato do provedor: para o restante do sistema, é apenas um
    ``SolarProvider``. Após esgotar as tentativas, propaga o
    ``ProviderUnavailableError`` original, permitindo que a fila de coleta
    reagende a tarefa.
    """

    def __init__(
        self,
        inner: SolarProvider,
        *,
        policy: RetryPolicy | None = None,
        sleep=asyncio.sleep,
    ) -> None:
        self._inner = inner
        self._policy = policy or RetryPolicy()
        self._sleep = sleep

    async def list_devices(self) -> list[SolarDevice]:
        return await self._with_retry("list_devices", self._inner.list_devices)

    async def get_overview(self, serial_number: str) -> DeviceOverview:
        return await self._with_retry(
            "get_overview",
            lambda: self._inner.get_overview(serial_number),
        )

    async def get_daily_energy(
        self,
        serial_number: str,
        start: date,
        end: date,
        *,
        expect_complete: bool = False,
    ) -> list[DailyEnergy]:
        return await self._with_retry(
            "get_daily_energy",
            lambda: self._inner.get_daily_energy(
                serial_number, start, end, expect_complete=expect_complete
            ),
        )

    async def _with_retry(self, operation: str, call):
        last_error: Exception | None = None
        for attempt in range(1, self._policy.max_attempts + 1):
            try:
                return await call()
            except _TRANSIENT_ERRORS as exc:
                last_error = exc
                if attempt >= self._policy.max_attempts:
                    break
                delay = self._policy.delay_for(attempt)
                logger.warning(
                    "provider_transient_retry",
                    extra={
                        "operation": operation,
                        "attempt": attempt,
                        "max_attempts": self._policy.max_attempts,
                        "delay_seconds": delay,
                    },
                )
                await self._sleep(delay)
        assert last_error is not None
        raise last_error
