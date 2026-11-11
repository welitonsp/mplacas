"""Regras puras do assistente de primeira conexão (ADR-096).

Sem sessão, sem HTTP, sem auditoria: só montar o rascunho da usina a partir do
que a marca informou e conciliar, na confirmação, o que o cliente manteve ou
mudou. Sessões, bilhete e chamadas à marca ficam no roteador de provedores.
"""

from __future__ import annotations

import enum
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from mplacas.db.models import Plant
from mplacas.plants.autofill import fill_plant_from_profile
from mplacas.providers.base import PlantProfile

DEFAULT_PLANT_NAME = "Minha usina"

_DRAFT_FIELDS = (
    "name",
    "installed_power_kwp",
    "latitude",
    "longitude",
    "array_tilt_degrees",
    "array_azimuth_degrees",
    "module_technology",
)
# Campo do rascunho → chave de ``plants.auto_filled`` (``plants.autofill``).
_ORIGIN_KEYS = {
    "name": "name",
    "installed_power_kwp": "dc_capacity_kwp",
    "latitude": "location",
    "longitude": "location",
    "array_tilt_degrees": "array_tilt_degrees",
    "array_azimuth_degrees": "array_azimuth_degrees",
    "module_technology": "module_technology",
}


def _text(value: object, places: str | None = None) -> str | None:
    """Rascunho como texto, já no formato que a confirmação aceita (casas)."""
    if value is None:
        return None
    if places is not None and isinstance(value, Decimal):
        return str(value.quantize(Decimal(places)))
    return str(value)


def _same(value: object, drafted: str | None) -> bool:
    if value is None or drafted is None:
        return value is None and drafted is None
    if isinstance(value, Decimal):
        try:
            return value == Decimal(drafted)
        except ArithmeticError:
            return False
    if isinstance(value, enum.Enum):
        return str(value.value) == drafted
    return str(value) == drafted


@dataclass(frozen=True, slots=True)
class Draft:
    values: dict[str, str | None]  # os _DRAFT_FIELDS, nesta ordem, como texto
    city: str | None
    origins: dict[str, str]  # o "filled" de fill_plant_from_profile


def build_draft(organization_id: uuid.UUID, profile: PlantProfile | None) -> Draft:
    # Rascunho numa usina que nunca vai para o banco (só para aplicar as regras).
    draft_plant = Plant(organization_id=organization_id, name=DEFAULT_PLANT_NAME)
    filled = fill_plant_from_profile(draft_plant, profile, set_name=True)
    texts: dict[str, str | None] = {
        "name": (draft_plant.name or DEFAULT_PLANT_NAME)[:120],
        "installed_power_kwp": _text(draft_plant.installed_power_kwp, "0.001"),
        "latitude": _text(draft_plant.latitude, "0.000001"),
        "longitude": _text(draft_plant.longitude, "0.000001"),
        "array_tilt_degrees": _text(draft_plant.array_tilt_degrees, "0.01"),
        "array_azimuth_degrees": _text(draft_plant.array_azimuth_degrees, "0.01"),
        "module_technology": draft_plant.module_technology,
    }
    values = {field: texts[field] for field in _DRAFT_FIELDS}
    return Draft(values=values, city=profile.city if profile else None, origins=filled)


@dataclass(frozen=True, slots=True)
class ConfirmedOrigins:
    auto_filled: dict[str, str]
    edited_by_owner: list[str]


def reconcile_origins(
    confirmed: object, draft: Mapping[str, str | None], origins: Mapping[str, str]
) -> ConfirmedOrigins:
    kept: dict[str, str] = {}
    for field_name in _DRAFT_FIELDS:
        key = _ORIGIN_KEYS[field_name]
        origin = origins.get(key)
        if origin and _same(getattr(confirmed, field_name), draft.get(field_name)):
            kept.setdefault(key, origin)
        elif origin:
            kept[key] = ""  # mudado pelo cliente: o valor é dele
    auto_filled = {key: origin for key, origin in kept.items() if origin}
    return ConfirmedOrigins(
        auto_filled=auto_filled,
        edited_by_owner=sorted(key for key, origin in kept.items() if not origin),
    )
