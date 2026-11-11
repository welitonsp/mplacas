"""Regras puras do assistente de primeira conexão (ADR-096): sem HTTP, sem banco."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

from mplacas.plants.autofill import BRAND, ESTIMATE
from mplacas.plants.schemas import ModuleTechnology
from mplacas.providers.base import PlantProfile
from mplacas.providers.first_connection import (
    _DRAFT_FIELDS,
    DEFAULT_PLANT_NAME,
    build_draft,
    reconcile_origins,
)

ORG = uuid.uuid4()
FULL = PlantProfile(
    name="Usina do Rogério",
    installed_power_kwp=Decimal("5.4"),
    latitude=Decimal("-17.74412345678"),
    longitude=Decimal("-48.625"),
    city="Caldas Novas",
)


def test_draft_without_profile_is_the_default_name_only() -> None:
    draft = build_draft(ORG, None)
    assert draft.values["name"] == DEFAULT_PLANT_NAME == "Minha usina"
    assert all(v is None for k, v in draft.values.items() if k != "name")
    assert draft.origins == {}
    assert draft.city is None
    assert list(draft.values) == list(_DRAFT_FIELDS)


def test_draft_from_full_profile_uses_fixed_decimals_and_origins() -> None:
    draft = build_draft(ORG, FULL)
    assert draft.values == {
        "name": "Usina do Rogério",
        "installed_power_kwp": "5.400",
        "latitude": "-17.744123",
        "longitude": "-48.625000",
        "array_tilt_degrees": "18.00",
        "array_azimuth_degrees": "0.00",
        "module_technology": draft.values["module_technology"],
    }
    assert list(draft.values) == list(_DRAFT_FIELDS)
    assert draft.values["module_technology"] is not None
    assert draft.city == "Caldas Novas"
    assert draft.origins == {
        "name": BRAND,
        "dc_capacity_kwp": BRAND,
        "location": BRAND,
        "array_tilt_degrees": ESTIMATE,
        "array_azimuth_degrees": ESTIMATE,
        "module_technology": ESTIMATE,
    }


def test_estimated_location_is_marked_estimate() -> None:
    profile = PlantProfile(
        latitude=Decimal("-17.7"), longitude=Decimal("-48.6"), location_estimated=True
    )
    draft = build_draft(ORG, profile)
    assert draft.origins["location"] == ESTIMATE
    assert draft.values["name"] == DEFAULT_PLANT_NAME


def test_overlong_name_is_truncated_to_120() -> None:
    draft = build_draft(ORG, PlantProfile(name="x" * 300))
    assert draft.values["name"] == "x" * 120


def _confirmed(**overrides: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "name": "Usina do Rogério",
        "installed_power_kwp": Decimal("5.400"),
        "latitude": Decimal("-17.744123"),
        "longitude": Decimal("-48.625000"),
        "array_tilt_degrees": Decimal("18.00"),
        "array_azimuth_degrees": Decimal("0.00"),
        "module_technology": ModuleTechnology(build_draft(ORG, FULL).values["module_technology"]),
    }
    return SimpleNamespace(**{**base, **overrides})


def _reconcile(**overrides: object):
    draft = build_draft(ORG, FULL)
    return draft, reconcile_origins(_confirmed(**overrides), draft.values, draft.origins)


def test_owner_kept_everything() -> None:
    draft, result = _reconcile()
    assert result.auto_filled == draft.origins
    assert list(result.auto_filled) == list(draft.origins)
    assert result.edited_by_owner == []


def test_changed_name_leaves_auto_filled() -> None:
    draft, result = _reconcile(name="Sítio")
    assert "name" not in result.auto_filled
    assert result.edited_by_owner == ["name"]
    assert result.auto_filled == {k: v for k, v in draft.origins.items() if k != "name"}


def test_equal_numbers_with_different_places_are_kept() -> None:
    _, result = _reconcile(array_tilt_degrees=Decimal("18"))
    assert result.edited_by_owner == []
    draft = {"array_tilt_degrees": "15.30"}
    kept = reconcile_origins(
        SimpleNamespace(array_tilt_degrees=Decimal("15.3")),
        draft,
        {"array_tilt_degrees": ESTIMATE},
    )
    assert kept.auto_filled == {"array_tilt_degrees": ESTIMATE}


def test_location_pair() -> None:
    _, lon_changed = _reconcile(longitude=Decimal("-48.5"))
    assert lon_changed.edited_by_owner == ["location"]
    assert "location" not in lon_changed.auto_filled
    _, lat_changed = _reconcile(latitude=Decimal("-17.5"))
    assert lat_changed.edited_by_owner == ["location"]
    _, both_kept = _reconcile()
    assert both_kept.auto_filled["location"] == BRAND


def test_edited_list_is_sorted() -> None:
    _, result = _reconcile(name="x", array_tilt_degrees=Decimal("1"))
    assert result.edited_by_owner == ["array_tilt_degrees", "name"]


def test_cleared_brand_field_counts_as_edited() -> None:
    _, result = _reconcile(installed_power_kwp=None)
    assert result.edited_by_owner == ["dc_capacity_kwp"]
    assert "dc_capacity_kwp" not in result.auto_filled


def test_field_the_brand_left_empty_is_in_neither() -> None:
    draft = build_draft(ORG, None)
    result = reconcile_origins(
        _confirmed(installed_power_kwp=Decimal("3.000")), draft.values, draft.origins
    )
    assert result.auto_filled == {} and result.edited_by_owner == []


def test_enum_none_and_invalid_text_comparisons() -> None:
    tech = ModuleTechnology(build_draft(ORG, FULL).values["module_technology"])
    same = reconcile_origins(
        SimpleNamespace(module_technology=tech),
        {"module_technology": tech.value},
        {"module_technology": ESTIMATE},
    )
    assert same.auto_filled == {"module_technology": ESTIMATE}
    both_none = reconcile_origins(
        SimpleNamespace(module_technology=None),
        {"module_technology": None},
        {"module_technology": ESTIMATE},
    )
    assert both_none.auto_filled == {"module_technology": ESTIMATE}
    bad = reconcile_origins(
        SimpleNamespace(installed_power_kwp=Decimal("5")),
        {"installed_power_kwp": "abc"},
        {"dc_capacity_kwp": BRAND},
    )
    assert bad.auto_filled == {} and bad.edited_by_owner == ["dc_capacity_kwp"]
