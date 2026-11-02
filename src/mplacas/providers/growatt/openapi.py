"""Cliente da OpenAPI V1 da Growatt (token do app ShinePhone), ADR-094.

É a interface que a Growatt documenta para programas de terceiros: sem login,
só o token no cabeçalho ``token``. O login por usuário e senha (API do app,
``client.py``) passou a ser recusado com HTTP 403 para servidores como o nosso
(31/10/2026); o token é o caminho recomendado.

Cada usina Growatt da conta vira um "aparelho" ``GW-PLANT-<id>``, como no
cliente clássico. Nenhuma mensagem de erro repete o token ou o texto devolvido
pela Growatt.

Envelope: ``{"error_code": 0, "error_msg": "", "data": {...}}``. Endpoints:
``plant/list``, ``plant/details``, ``plant/data`` e ``plant/energy`` (por dia,
no máximo 7 dias por consulta).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import httpx

from mplacas.providers.base import (
    DailyEnergy,
    DeviceOverview,
    PlantProfile,
    ProviderAuthError,
    ProviderError,
    ProviderIncompleteDataError,
    ProviderRateLimitedError,
    ProviderSchemaError,
    ProviderUnavailableError,
    SolarDevice,
    SolarProvider,
)
from mplacas.providers.growatt.client import _kwh, _plant_id, plant_serial
from mplacas.providers.profile import parse_coordinate, parse_kwp, parse_text

logger = logging.getLogger(__name__)

DEFAULT_OPENAPI_URL = "https://openapi.growatt.com/v1/"
# A OpenAPI aceita até 7 dias por consulta diária.
MAX_DAYS_PER_QUERY = 7
_PAGE_SIZE = "100"
_MAX_PAGES = 20
# 10011: token inválido ou sem permissão; 10012: consultas frequentes demais.
_AUTH_CODES = {10011}
_RATE_LIMIT_CODES = {10012}


def _code(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class GrowattOpenApiClient(SolarProvider):
    def __init__(
        self,
        *,
        token: str,
        base_url: str = DEFAULT_OPENAPI_URL,
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            timeout=httpx.Timeout(timeout_seconds),
            headers={"token": token, "Accept": "application/json"},
            transport=transport,
            follow_redirects=False,
        )
        self._plants_cache: list[dict[str, Any]] | None = None

    def __repr__(self) -> str:
        return "GrowattOpenApiClient(token=<hidden>)"

    async def __aenter__(self) -> GrowattOpenApiClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, str]) -> Any:
        try:
            response = await self._client.get(path, params=params)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderUnavailableError("Growatt indisponível ou com timeout") from exc
        if response.status_code in {401, 403}:
            raise ProviderAuthError("Growatt recusou o token")
        if response.status_code == 429:
            raise ProviderRateLimitedError("Growatt pediu para esperar")
        if response.status_code >= 500:
            raise ProviderUnavailableError("Growatt apresentou falha temporária")
        if response.status_code >= 300:
            raise ProviderSchemaError(
                f"Resposta HTTP inesperada da Growatt: {response.status_code}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderSchemaError("Growatt retornou conteúdo não JSON") from exc
        if not isinstance(body, dict):
            raise ProviderSchemaError("Growatt retornou envelope incompatível")
        code = _code(body.get("error_code"))
        if code != 0:
            # Qual endpoint recusou e o motivo da Growatt (texto curto dela,
            # sem token nem dado da usina): o mesmo token lista as usinas mas
            # recebe 10011 em outros endpoints (02/11/2026).
            logger.info(
                "growatt_openapi_error",
                extra={
                    "endpoint": path,
                    "error_code": code,
                    "error_msg": str(body.get("error_msg") or "")[:120],
                },
            )
        if code in _AUTH_CODES:
            raise ProviderAuthError("Growatt recusou o token")
        if code in _RATE_LIMIT_CODES:
            raise ProviderRateLimitedError("Growatt pediu para esperar")
        if code != 0:
            raise ProviderSchemaError(f"Growatt respondeu com erro {code}")
        return body.get("data")

    async def _plants(self) -> list[dict[str, Any]]:
        # A Growatt só aceita ``plant/list`` de tempos em tempos (10012,
        # "error_frequently_access", visto em 02/11/2026): reaproveita a lista
        # já lida por este cliente.
        if self._plants_cache is not None:
            return self._plants_cache
        plants: list[dict[str, Any]] = []
        for page in range(1, _MAX_PAGES + 1):
            data = await self._get(
                "plant/list",
                {"page": str(page), "perpage": _PAGE_SIZE, "search_type": "", "search_keyword": ""},
            )
            rows = data.get("plants") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                raise ProviderSchemaError("Lista de usinas Growatt ausente")
            for row in rows:
                if not isinstance(row, dict) or row.get("plant_id") in (None, ""):
                    raise ProviderSchemaError("Usina Growatt sem identificador")
                plants.append(row)
            total = _code(data.get("count"))
            if not rows or total is None or len(plants) >= total:
                self._plants_cache = plants
                return plants
        # Nunca truncar em silêncio: faltariam usinas (e produção) na conta.
        raise ProviderSchemaError("Conta Growatt com usinas demais para listar")

    async def list_devices(self) -> list[SolarDevice]:
        return [
            SolarDevice(
                serial_number=plant_serial(str(row["plant_id"])),
                model_name="Usina Growatt",
                city=parse_text(row.get("city")),
                last_update=None,
            )
            for row in await self._plants()
        ]

    async def get_overview(self, serial_number: str) -> DeviceOverview:
        data = await self._get("plant/data", {"plant_id": _plant_id(serial_number)})
        if not isinstance(data, dict):
            raise ProviderSchemaError("Resumo da usina Growatt ausente")
        # A OpenAPI informa a potência atual em kW. Campo ausente é erro, nunca zero.
        current_kw = _kwh(data.get("current_power"), "current_power")
        return DeviceOverview(
            serial_number=serial_number,
            current_power_w=current_kw * 1000,
            today_energy_kwh=_kwh(data.get("today_energy"), "today_energy"),
            last_update=None,
            status=None,
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
        plant_id = _plant_id(serial_number)
        result: dict[date, Decimal] = {}
        cursor = start
        while cursor <= end:
            window_end = min(cursor + timedelta(days=MAX_DAYS_PER_QUERY - 1), end)
            data = await self._get(
                "plant/energy",
                {
                    "plant_id": plant_id,
                    "start_date": cursor.isoformat(),
                    "end_date": window_end.isoformat(),
                    "time_unit": "day",
                    "page": "1",
                    "perpage": _PAGE_SIZE,
                },
            )
            rows = data.get("energys") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                raise ProviderSchemaError("Série diária Growatt ausente")
            for row in rows:
                if not isinstance(row, dict):
                    raise ProviderSchemaError("Dia Growatt inválido")
                try:
                    day = date.fromisoformat(str(row.get("date", ""))[:10])
                except ValueError as exc:
                    raise ProviderSchemaError("Data Growatt inválida") from exc
                if not cursor <= day <= window_end or row.get("energy") in (None, ""):
                    continue
                result[day] = _kwh(row["energy"], "energy")
            cursor = window_end + timedelta(days=1)
        if expect_complete:
            expected = {start + timedelta(days=offset) for offset in range((end - start).days + 1)}
            if expected - set(result):
                raise ProviderIncompleteDataError("Growatt não cobriu todos os dias solicitados")
        return [DailyEnergy(production_date=day, energy_kwh=result[day]) for day in sorted(result)]

    async def probe(self) -> dict[str, str]:
        """Quais endpoints de leitura este token alcança (ADR-094).

        Só leitura, só o resultado de cada um (``ok`` ou o tipo do erro),
        nunca o conteúdo. Usado quando a produção é recusada para descobrir
        por onde o token consegue ler.
        """
        result: dict[str, str] = {}
        try:
            plants = await self._plants()
        except ProviderError as exc:
            return {"plant/list": type(exc).__name__}
        result["plant/list"] = f"ok:{len(plants)}"
        if not plants:
            return result
        plant_id = str(plants[0]["plant_id"])
        today = date.today()
        checks: list[tuple[str, dict[str, str]]] = [
            ("plant/data", {"plant_id": plant_id}),
            ("plant/details", {"plant_id": plant_id}),
            ("device/list", {"plant_id": plant_id, "page": "1", "perpage": _PAGE_SIZE}),
            (
                "plant/energy",
                {
                    "plant_id": plant_id,
                    "start_date": (today - timedelta(days=6)).isoformat(),
                    "end_date": today.isoformat(),
                    "time_unit": "day",
                    "page": "1",
                    "perpage": _PAGE_SIZE,
                },
            ),
            (
                "plant/energy:month",
                {
                    "plant_id": plant_id,
                    "start_date": today.replace(day=1).isoformat()[:7],
                    "end_date": today.isoformat()[:7],
                    "time_unit": "month",
                    "page": "1",
                    "perpage": _PAGE_SIZE,
                },
            ),
            ("plant/power", {"plant_id": plant_id, "date": today.isoformat()}),
        ]
        for name, params in checks:
            path = name.split(":")[0]
            try:
                data = await self._get(path, params)
            except ProviderError as exc:
                result[name] = type(exc).__name__
            else:
                keys = sorted(data)[:12] if isinstance(data, dict) else []
                result[name] = "ok:" + ",".join(str(key) for key in keys)
        return result

    async def plant_profile(self) -> PlantProfile | None:
        """Cadastro da maior usina da conta, melhor esforço (ADR-094).

        A base é a própria ``plant/list``, que já traz nome, potência (kW),
        cidade e coordenadas. ``plant/details`` só completa o que faltar: há
        tokens que listam as usinas mas não têm permissão para os detalhes
        (``10011``, visto em 02/11/2026), e isso não pode zerar o cadastro.
        """
        plants = await self._plants()
        if not plants:
            return None
        chosen = max(plants, key=lambda row: parse_kwp(row.get("peak_power"), unit="kW") or 0)
        # Só os nomes dos campos (nunca os valores) — para ajustar a leitura
        # ao formato real da Growatt sem expor dado do cliente.
        logger.info(
            "growatt_openapi_plant_fields",
            extra={
                "fields": sorted(str(key) for key in chosen)[:40],
                # Formato de cada valor que importa, nunca o valor (ADR-094).
                "shapes": {key: _shape(chosen.get(key)) for key in _PROFILE_KEYS},
            },
        )
        details: dict[str, Any] = {}
        if not _complete(chosen):
            try:
                body = await self._get("plant/details", {"plant_id": str(chosen["plant_id"])})
            except ProviderError as exc:
                logger.info(
                    "growatt_openapi_plant_details_unavailable",
                    extra={"error_type": type(exc).__name__},
                )
            else:
                if isinstance(body, dict):
                    details = body["plant"] if isinstance(body.get("plant"), dict) else body

        def pick(*keys: str) -> Any:
            for source in (chosen, details):
                for key in keys:
                    value = source.get(key)
                    if value not in (None, ""):
                        return value
            return None

        return PlantProfile(
            name=parse_text(pick("name", "plant_name", "plantName")),
            # A OpenAPI informa ``peak_power`` em kW.
            installed_power_kwp=parse_kwp(pick("peak_power", "peakPower"), unit="kW"),
            latitude=parse_coordinate(pick("latitude", "lat"), limit=90),
            longitude=parse_coordinate(pick("longitude", "lng", "lon"), limit=180),
            city=parse_text(pick("city")),
            commissioned_on=None,
            timezone=None,
        )


_PROFILE_KEYS = (
    "name",
    "peak_power",
    "city",
    "latitude",
    "longitude",
    "latitude_d",
    "latitude_f",
    "longitude_d",
    "longitude_f",
)


def _shape(value: Any) -> str:
    """Descrição do formato sem o conteúdo: ``vazio``, ``zero``, ``numero``,
    ``texto-numero``, ``texto-grau``, ``texto`` ou o tipo."""
    if value is None or value == "":
        return "vazio"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "zero" if value == 0 else "numero"
    if isinstance(value, str):
        text = value.strip()
        try:
            return "zero" if float(text.replace(",", ".")) == 0 else "texto-numero"
        except ValueError:
            pass
        if any(mark in text for mark in ("°", "'", '"')):
            return "texto-grau"
        return "texto"
    return type(value).__name__


def _complete(row: dict[str, Any]) -> bool:
    """A linha da lista já tem o essencial (potência e localização)?"""
    has_power = parse_kwp(row.get("peak_power"), unit="kW") is not None
    has_place = parse_coordinate(row.get("latitude"), limit=90) is not None or bool(
        parse_text(row.get("city"))
    )
    return has_power and has_place
