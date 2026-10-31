"""Preenche a usina com o que a marca informa, na conexão (ADR-093 § 7).

Regras:

- Só preenche campo **vazio**. O que o dono informou nunca é sobrescrito.
- Cada campo preenchido fica marcado em ``Plant.auto_filled`` com a origem:
  ``BRAND`` (veio do app da marca) ou ``ESTIMATE`` (estimativa nossa). A tela
  mostra "confira" nesses campos; ao editar, a marca some.
- Estimativas só onde há regra física conhecida e só para destravar a
  produção esperada: coordenadas pela cidade, inclinação ≈ latitude (entre 10°
  e 30°), painéis voltados para o equador e módulo monocristalino (o mais
  comum no Brasil). Potência nunca é estimada.
- Data de ligação nunca é preenchida: o regime da Lei 14.300 e o retorno do
  investimento dependem dela, e nenhuma marca informa a data real.
- A rede (geocodificação) roda em ``locate_profile``, **antes** de abrir a
  transação; ``fill_plant_from_profile`` não faz I/O.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Awaitable, Callable
from decimal import Decimal

import httpx

from mplacas.db.models import Plant
from mplacas.plants.schemas import ModuleTechnology
from mplacas.providers.base import PlantProfile
from mplacas.providers.profile import parse_coordinate

logger = logging.getLogger(__name__)

BRAND = "BRAND"
ESTIMATE = "ESTIMATE"

# Nomes dos campos como a API de configuração da usina os expõe.
NAME = "name"
DC_CAPACITY = "dc_capacity_kwp"
LOCATION = "location"
TILT = "array_tilt_degrees"
AZIMUTH = "array_azimuth_degrees"
MODULE_TECHNOLOGY = "module_technology"

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
_MIN_TILT = Decimal(10)
_MAX_TILT = Decimal(30)

Coordinates = tuple[Decimal, Decimal]
Geocoder = Callable[[str], Awaitable[Coordinates | None]]


async def geocode_city_open_meteo(city: str) -> Coordinates | None:
    """Coordenadas aproximadas (centro da cidade) pelo Open-Meteo, no Brasil.

    Melhor esforço: falha de rede, nome ambíguo ou resposta estranha devolvem
    ``None`` e a usina segue sem localização.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            response = await client.get(
                GEOCODING_URL,
                params={
                    "name": city,
                    "count": "1",
                    "language": "pt",
                    "format": "json",
                    "countryCode": "BR",
                },
            )
        if response.status_code != 200:
            return None
        results = response.json().get("results")
    except (httpx.HTTPError, ValueError, AttributeError):
        logger.info("plant_autofill_geocoding_unavailable")
        return None
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        return None
    latitude = parse_coordinate(results[0].get("latitude"), limit=90)
    longitude = parse_coordinate(results[0].get("longitude"), limit=180)
    if latitude is None or longitude is None:
        return None
    return latitude, longitude


# Ponto de troca para testes: nunca chama a internet fora de produção.
geocode_city: Geocoder = geocode_city_open_meteo


def estimated_tilt(latitude: Decimal) -> Decimal:
    tilt = abs(latitude).quantize(Decimal(1))
    return min(max(tilt, _MIN_TILT), _MAX_TILT)


def estimated_azimuth(latitude: Decimal) -> Decimal:
    """0° = norte (convenção de ``photovoltaic.poa``): no hemisfério sul os
    painéis olham para o norte; no norte, para o sul (180°)."""
    return Decimal(0) if latitude < 0 else Decimal(180)


async def locate_profile(profile: PlantProfile | None) -> PlantProfile | None:
    """Completa as coordenadas pela cidade quando a marca não as deu (com rede).

    Chamar fora de qualquer transação: a consulta pode levar alguns segundos.
    """
    if profile is None or profile.latitude is not None or not profile.city:
        return profile
    found = await geocode_city(profile.city)
    if found is None:
        return profile
    return dataclasses.replace(
        profile, latitude=found[0], longitude=found[1], location_estimated=True
    )


def fill_plant_from_profile(
    plant: Plant, profile: PlantProfile | None, *, set_name: bool = False
) -> dict[str, str]:
    """Preenche os campos vazios (sem I/O) e devolve ``{campo: origem}`` do que mudou."""
    filled: dict[str, str] = {}
    profile = profile or PlantProfile()

    if set_name and profile.name:
        plant.name = profile.name
        filled[NAME] = BRAND
    if plant.installed_power_kwp is None and profile.installed_power_kwp is not None:
        plant.installed_power_kwp = profile.installed_power_kwp
        filled[DC_CAPACITY] = BRAND
    if (
        plant.latitude is None
        and plant.longitude is None
        and profile.latitude is not None
        and profile.longitude is not None
    ):
        plant.latitude, plant.longitude = profile.latitude, profile.longitude
        filled[LOCATION] = ESTIMATE if profile.location_estimated else BRAND
    if plant.latitude is not None:
        if plant.array_tilt_degrees is None:
            plant.array_tilt_degrees = estimated_tilt(plant.latitude)
            filled[TILT] = ESTIMATE
        if plant.array_azimuth_degrees is None:
            plant.array_azimuth_degrees = estimated_azimuth(plant.latitude)
            filled[AZIMUTH] = ESTIMATE
        if plant.module_technology is None:
            plant.module_technology = ModuleTechnology.MONOCRYSTALLINE_SILICON.value
            filled[MODULE_TECHNOLOGY] = ESTIMATE

    if filled:
        plant.auto_filled = {**(plant.auto_filled or {}), **filled}
    return filled


def forget_auto_filled(plant: Plant, *fields: str) -> None:
    """O dono editou: o valor passa a ser dele, sem marca de "automático"."""
    if not plant.auto_filled:
        return
    remaining = {key: value for key, value in plant.auto_filled.items() if key not in fields}
    plant.auto_filled = remaining or None
