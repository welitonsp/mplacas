"""Cliente da API clássica da Growatt (a do app ShinePhone), ADR-092.

Entra com usuário e senha do dono e lê a produção diária **por usina**: cada
usina Growatt da conta vira um "aparelho" ``GW-PLANT-<id>`` no MPlacas. A API
não é documentada; os endpoints seguem a biblioteca ``growattServer`` (MIT),
usada só como referência. Nenhuma mensagem de erro repete usuário, senha ou o
texto devolvido pela Growatt.
"""

from __future__ import annotations

import calendar
import hashlib
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from mplacas.providers.base import (
    DailyEnergy,
    DeviceOverview,
    ProviderAuthError,
    ProviderIncompleteDataError,
    ProviderRateLimitedError,
    ProviderSchemaError,
    PlantProfile,
    ProviderUnavailableError,
    SolarDevice,
    SolarProvider,
)
from mplacas.providers.profile import parse_coordinate, parse_kwp, parse_text

DEFAULT_BASE_URL = "https://openapi.growatt.com"
PLANT_PREFIX = "GW-PLANT-"
# A Growatt passou a recusar requisições sem User-Agent; usamos um fixo e
# identificável, no formato do app Android.
USER_AGENT = "Dalvik/2.1.0 (Linux; U; Android 12; MPlacas)"
_RATE_LIMIT_CODES = {"507"}
_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")


def hash_password(password: str) -> str:
    """Senha no formato do app: MD5 em hexadecimal, com ``0`` → ``c`` nas posições pares."""
    digest = list(hashlib.md5(password.encode("utf-8"), usedforsecurity=False).hexdigest())
    for index in range(0, len(digest), 2):
        if digest[index] == "0":
            digest[index] = "c"
    return "".join(digest)


def plant_serial(plant_id: str) -> str:
    return f"{PLANT_PREFIX}{plant_id}"


def _plant_id(serial_number: str) -> str:
    if not serial_number.startswith(PLANT_PREFIX) or not serial_number[len(PLANT_PREFIX) :]:
        raise ProviderSchemaError("identificador de usina Growatt inválido")
    return serial_number[len(PLANT_PREFIX) :]


def _kwh(value: Any, field: str) -> Decimal:
    """``"4.1"``, ``4.1`` ou ``"4.1 kWh"`` → ``Decimal('4.1')``. Nunca inventa zero."""
    if isinstance(value, bool) or value is None:
        raise ProviderSchemaError(f"Campo numérico inválido: {field}")
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    elif isinstance(value, str):
        match = _NUMBER.search(value)
        if match is None:
            raise ProviderSchemaError(f"Campo numérico inválido: {field}")
        text = match.group(0).replace(",", ".")
    else:
        raise ProviderSchemaError(f"Campo numérico inválido: {field}")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ProviderSchemaError(f"Campo numérico inválido: {field}") from exc
    if number < 0:
        raise ProviderSchemaError(f"Energia negativa: {field}")
    return number


def _month_starts(start: date, end: date) -> list[date]:
    months: list[date] = []
    cursor = start.replace(day=1)
    while cursor <= end:
        months.append(cursor)
        last = calendar.monthrange(cursor.year, cursor.month)[1]
        cursor = cursor.replace(day=last) + timedelta(days=1)
    return months


def _day_of_month(key: str, month: date) -> date | None:
    """Aceita ``"5"``/``"05"`` (dia do mês) e ``"2026-10-05"``; ignora o resto."""
    key = key.strip()
    if key.isdigit():
        day = int(key)
        if 1 <= day <= calendar.monthrange(month.year, month.month)[1]:
            return month.replace(day=day)
        return None
    try:
        parsed = date.fromisoformat(key)
    except ValueError:
        return None
    if (parsed.year, parsed.month) != (month.year, month.month):
        return None
    return parsed


class GrowattClient(SolarProvider):
    def __init__(
        self,
        *,
        account: str,
        password: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._account = account
        self._password = password
        self._user_id: str | None = None
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": USER_AGENT},
            transport=transport,
            follow_redirects=False,
        )

    def __repr__(self) -> str:
        return "GrowattClient(account=<hidden>, password=<hidden>)"

    async def __aenter__(self) -> GrowattClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
        login: bool = False,
        envelope: str = "back",
    ) -> dict[str, Any]:
        try:
            response = await self._client.request(method, path, params=params, data=data)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderUnavailableError("Growatt indisponível ou com timeout") from exc
        if response.status_code in {401, 403}:
            raise ProviderAuthError("Growatt recusou o acesso")
        if 300 <= response.status_code < 400 and login:
            # Redirecionar o próprio login é mudança de rota/bloqueio da
            # Growatt, não senha errada: não pode virar "login recusado".
            raise ProviderUnavailableError("Growatt redirecionou o login")
        if 300 <= response.status_code < 400:
            # Sessão expirada: a API clássica redireciona para a tela de login.
            raise ProviderAuthError("Sessão Growatt expirada")
        if response.status_code == 507:
            raise ProviderRateLimitedError("Growatt bloqueou por excesso de tentativas")
        if response.status_code >= 500:
            raise ProviderUnavailableError("Growatt apresentou falha temporária")
        if response.status_code >= 400:
            raise ProviderSchemaError(
                f"Resposta HTTP inesperada da Growatt: {response.status_code}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderSchemaError("Growatt retornou conteúdo não JSON") from exc
        if not envelope:
            if not isinstance(body, dict):
                raise ProviderSchemaError("Growatt retornou envelope incompatível")
            return body
        back = body.get(envelope) if isinstance(body, dict) else None
        if not isinstance(back, dict):
            raise ProviderSchemaError("Growatt retornou envelope incompatível")
        return back

    async def _login(self) -> str:
        if self._user_id is not None:
            return self._user_id
        back = await self._request(
            "POST",
            "/newTwoLoginAPI.do",
            data={"userName": self._account, "password": hash_password(self._password)},
            login=True,
        )
        if back.get("success") is not True:
            code = str(back.get("msg") or back.get("error") or back.get("errCode") or "")
            if code in _RATE_LIMIT_CODES:
                raise ProviderRateLimitedError("Growatt bloqueou por excesso de tentativas")
            raise ProviderAuthError("Growatt recusou o usuário ou a senha")
        user = back.get("user")
        user_id = user.get("id") if isinstance(user, dict) else back.get("userId")
        if user_id in (None, ""):
            raise ProviderSchemaError("Growatt não informou o usuário após o login")
        self._user_id = str(user_id)
        return self._user_id

    async def _plants(self) -> list[dict[str, Any]]:
        user_id = await self._login()
        back = await self._request("GET", "/PlantListAPI.do", params={"userId": user_id})
        rows = back.get("data")
        if not isinstance(rows, list):
            raise ProviderSchemaError("Lista de usinas Growatt ausente")
        plants: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict) or row.get("plantId") in (None, ""):
                raise ProviderSchemaError("Usina Growatt sem identificador")
            plants.append(row)
        return plants

    async def list_devices(self) -> list[SolarDevice]:
        return [
            SolarDevice(
                serial_number=plant_serial(str(row["plantId"])),
                model_name="Usina Growatt",
                city=None,
                last_update=None,
            )
            for row in await self._plants()
        ]

    async def plant_profile(self) -> PlantProfile | None:
        """Dados cadastrados na Growatt da maior usina da conta (ADR-093 § 7).

        ``newPlantAPI.do?op=getPlant`` devolve o cadastro sem o envelope
        ``back``. Campo ausente ou estranho vira ``None``; a usina é a de maior
        potência quando a conta tem mais de uma.
        """
        plants = await self._plants()
        if not plants:
            return None
        chosen = max(plants, key=lambda row: parse_kwp(row.get("nominalPower"), unit="W") or 0)
        body = await self._request(
            "GET",
            "/newPlantAPI.do",
            params={"op": "getPlant", "plantId": str(chosen["plantId"])},
            envelope="",
        )
        for wrapper in ("obj", "back", "data"):
            if isinstance(body.get(wrapper), dict):
                body = body[wrapper]
                break
        return PlantProfile(
            name=parse_text(body.get("plantName")) or parse_text(chosen.get("plantName")),
            installed_power_kwp=parse_kwp(body.get("nominalPower"), unit="W")
            or parse_kwp(chosen.get("nominalPower"), unit="W"),
            latitude=parse_coordinate(body.get("plant_lat"), limit=90),
            longitude=parse_coordinate(body.get("plant_lng"), limit=180),
            city=parse_text(body.get("city")),
            # ``createDateText`` é a data do cadastro na nuvem Growatt, não a da
            # ligação da usina: não alimenta ``commissioned_on`` (regime da Lei
            # 14.300 e retorno do investimento dependem da data real).
            commissioned_on=None,
            timezone=None,
        )

    async def get_overview(self, serial_number: str) -> DeviceOverview:
        plant_id = _plant_id(serial_number)
        for row in await self._plants():
            if str(row["plantId"]) == plant_id:
                return DeviceOverview(
                    serial_number=serial_number,
                    current_power_w=_kwh(row.get("currentPower", "0"), "currentPower"),
                    today_energy_kwh=_kwh(row.get("todayEnergy", "0"), "todayEnergy"),
                    last_update=None,
                    status=None,
                )
        raise ProviderSchemaError("Usina Growatt não encontrada na conta")

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
        await self._login()
        result: list[DailyEnergy] = []
        covered: set[date] = set()
        for month in _month_starts(start, end):
            back = await self._request(
                "GET",
                "/PlantDetailAPI.do",
                params={"plantId": plant_id, "type": "2", "date": month.strftime("%Y-%m")},
            )
            data = back.get("data")
            if not isinstance(data, dict):
                raise ProviderSchemaError("Série mensal Growatt ausente")
            for key, raw_value in data.items():
                if not isinstance(key, str):
                    continue
                day = _day_of_month(key, month)
                if day is None or not start <= day <= end:
                    continue
                if raw_value in (None, ""):
                    continue
                covered.add(day)
                result.append(DailyEnergy(production_date=day, energy_kwh=_kwh(raw_value, "data")))
        if expect_complete:
            expected = {start + timedelta(days=offset) for offset in range((end - start).days + 1)}
            if expected - covered:
                raise ProviderIncompleteDataError("Growatt não cobriu todos os dias solicitados")
        result.sort(key=lambda item: item.production_date)
        return result
