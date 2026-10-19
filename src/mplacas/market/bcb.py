"""Cliente mínimo da API pública de séries temporais do Banco Central (SGS).

Formato: ``GET https://api.bcb.gov.br/dados/serie/bcdata.sgs.{código}/dados
?formato=json&dataInicial=DD/MM/AAAA&dataFinal=DD/MM/AAAA`` → lista de
``{"data": "DD/MM/AAAA", "valor": "0.07"}``. Séries usadas (mensais, em % ao
mês): 4391 = CDI acumulado no mês; 433 = IPCA, variação mensal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

SGS_SERIES = {"CDI": 4391, "IPCA": 433}
SOURCE = "BCB_SGS"


class BcbSgsError(RuntimeError):
    """A série não pôde ser obtida ou validada."""


@dataclass(frozen=True, slots=True)
class MonthlyRate:
    reference_month: str  # "AAAA-MM"
    rate_percent: Decimal  # % ao mês


class BcbSgsClient:
    def __init__(
        self,
        *,
        base_url: str = "https://api.bcb.gov.br",
        timeout_seconds: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def monthly_rates(
        self, index_code: str, *, start: date, end: date
    ) -> tuple[MonthlyRate, ...]:
        series = SGS_SERIES.get(index_code)
        if series is None:
            raise BcbSgsError(f"unknown index: {index_code}")
        url = f"{self._base_url}/dados/serie/bcdata.sgs.{series}/dados"
        params = {
            "formato": "json",
            "dataInicial": start.strftime("%d/%m/%Y"),
            "dataFinal": end.strftime("%d/%m/%Y"),
        }
        try:
            if self._client is not None:
                response = await self._client.get(url, params=params, timeout=self._timeout_seconds)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise BcbSgsError("BCB request failed") from exc
        if response.status_code != 200:
            raise BcbSgsError(f"BCB returned HTTP {response.status_code}")
        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise BcbSgsError("BCB returned invalid JSON") from exc
        return parse_monthly_payload(payload)


def parse_monthly_payload(payload: Any) -> tuple[MonthlyRate, ...]:
    if not isinstance(payload, list):
        raise BcbSgsError("BCB payload is not a list")
    rates: list[MonthlyRate] = []
    for item in payload:
        if not isinstance(item, dict):
            raise BcbSgsError("BCB item is not an object")
        raw_date, raw_value = item.get("data"), item.get("valor")
        if not isinstance(raw_date, str) or not isinstance(raw_value, str):
            raise BcbSgsError("BCB item has unexpected fields")
        parts = raw_date.split("/")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            raise BcbSgsError("BCB date is malformed")
        try:
            value = Decimal(raw_value.replace(",", "."))
        except InvalidOperation as exc:
            raise BcbSgsError("BCB value is not a number") from exc
        # Taxa mensal plausível: entre -5% e +10% ao mês (deflação forte a
        # juros muito altos). Fora disso é erro de contrato, não dado.
        if not (Decimal("-5") <= value <= Decimal("10")):
            raise BcbSgsError("BCB value outside plausible monthly range")
        rates.append(MonthlyRate(reference_month=f"{parts[2]}-{parts[1]}", rate_percent=value))
    return tuple(rates)
