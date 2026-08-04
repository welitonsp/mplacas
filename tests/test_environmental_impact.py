from __future__ import annotations

from decimal import Decimal

import pytest

from mplacas.intelligence.environmental import (
    ENVIRONMENTAL_MODEL_VERSION,
    ENVIRONMENTAL_UNAVAILABLE_NO_PRODUCTION_DATA,
    GRID_EMISSION_FACTOR_KG_CO2_PER_KWH,
    TREE_ABSORPTION_KG_CO2_PER_YEAR,
    assess_environmental_impact,
)


def test_computes_co2_avoided_and_equivalent_trees_for_positive_production() -> None:
    result = assess_environmental_impact(production_kwh=Decimal("1000"))

    assert result.co2_avoided_kg == Decimal("38.5")
    # 38.5 / 22 = 1.75... truncado para 1, não arredondado para 2.
    assert result.equivalent_trees == 1
    assert result.emission_factor_version == ENVIRONMENTAL_MODEL_VERSION
    assert result.unavailable_reason is None


def test_quantizes_co2_avoided_with_round_half_up() -> None:
    # 10 * 0.0385 = 0.385, que fica mais próximo de 0.4 do que de 0.3 na
    # quantização em 1 casa decimal (ROUND_HALF_UP).
    result = assess_environmental_impact(production_kwh=Decimal("10"))

    assert result.co2_avoided_kg == Decimal("0.4")


def test_returns_unavailable_when_production_is_none() -> None:
    result = assess_environmental_impact(production_kwh=None)

    assert result.co2_avoided_kg is None
    assert result.equivalent_trees is None
    assert result.unavailable_reason == ENVIRONMENTAL_UNAVAILABLE_NO_PRODUCTION_DATA
    assert result.emission_factor_version == ENVIRONMENTAL_MODEL_VERSION


def test_returns_unavailable_when_production_is_zero_never_fabricating_zero() -> None:
    result = assess_environmental_impact(production_kwh=Decimal("0"))

    assert result.co2_avoided_kg is None
    assert result.equivalent_trees is None
    assert result.unavailable_reason == ENVIRONMENTAL_UNAVAILABLE_NO_PRODUCTION_DATA


def test_rejects_negative_production_as_corrupted_data() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        assess_environmental_impact(production_kwh=Decimal("-1"))


def test_truncates_equivalent_trees_down_instead_of_rounding() -> None:
    # 200 * 0.0385 = 7.7 kg de CO2 evitado; 7.7 / 22 = 0.35..., que trunca
    # para 0. Esse zero é legítimo (resultado de cálculo), não ausência de
    # dado: co2_avoided_kg permanece um valor positivo real.
    result = assess_environmental_impact(production_kwh=Decimal("200"))

    assert result.co2_avoided_kg == Decimal("7.7")
    assert result.equivalent_trees == 0
    assert result.unavailable_reason is None


def test_emission_factor_constant_is_pinned_and_requires_version_bump_to_change() -> None:
    """Trava o valor exato do fator de emissão.

    Qualquer alteração no valor numérico de `GRID_EMISSION_FACTOR_KG_CO2_PER_KWH`
    faz este teste falhar. Isso é intencional: o fator é versionado
    (ADR-038/ADR-066) e uma mudança de valor exige subir
    `ENVIRONMENTAL_MODEL_VERSION` para `_V2`, não apenas editar a constante
    in-place. Quem alterar o valor deve também atualizar este teste e a
    versão do modelo na mesma mudança.
    """
    assert GRID_EMISSION_FACTOR_KG_CO2_PER_KWH == Decimal("0.0385")
    assert TREE_ABSORPTION_KG_CO2_PER_YEAR == Decimal("22")
    assert ENVIRONMENTAL_MODEL_VERSION == "MPLACAS_BR_SIN_ENVIRONMENTAL_V1"
