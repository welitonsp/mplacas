"""Cliente da API clássica da Growatt (ADR-092), com respostas simuladas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs

import httpx
import pytest

from mplacas.providers.base import (
    ProviderAuthError,
    ProviderIncompleteDataError,
    ProviderRateLimitedError,
    ProviderSchemaError,
    ProviderUnavailableError,
)
from mplacas.providers.growatt.client import GrowattClient, hash_password, plant_serial
from mplacas.providers.resilient import ResilientSolarProvider, RetryPolicy

LOGIN = "rogerio"
PASSWORD = "senha-do-app"


def _ok(back: dict) -> httpx.Response:
    return httpx.Response(200, json={"back": back})


class FakeGrowatt:
    def __init__(self, *, months: dict[str, dict] | None = None, login: dict | None = None):
        self.months = months or {}
        self.login_back = login or {"success": True, "user": {"id": 42, "rightlevel": 1}}
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        path = request.url.path
        if path == "/newTwoLoginAPI.do":
            return _ok(self.login_back)
        if path == "/PlantListAPI.do":
            assert request.url.params["userId"] == "42"
            return _ok(
                {
                    "data": [
                        {
                            "plantId": "777",
                            "plantName": "Casa",
                            "todayEnergy": "4.1 kWh",
                            "currentPower": "963.2 W",
                        },
                    ],
                    "success": True,
                }
            )
        if path == "/PlantDetailAPI.do":
            assert request.url.params["type"] == "2"
            month = request.url.params["date"]
            return _ok({"plantData": {"plantId": "777"}, "data": self.months.get(month, {})})
        return httpx.Response(404)

    def logins(self) -> int:
        return sum(1 for call in self.calls if call.url.path == "/newTwoLoginAPI.do")


def _client(fake) -> GrowattClient:
    return GrowattClient(account=LOGIN, password=PASSWORD, transport=httpx.MockTransport(fake))


def test_password_uses_the_app_format() -> None:
    # Vetores fixos: MD5 de "abc" é 900150983cd24fb0d6963f7d28e17f72; o app troca
    # o "0" da posição par 2 por "c". O outro vetor não muda nas posições pares.
    assert hash_password("abc") == "90c150983cd24fb0d6963f7d28e17f72"
    assert hash_password(PASSWORD) == "8f26828bc65243c69050663dbdee99e0"


async def test_login_sends_user_agent_and_hashed_password_never_the_plain_one() -> None:
    fake = FakeGrowatt()
    async with _client(fake) as client:
        devices = await client.list_devices()

    login_call = fake.calls[0]
    form = parse_qs(login_call.content.decode())
    assert form["userName"] == [LOGIN]
    assert form["password"] == [hash_password(PASSWORD)]
    assert PASSWORD.encode() not in login_call.content
    assert "MPlacas" in login_call.headers["User-Agent"]
    assert [d.serial_number for d in devices] == [plant_serial("777")]
    assert PASSWORD not in repr(client)


async def test_daily_energy_reads_the_month_and_logs_in_once() -> None:
    fake = FakeGrowatt(months={"2026-10": {"1": "10.5", "2": "11", "03": "9.25 kWh", "31": "0"}})
    async with _client(fake) as client:
        rows = await client.get_daily_energy(
            plant_serial("777"), date(2026, 10, 1), date(2026, 10, 3), expect_complete=True
        )
        await client.list_devices()

    assert [(r.production_date, r.energy_kwh) for r in rows] == [
        (date(2026, 10, 1), Decimal("10.5")),
        (date(2026, 10, 2), Decimal("11")),
        (date(2026, 10, 3), Decimal("9.25")),
    ]
    assert fake.logins() == 1


async def test_month_turn_reads_both_months_and_accepts_iso_keys() -> None:
    fake = FakeGrowatt(months={"2026-09": {"2026-09-30": "8.0"}, "2026-10": {"2026-10-01": "7.5"}})
    async with _client(fake) as client:
        rows = await client.get_daily_energy(
            plant_serial("777"), date(2026, 9, 30), date(2026, 10, 1), expect_complete=True
        )

    assert [r.production_date for r in rows] == [date(2026, 9, 30), date(2026, 10, 1)]


async def test_missing_day_is_incomplete_never_zero() -> None:
    fake = FakeGrowatt(months={"2026-10": {"1": "10.5", "3": ""}})
    async with _client(fake) as client:
        rows = await client.get_daily_energy(
            plant_serial("777"), date(2026, 10, 1), date(2026, 10, 3)
        )
        assert [r.production_date for r in rows] == [date(2026, 10, 1)]
        with pytest.raises(ProviderIncompleteDataError):
            await client.get_daily_energy(
                plant_serial("777"), date(2026, 10, 1), date(2026, 10, 3), expect_complete=True
            )


@pytest.mark.parametrize("bad", ["abc", -1, True, {"v": 1}])
async def test_invalid_values_are_schema_errors(bad) -> None:
    fake = FakeGrowatt(months={"2026-10": {"1": bad}})
    async with _client(fake) as client:
        with pytest.raises(ProviderSchemaError):
            await client.get_daily_energy(plant_serial("777"), date(2026, 10, 1), date(2026, 10, 1))


async def test_refused_login_is_an_auth_error_without_echoing_anything() -> None:
    fake = FakeGrowatt(login={"success": False, "msg": "502", "error": "senha errada para rogerio"})
    async with _client(fake) as client:
        with pytest.raises(ProviderAuthError) as raised:
            await client.list_devices()

    assert LOGIN not in str(raised.value) and "senha errada" not in str(raised.value)


@pytest.mark.parametrize(
    "response",
    [
        _ok({"success": False, "msg": "507"}),
        httpx.Response(507),
    ],
)
async def test_rate_limit_is_never_retried(response) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return response

    client = GrowattClient(account=LOGIN, password=PASSWORD, transport=httpx.MockTransport(handler))
    provider = ResilientSolarProvider(
        client, policy=RetryPolicy(max_attempts=4, base_delay_seconds=0)
    )
    try:
        with pytest.raises(ProviderRateLimitedError):
            await provider.list_devices()
    finally:
        await client.aclose()

    assert len(calls) == 1


async def test_server_errors_and_timeouts_are_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    async with GrowattClient(
        account=LOGIN, password=PASSWORD, transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(ProviderUnavailableError):
            await client.list_devices()

    async with GrowattClient(
        account=LOGIN,
        password=PASSWORD,
        transport=httpx.MockTransport(lambda request: httpx.Response(502)),
    ) as client:
        with pytest.raises(ProviderUnavailableError):
            await client.list_devices()


async def test_redirect_to_login_is_an_expired_session() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/newTwoLoginAPI.do":
            return _ok({"success": True, "user": {"id": 42}})
        return httpx.Response(302, headers={"Location": "/login"})

    async with GrowattClient(
        account=LOGIN, password=PASSWORD, transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(ProviderAuthError):
            await client.list_devices()


async def test_non_json_and_bad_envelope_are_schema_errors() -> None:
    for response in (httpx.Response(200, content=b"<html>"), httpx.Response(200, json={"x": 1})):
        async with GrowattClient(
            account=LOGIN,
            password=PASSWORD,
            transport=httpx.MockTransport(lambda r, resp=response: resp),
        ) as client:
            with pytest.raises(ProviderSchemaError):
                await client.list_devices()


async def test_overview_reads_today_energy_from_the_plant_list() -> None:
    async with _client(FakeGrowatt()) as client:
        overview = await client.get_overview(plant_serial("777"))
        with pytest.raises(ProviderSchemaError):
            await client.get_overview("SN-QUALQUER")

    assert overview.today_energy_kwh == Decimal("4.1")
    assert overview.current_power_w == Decimal("963.2")


async def test_redirect_on_login_is_unavailable_not_a_wrong_password() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "/novo-login"})

    async with GrowattClient(
        account=LOGIN, password=PASSWORD, transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(ProviderUnavailableError):
            await client.list_devices()
