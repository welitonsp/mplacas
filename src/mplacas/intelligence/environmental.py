"""Impacto ambiental do ciclo de energia: CO2 evitado e árvores equivalentes.

Função pura, sem I/O, sem sessão de banco, no mesmo padrão de
`energy_engine.py` (ADR-006, ADR-012). Ver ADR-066 para o contrato completo e
a discussão de trade-offs (fator médio vs. marginal, escalar anual vs. série
mensal, e a natureza aproximada do indicador "árvores equivalentes").

Fonte do fator de emissão (`GRID_EMISSION_FACTOR_KG_CO2_PER_KWH`):

O MCTI publica, através do SIRENE (Sistema de Registro Nacional de
Emissões), o fator médio anual de emissão de CO2 da geração de energia
elétrica do Sistema Interligado Nacional (SIN). O portal
`https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/sirene` estava, no momento
desta implementação (2026-08-04), atrás de um WAF que retornava um desafio
JavaScript em vez do conteúdo (não foi possível ler a fonte ao vivo). O valor
abaixo foi confirmado através de uma cópia arquivada pelo Wayback Machine
(web.archive.org) de uma notícia publicada pelo próprio MCTI no domínio
`gov.br/mcti`, não através da planilha oficial "ao vivo":

    "O fator médio anual em 2023 foi de 0,0385 toneladas de C02 por
    megawatt-hora (tCO2/MWh). Na conversão, o número significa 38,5 kg de
    emissão de C02 a cada megawatt-hora."

URL da notícia (snapshot lido em 2026-08-04, arquivado em 2025-04-17):
https://web.archive.org/web/20250417153011/https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/sirene/central-de-conteudo/noti/fator-de-emissao-de-co2-na-geracao-de-energia-eletrica-no-brasil-em-2023-e-o-menor-em-12-anos

Ano de referência: 2023 (fator médio anual, não a série mensal). É o mesmo
valor (0,0385) já registrado como estimativa na seção "Pontos que exigem
confirmação" do ADR-066, agora confirmado por texto oficial do MCTI, ainda
que lido via arquivo e não via planilha original. É o fator MÉDIO da matriz
(inventário corporativo de consumo), não o fator de MARGEM DE OPERAÇÃO
(usado em projetos de MDL) — escolha deliberada registrada no ADR-066,
seção "Negativas".

Fonte do fator de absorção por árvore (`TREE_ABSORPTION_KG_CO2_PER_YEAR`):

Não foi possível, nesta sessão, localizar uma fonte primária brasileira
(Embrapa) ou um valor IPCC específico para floresta tropical em regeneração
com uma cifra direta de "kg de CO2 por árvore por ano" — o dado costuma
existir apenas como taxa de crescimento de biomassa por hectare, que exige
premissas adicionais (densidade de árvores por hectare, espécie, idade) para
virar um número "por árvore". Mantém-se o valor de referência mais citado
internacionalmente, ~48 lb/ano ≈ 21,77 kg/ano por árvore madura, arredondado
para 22 kg — origem: pesquisa do U.S. Forest Service (Coweeta Hydrologic
Laboratory), popularizada pela Arbor Day Foundation e pela EPA dos EUA, e
amplamente reproduzida por veículos brasileiros. NÃO é uma fonte brasileira
nem específica de floresta tropical em regeneração — é a mesma limitação já
registrada no ADR-066 ("Árvores equivalentes é uma aproximação de rigor
limitado"). Fica documentado como ponto em aberto para uma revisão futura
(`_V2`) caso uma fonte Embrapa/IPCC mais adequada seja localizada.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

ENVIRONMENTAL_MODEL_VERSION = "MPLACAS_BR_SIN_ENVIRONMENTAL_V1"

# Fonte: MCTI/SIRENE — Fatores de emissão de CO2 da geração de energia
# elétrica no SIN. Fator médio anual de 2023, em tCO2/MWh (= kgCO2/kWh).
# Ver docstring do módulo para a citação completa e a ressalva sobre acesso
# via Wayback Machine em vez da planilha oficial ao vivo (portal atrás de
# WAF no momento da implementação).
GRID_EMISSION_FACTOR_KG_CO2_PER_KWH: Final = Decimal("0.0385")

# Aproximação. Fonte: pesquisa do U.S. Forest Service (Coweeta Hydrologic
# Laboratory), popularizada pela Arbor Day Foundation / EPA (~48 lb/ano ≈
# 21,77 kg/ano por árvore madura, arredondado para 22 kg). NÃO é fonte
# brasileira nem específica de floresta tropical em regeneração — ver
# docstring do módulo.
TREE_ABSORPTION_KG_CO2_PER_YEAR: Final = Decimal("22")

ENVIRONMENTAL_UNAVAILABLE_NO_PRODUCTION_DATA = "NO_PRODUCTION_DATA"

_ONE_DECIMAL = Decimal("0.1")


def _q1(value: Decimal) -> Decimal:
    return value.quantize(_ONE_DECIMAL, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class EnvironmentalImpact:
    co2_avoided_kg: Decimal | None
    equivalent_trees: int | None
    emission_factor_version: str
    unavailable_reason: str | None


def assess_environmental_impact(
    *, production_kwh: Decimal | None
) -> EnvironmentalImpact:
    """Calcula CO2 evitado e árvores equivalentes a partir da geração do ciclo.

    A base é a geração TOTAL do ciclo (autoconsumo + injeção), não apenas o
    autoconsumo — ver ADR-066, seção "Base de cálculo", para a justificativa
    física. Nunca fabrica um zero: produção ausente ou não positiva resulta
    em campos `None` com motivo explícito. Produção negativa é tratada como
    dado corrompido (`ValueError`), não como ausência de dado.
    """
    if production_kwh is not None and production_kwh < 0:
        raise ValueError("production_kwh cannot be negative")

    if production_kwh is None or production_kwh <= 0:
        return EnvironmentalImpact(
            co2_avoided_kg=None,
            equivalent_trees=None,
            emission_factor_version=ENVIRONMENTAL_MODEL_VERSION,
            unavailable_reason=ENVIRONMENTAL_UNAVAILABLE_NO_PRODUCTION_DATA,
        )

    co2_avoided_kg = _q1(production_kwh * GRID_EMISSION_FACTOR_KG_CO2_PER_KWH)
    equivalent_trees = int(co2_avoided_kg / TREE_ABSORPTION_KG_CO2_PER_YEAR)

    return EnvironmentalImpact(
        co2_avoided_kg=co2_avoided_kg,
        equivalent_trees=equivalent_trees,
        emission_factor_version=ENVIRONMENTAL_MODEL_VERSION,
        unavailable_reason=None,
    )
