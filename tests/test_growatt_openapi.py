"""OpenAPI V1 da Growatt por token (ADR-094), com respostas simuladas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest

from mplacas.providers.base import (
    PlantProfile,
    ProviderAuthError,
    ProviderBlockedError,
    ProviderIncompleteDataError,
    ProviderRateLimitedError,
    ProviderSchemaError,
    ProviderUnavailableError,
)
from mplacas.providers.growatt.client import GrowattClient
from mplacas.providers.growatt.openapi import GrowattOpenApiClient

TOKEN = "token-de-teste"


def _ok(data) -> httpx.Response:
    return httpx.Response(200, json={"error_code": 0, "error_msg": "", "data": data})


class FakeOpenApi:
    def __init__(self, energys: dict[str, str] | None = None) -> None:
        self.energys = energys or {}
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        assert request.headers["token"] == TOKEN
        path = request.url.path
        if path == "/v1/plant/list":
            return _ok(
                {
                    "count": 2,
                    "plants": [
                        {"plant_id": 11, "name": "Pequena", "peak_power": 2.0, "city": "Goiânia"},
                        {"plant_id": 22, "name": "Casa", "peak_power": 5.4, "city": "Caldas Novas"},
                    ],
                }
            )
        if path == "/v1/plant/details":
            assert request.url.params["plant_id"] == "22"
            return _ok(
                {
                    "name": "Usina do Rogério",
                    "peak_power": 5.4,
                    "latitude": "-17.7441",
                    "longitude": "-48.6252",
                    "city": "Caldas Novas",
                }
            )
        if path == "/v1/plant/energy":
            params = request.url.params
            assert params["time_unit"] == "day"
            start = date.fromisoformat(params["start_date"])
            end = date.fromisoformat(params["end_date"])
            assert (end - start).days < 7
            rows = [
                {"date": day, "energy": value}
                for day, value in self.energys.items()
                if start <= date.fromisoformat(day) <= end
            ]
            return _ok({"count": len(rows), "time_unit": "day", "energys": rows})
        if path == "/v1/plant/data":
            return _ok({"current_power": 1.25, "today_energy": "4.1"})
        return httpx.Response(404)


def _envelope(code: int, message: str) -> httpx.Response:
    return httpx.Response(200, json={"error_code": code, "error_msg": message})


def _client(handler) -> GrowattOpenApiClient:
    return GrowattOpenApiClient(token=TOKEN, transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_lists_plants_as_devices_and_never_shows_the_token() -> None:
    client = _client(FakeOpenApi())
    devices = await client.list_devices()
    await client.aclose()
    assert [d.serial_number for d in devices] == ["GW-PLANT-11", "GW-PLANT-22"]
    assert TOKEN not in repr(client)


@pytest.mark.asyncio
async def test_daily_energy_splits_in_windows_of_seven_days() -> None:
    fake = FakeOpenApi({f"2026-10-{day:02d}": f"{day}.5" for day in range(1, 16)})
    client = _client(fake)
    rows = await client.get_daily_energy(
        "GW-PLANT-22", date(2026, 10, 1), date(2026, 10, 15), expect_complete=True
    )
    await client.aclose()
    assert len(rows) == 15
    assert rows[0].energy_kwh == Decimal("1.5")
    assert sum(1 for call in fake.calls if call.url.path == "/v1/plant/energy") == 3


@pytest.mark.asyncio
async def test_missing_day_is_incomplete_never_zero() -> None:
    client = _client(FakeOpenApi({"2026-10-01": "3.0"}))
    with pytest.raises(ProviderIncompleteDataError):
        await client.get_daily_energy(
            "GW-PLANT-22", date(2026, 10, 1), date(2026, 10, 2), expect_complete=True
        )
    await client.aclose()


@pytest.mark.asyncio
async def test_profile_uses_the_list_row_of_biggest_plant_in_kw() -> None:
    fake = FakeOpenApi()
    client = _client(fake)
    profile = await client.plant_profile()
    await client.aclose()
    # a linha da lista já tem potência e cidade: os detalhes nem são pedidos
    assert profile == PlantProfile(
        name="Casa", installed_power_kwp=Decimal("5.400"), city="Caldas Novas"
    )
    assert all(call.url.path != "/v1/plant/details" for call in fake.calls)


@pytest.mark.asyncio
async def test_profile_completes_from_details_when_list_is_partial() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/plant/list":
            return _ok({"count": 1, "plants": [{"plant_id": 22, "name": "Casa"}]})
        return FakeOpenApi()(request)

    client = _client(handler)
    profile = await client.plant_profile()
    await client.aclose()
    assert profile == PlantProfile(
        name="Casa",
        installed_power_kwp=Decimal("5.400"),
        latitude=Decimal("-17.744100"),
        longitude=Decimal("-48.625200"),
        city="Caldas Novas",
    )


@pytest.mark.asyncio
async def test_overview_converts_kw_to_watts() -> None:
    client = _client(FakeOpenApi())
    overview = await client.get_overview("GW-PLANT-22")
    await client.aclose()
    assert overview.current_power_w == Decimal("1250.00")
    assert overview.today_energy_kwh == Decimal("4.1")


@pytest.mark.parametrize(
    "response,error",
    [
        (
            httpx.Response(200, json={"error_code": 10011, "error_msg": "permission denied"}),
            ProviderAuthError,
        ),
        (
            httpx.Response(200, json={"error_code": 10012, "error_msg": "frequently"}),
            ProviderRateLimitedError,
        ),
        (
            httpx.Response(200, json={"error_code": 10001, "error_msg": "system"}),
            ProviderSchemaError,
        ),
        (httpx.Response(403), ProviderAuthError),
        (httpx.Response(429), ProviderRateLimitedError),
        (httpx.Response(502), ProviderUnavailableError),
        (httpx.Response(200, text="<html>"), ProviderSchemaError),
    ],
)
@pytest.mark.asyncio
async def test_errors_are_classified_without_echoing(response, error) -> None:
    client = _client(lambda request, resp=response: resp)
    with pytest.raises(error) as caught:
        await client.list_devices()
    await client.aclose()
    assert TOKEN not in str(caught.value)
    assert "permission denied" not in str(caught.value)


@pytest.mark.asyncio
async def test_classic_login_403_is_blocked_not_wrong_password() -> None:
    client = GrowattClient(
        account="u", password="p", transport=httpx.MockTransport(lambda r: httpx.Response(403))
    )
    with pytest.raises(ProviderBlockedError):
        await client.list_devices()
    await client.aclose()


@pytest.mark.asyncio
async def test_plant_list_is_paginated_never_truncated() -> None:
    pages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params["page"]
        pages.append(page)
        rows = [{"plant_id": int(page) * 1000 + n} for n in range(100 if page == "1" else 5)]
        return _ok({"count": 105, "plants": rows})

    client = _client(handler)
    devices = await client.list_devices()
    await client.aclose()
    assert len(devices) == 105
    assert pages == ["1", "2"]


@pytest.mark.asyncio
async def test_overview_without_fields_is_an_error_never_zero() -> None:
    client = _client(lambda request: _ok({"today_energy": "4.1"}))
    with pytest.raises(ProviderSchemaError):
        await client.get_overview("GW-PLANT-22")
    await client.aclose()


def test_blocked_login_waits_an_hour_in_collection() -> None:
    from mplacas.collection.worker import SLOW_RETRY_SECONDS, slow_retry_seconds
    from mplacas.providers.resilient import _TRANSIENT_ERRORS

    blocked = ProviderBlockedError("bloqueado")
    assert slow_retry_seconds(blocked) == SLOW_RETRY_SECONDS
    assert not isinstance(blocked, _TRANSIENT_ERRORS)


def test_factory_builds_the_token_client_with_its_own_source() -> None:
    from mplacas.providers.factory import ENERGY_SOURCES, build_client

    client = build_client("GROWATT_TOKEN", account="token-x", password=TOKEN)
    assert isinstance(client, GrowattOpenApiClient)
    assert ENERGY_SOURCES["GROWATT_TOKEN"] == "GROWATT_OPENAPI_V1"


@pytest.mark.asyncio
async def test_profile_uses_the_list_when_details_are_not_permitted() -> None:
    """02/11/2026: token lista as usinas mas recebe 10011 nos detalhes."""
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        if request.url.path == "/v1/plant/list":
            return _ok(
                {
                    "count": 1,
                    "plants": [
                        {
                            "plant_id": 1383141,
                            "name": "Usina do Rogério",
                            "peak_power": 6.6,
                            "city": "Caldas Novas",
                            "latitude": "-17.74",
                            "longitude": "-48.62",
                        }
                    ],
                }
            )
        return _envelope(10011, "permission denied")

    client = _client(handler)
    profile = await client.plant_profile()
    await client.aclose()
    assert profile is not None
    assert profile.name == "Usina do Rogério"
    assert profile.installed_power_kwp == Decimal("6.600")
    assert profile.latitude == Decimal("-17.740000")
    assert "/v1/plant/details" not in asked  # a lista já bastava


@pytest.mark.asyncio
async def test_profile_survives_denied_details_when_list_is_partial() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/plant/list":
            return _ok({"count": 1, "plants": [{"plant_id": 9, "name": "Sítio"}]})
        return _envelope(10011, "permission denied")

    client = _client(handler)
    profile = await client.plant_profile()
    await client.aclose()
    assert profile == PlantProfile(name="Sítio")


def test_shape_never_reveals_the_value() -> None:
    from mplacas.providers.growatt.openapi import _shape

    assert _shape(None) == "vazio"
    assert _shape("") == "vazio"
    assert _shape(0) == "zero"
    assert _shape("0.0") == "zero"
    assert _shape(6.6) == "numero"
    assert _shape("-17.74") == "texto-numero"
    assert _shape("17°44'") == "texto-grau"
    assert _shape("Caldas Novas") == "texto"


@pytest.mark.asyncio
async def test_probe_maps_which_reads_the_token_reaches_without_content(caplog) -> None:
    """02/11/2026: lista ok, produção com 10011 — o mapa mostra por onde ler."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v1/plant/list":
            return _ok({"count": 1, "plants": [{"plant_id": 7, "name": "Segredo da usina"}]})
        if path == "/v1/plant/data":
            return _ok({"today_energy": "4.1", "total_energy": "900"})
        return _envelope(10011, "permission denied")

    client = _client(handler)
    with caplog.at_level("INFO"):
        result = await client.probe()
    await client.aclose()
    assert result["plant/list"] == "ok:1"
    assert result["plant/data"] == "ok:today_energy,total_energy"
    assert result["plant/energy"] == "ProviderAuthError"
    assert "Segredo" not in str(result) and "4.1" not in str(result)
    errors = [r for r in caplog.records if r.message == "growatt_openapi_error"]
    assert errors and errors[0].error_code == 10011
    assert TOKEN not in caplog.text
