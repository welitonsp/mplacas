from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from mplacas.providers.base import (
    DailyEnergy,
    DeviceOverview,
    ProviderAuthError,
    ProviderIncompleteDataError,
    ProviderSchemaError,
    ProviderUnavailableError,
    SolarDevice,
    SolarProvider,
)


class NepViewerClient(SolarProvider):
    """Adaptador de leitura para a API web não oficial da NEPViewer.

    O restante do sistema não conhece endpoints nem formatos específicos da NEP.
    """

    def __init__(
        self,
        *,
        account: str,
        password: str,
        base_url: str = "https://api.nepviewer.net/v2",
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._account = account
        self._password = password
        self._token: str | None = None
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
            headers={"oem": "NEP", "client": "web", "app": "0"},
            transport=transport,
        )

    async def __aenter__(self) -> NepViewerClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _authenticate(self) -> None:
        data = await self._post(
            "sign-in",
            {"account": self._account, "password": self._password},
            authenticated=False,
        )
        try:
            token = data["tokenInfo"]["token"]
        except (KeyError, TypeError) as exc:
            raise ProviderSchemaError("NEPViewer não retornou token no formato esperado") from exc
        if not isinstance(token, str) or not token.strip():
            raise ProviderSchemaError("NEPViewer retornou token inválido")
        self._token = token

    async def _post(
        self, path: str, payload: dict[str, Any], *, authenticated: bool = True
    ) -> dict[str, Any]:
        if authenticated and not self._token:
            await self._authenticate()

        headers = {"Authorization": self._token} if authenticated and self._token else {}
        try:
            response = await self._client.post(path, json=payload, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderUnavailableError("NEPViewer indisponível ou com timeout") from exc

        if response.status_code in {401, 403}:
            if authenticated and self._token:
                self._token = None
                await self._authenticate()
                return await self._post(path, payload, authenticated=True)
            raise ProviderAuthError("Credenciais NEPViewer recusadas")
        if response.status_code >= 500:
            raise ProviderUnavailableError("NEPViewer apresentou falha temporária")
        if response.status_code >= 400:
            raise ProviderSchemaError(
                f"Resposta HTTP inesperada da NEPViewer: {response.status_code}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderSchemaError("NEPViewer retornou conteúdo não JSON") from exc
        if not isinstance(body, dict) or not isinstance(body.get("data"), dict):
            raise ProviderSchemaError("NEPViewer retornou envelope incompatível")
        return body["data"]

    @staticmethod
    def _decimal(value: Any, field: str) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ProviderSchemaError(f"Campo numérico inválido: {field}") from exc

    @staticmethod
    def _datetime(value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            raise ProviderSchemaError("Timestamp inválido")
        for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        raise ProviderSchemaError("Formato de timestamp desconhecido")

    async def list_devices(self) -> list[SolarDevice]:
        data = await self._post("device/list", {"page": {"size": 100, "num": 0}})
        rows = data.get("list")
        if not isinstance(rows, list):
            raise ProviderSchemaError("Lista de dispositivos ausente")
        devices: list[SolarDevice] = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("sn"), str):
                raise ProviderSchemaError("Dispositivo sem número de série")
            devices.append(
                SolarDevice(
                    serial_number=row["sn"],
                    model_name=(
                        row.get("modelName") if isinstance(row.get("modelName"), str) else None
                    ),
                    city=row.get("city") if isinstance(row.get("city"), str) else None,
                    last_update=self._datetime(row.get("lastUpdate")),
                )
            )
        return devices

    async def get_overview(self, serial_number: str) -> DeviceOverview:
        data = await self._post("device/statistics/overview", {"sn": serial_number})
        return DeviceOverview(
            serial_number=serial_number,
            current_power_w=self._decimal(data.get("totalNow", 0), "totalNow"),
            today_energy_kwh=self._decimal(
                data.get("production", {}).get("today", 0)
                if isinstance(data.get("production"), dict)
                else 0,
                "production.today",
            ),
            last_update=self._datetime(data.get("lastUpdate")),
            status=data.get("alertTitle") if isinstance(data.get("alertTitle"), str) else None,
        )

    async def get_daily_energy(
        self,
        serial_number: str,
        start: date,
        end: date,
        *,
        expect_complete: bool = False,
    ) -> list[DailyEnergy]:
        if end < start:
            raise ValueError("A data final não pode ser anterior à inicial")

        query_start, query_end = start, end
        # A API comunitariamente observada falha em intervalos de um único dia.
        if start == end:
            query_start = start - timedelta(days=1)

        data = await self._post(
            "device/statistics/echarts",
            {
                "sn": serial_number,
                "types": 3,
                "rangeDate": f"{query_start.isoformat()}~{query_end.isoformat()}",
            },
        )
        dates = data.get("xAxisData")
        series = data.get("series")
        if not isinstance(dates, list) or not isinstance(series, list) or not series:
            raise ProviderSchemaError("Série diária ausente")
        values = series[0].get("data") if isinstance(series[0], dict) else None
        if not isinstance(values, list) or len(values) != len(dates):
            raise ProviderSchemaError("Datas e valores possuem tamanhos incompatíveis")

        result: list[DailyEnergy] = []
        covered: set[date] = set()
        for raw_date, raw_value in zip(dates, values, strict=True):
            if not isinstance(raw_date, str):
                continue
            parsed = self._datetime(raw_date)
            if parsed is None or not start <= parsed.date() <= end:
                continue
            covered.add(parsed.date())
            if raw_value is None:
                continue
            result.append(
                DailyEnergy(
                    production_date=parsed.date(),
                    energy_kwh=self._decimal(raw_value, "series.data"),
                )
            )

        if expect_complete:
            expected: set[date] = set()
            cursor = start
            while cursor <= end:
                expected.add(cursor)
                cursor += timedelta(days=1)
            missing = expected - covered
            if missing:
                raise ProviderIncompleteDataError(
                    "NEPViewer não cobriu todos os dias solicitados"
                )
        return result
