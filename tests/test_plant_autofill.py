"""ADR-093 § 7 — a usina se preenche com o que a marca informa."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import httpx
import pytest

import mplacas.plants.autofill as autofill
from mplacas.db.models import Plant
from mplacas.providers.base import PlantProfile
from mplacas.providers.growatt.client import GrowattClient
from mplacas.providers.nepviewer.client import NepViewerClient
from mplacas.providers.profile import parse_coordinate, parse_date, parse_kwp, parse_text


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("5400", Decimal("5.400")),
        (5400, Decimal("5.400")),
        ("5.4", Decimal("5.400")),
        ("5,4 kW", Decimal("5.400")),
        (0, None),
        ("abc", None),
        (None, None),
        (True, None),
        ("99999999", None),
    ],
)
def test_parse_kwp_reads_watts_or_kw_and_drops_nonsense(raw, expected) -> None:
    assert parse_kwp(raw) == expected


def test_parse_coordinate_drops_zero_and_out_of_range() -> None:
    assert parse_coordinate("-17.741", limit=90) == Decimal("-17.741000")
    assert parse_coordinate("0", limit=90) is None
    assert parse_coordinate("95", limit=90) is None
    assert parse_coordinate("", limit=90) is None


def test_parse_date_and_text() -> None:
    assert parse_date("2021-03-15") == date(2021, 3, 15)
    assert parse_date("2021-03-15 10:00:00") == date(2021, 3, 15)
    assert parse_date("15/03/2021") == date(2021, 3, 15)
    assert parse_date("2999-01-01") is None
    assert parse_date("ontem") is None
    assert parse_text("  Usina   Casa ") == "Usina Casa"
    assert parse_text(42) is None


def _ok(back: dict) -> httpx.Response:
    return httpx.Response(200, json={"back": back})


@pytest.mark.asyncio
async def test_growatt_profile_reads_plant_settings_of_biggest_plant() -> None:
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/newTwoLoginAPI.do":
            return _ok({"success": True, "user": {"id": 42}})
        if request.url.path == "/PlantListAPI.do":
            return _ok(
                {
                    "data": [
                        {"plantId": "1", "plantName": "Pequena", "nominalPower": "2000"},
                        {"plantId": "2", "plantName": "Casa", "nominalPower": "5400"},
                    ]
                }
            )
        if request.url.path == "/newPlantAPI.do":
            assert request.url.params["op"] == "getPlant"
            asked.append(request.url.params["plantId"])
            # sem envelope "back", como na biblioteca de referência
            return httpx.Response(
                200,
                json={
                    "plantName": "Usina do Rogério",
                    "nominalPower": 5400,
                    "plant_lat": "-17.7441",
                    "plant_lng": "-48.6252",
                    "city": "Caldas Novas",
                    "createDateText": "2021-03-15",
                },
            )
        return httpx.Response(404)

    client = GrowattClient(account="u", password="p", transport=httpx.MockTransport(handler))
    profile = await client.plant_profile()
    await client.aclose()

    assert asked == ["2"]
    assert profile == PlantProfile(
        name="Usina do Rogério",
        installed_power_kwp=Decimal("5.400"),
        latitude=Decimal("-17.744100"),
        longitude=Decimal("-48.625200"),
        city="Caldas Novas",
        commissioned_on=None,  # data do cadastro na nuvem não é a da ligação
    )


def test_growatt_power_is_always_watts() -> None:
    assert parse_kwp("150000", unit="W") == Decimal("150.000")
    assert parse_kwp("150", unit="W") == Decimal("0.150")
    assert parse_kwp("150", unit="kW") == Decimal("150.000")


@pytest.mark.asyncio
async def test_growatt_profile_tolerates_empty_settings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/newTwoLoginAPI.do":
            return _ok({"success": True, "user": {"id": 42}})
        if request.url.path == "/PlantListAPI.do":
            return _ok({"data": [{"plantId": "9", "plantName": "Sítio", "nominalPower": "x"}]})
        return httpx.Response(200, json={"plant_lat": "0", "plant_lng": "0", "city": ""})

    client = GrowattClient(account="u", password="p", transport=httpx.MockTransport(handler))
    profile = await client.plant_profile()
    await client.aclose()

    assert profile == PlantProfile(name="Sítio")


@pytest.mark.asyncio
async def test_nepviewer_profile_is_the_city() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/sign-in"):
            return httpx.Response(200, json={"data": {"tokenInfo": {"token": "t"}}})
        return httpx.Response(
            200, json={"data": {"list": [{"sn": "A1", "city": " Goiânia "}, {"sn": "A2"}]}}
        )

    client = NepViewerClient(account="u", password="p", transport=httpx.MockTransport(handler))
    try:
        profile = await client.plant_profile()
    finally:
        await client.aclose()
    assert profile == PlantProfile(city="Goiânia")


def _plant(**fields) -> Plant:
    return Plant(id=uuid.uuid4(), organization_id=uuid.uuid4(), name="Minha usina", **fields)


def test_fill_uses_brand_data_and_estimates_the_rest() -> None:
    plant = _plant()
    profile = PlantProfile(
        name="Casa",
        installed_power_kwp=Decimal("5.4"),
        latitude=Decimal("-17.7"),
        longitude=Decimal("-48.6"),
        commissioned_on=date(2021, 3, 15),
    )

    filled = autofill.fill_plant_from_profile(plant, profile, set_name=True)

    assert plant.name == "Casa"
    assert plant.installed_power_kwp == Decimal("5.4")
    assert (plant.latitude, plant.longitude) == (Decimal("-17.7"), Decimal("-48.6"))
    assert plant.array_tilt_degrees == Decimal(18)
    assert plant.array_azimuth_degrees == Decimal(0)  # norte, no hemisfério sul
    assert plant.module_technology == "MONOCRYSTALLINE_SILICON"
    assert plant.commissioned_on is None  # nunca preenchida automaticamente
    assert filled == {
        "name": "BRAND",
        "dc_capacity_kwp": "BRAND",
        "location": "BRAND",
        "array_tilt_degrees": "ESTIMATE",
        "array_azimuth_degrees": "ESTIMATE",
        "module_technology": "ESTIMATE",
    }
    assert plant.auto_filled == filled


def test_fill_never_overwrites_what_the_owner_entered() -> None:
    plant = _plant(
        installed_power_kwp=Decimal("7.2"),
        latitude=Decimal("-16.0"),
        longitude=Decimal("-49.0"),
        array_tilt_degrees=Decimal(12),
        array_azimuth_degrees=Decimal(20),
        module_technology="POLYCRYSTALLINE_SILICON",
        commissioned_on=date(2020, 1, 1),
    )
    profile = PlantProfile(
        name="Outro nome",
        installed_power_kwp=Decimal("5.4"),
        latitude=Decimal("-17.7"),
        longitude=Decimal("-48.6"),
        commissioned_on=date(2021, 3, 15),
    )

    filled = autofill.fill_plant_from_profile(plant, profile)

    assert filled == {}
    assert plant.name == "Minha usina"
    assert plant.installed_power_kwp == Decimal("7.2")
    assert plant.latitude == Decimal("-16.0")
    assert plant.array_tilt_degrees == Decimal(12)
    assert plant.auto_filled is None


@pytest.mark.asyncio
async def test_fill_geocodes_the_city_when_there_are_no_coordinates(monkeypatch) -> None:
    asked: list[str] = []

    async def fake_geocode(city: str):
        asked.append(city)
        return Decimal("-16.686900"), Decimal("-49.264800")

    monkeypatch.setattr(autofill, "geocode_city", fake_geocode)
    plant = _plant()

    located = await autofill.locate_profile(PlantProfile(city="Goiânia"))
    filled = autofill.fill_plant_from_profile(plant, located)

    assert asked == ["Goiânia"]
    assert filled["location"] == "ESTIMATE"
    assert plant.array_tilt_degrees == Decimal(17)


@pytest.mark.asyncio
async def test_fill_without_location_estimates_nothing(monkeypatch) -> None:
    async def no_geocode(city: str):
        return None

    monkeypatch.setattr(autofill, "geocode_city", no_geocode)
    plant = _plant()

    located = await autofill.locate_profile(PlantProfile(city="Lugar Nenhum"))
    filled = autofill.fill_plant_from_profile(plant, located)

    assert filled == {}
    assert plant.array_tilt_degrees is None
    assert plant.module_technology is None


def test_tilt_estimate_is_bounded() -> None:
    assert autofill.estimated_tilt(Decimal("-3.1")) == Decimal(10)
    assert autofill.estimated_tilt(Decimal("-31.7")) == Decimal(30)
    assert autofill.estimated_azimuth(Decimal("5")) == Decimal(180)


@pytest.mark.asyncio
async def test_locate_keeps_brand_coordinates_without_network(monkeypatch) -> None:
    async def boom(city: str):
        raise AssertionError("não deveria geocodificar")

    monkeypatch.setattr(autofill, "geocode_city", boom)
    profile = PlantProfile(latitude=Decimal("-17"), longitude=Decimal("-48"), city="X")
    assert await autofill.locate_profile(profile) is profile


def test_forget_auto_filled_drops_only_edited_fields() -> None:
    plant = _plant()
    plant.auto_filled = {"location": "BRAND", "orientation": "ESTIMATE"}
    autofill.forget_auto_filled(plant, "orientation")
    assert plant.auto_filled == {"location": "BRAND"}
    autofill.forget_auto_filled(plant, "location")
    assert plant.auto_filled is None


class _FlushOnly:
    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_owner_edits_remove_the_automatic_mark() -> None:
    from mplacas.plants.schemas import (
        PlantLocationUpdateRequest,
        PlantTechnicalConfigurationUpdateRequest,
    )
    from mplacas.plants.service import PlantService

    plant = _plant()
    plant.auto_filled = {
        "dc_capacity_kwp": "BRAND",
        "array_tilt_degrees": "ESTIMATE",
        "array_azimuth_degrees": "ESTIMATE",
        "location": "BRAND",
        "module_technology": "ESTIMATE",
    }
    service = PlantService(_FlushOnly())  # type: ignore[arg-type]

    await service.update_technical_configuration(
        plant, PlantTechnicalConfigurationUpdateRequest(array_tilt_degrees=Decimal(15))
    )
    # editar só a inclinação: o azimute continua marcado como estimado
    assert plant.auto_filled == {
        "dc_capacity_kwp": "BRAND",
        "array_azimuth_degrees": "ESTIMATE",
        "location": "BRAND",
        "module_technology": "ESTIMATE",
    }

    await service.update_location(
        plant,
        PlantLocationUpdateRequest(latitude=Decimal("-17.7"), longitude=Decimal("-48.6")),
    )
    assert "location" not in plant.auto_filled


@pytest.mark.asyncio
async def test_profile_failure_never_breaks_the_connection(monkeypatch) -> None:
    import mplacas.providers.router as provider_router
    from mplacas.providers.accounts import ProviderLogin
    from mplacas.providers.base import SolarDevice

    class Broken:
        async def list_devices(self):
            return [SolarDevice("GW-PLANT-1", None, None, None)]

        async def plant_profile(self):
            raise KeyError("plantId")

        async def aclose(self):
            return None

    monkeypatch.setattr(provider_router, "build_client", lambda *a, **k: Broken())
    inspection = await provider_router.verify_with_provider(
        "GROWATT", ProviderLogin(login="u", password="p")
    )
    assert inspection.serials == ["GW-PLANT-1"]
    assert inspection.profile is None
