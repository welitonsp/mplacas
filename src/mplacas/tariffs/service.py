"""Tarifa cheia de um ciclo de faturamento (ADR-080).

A conta "sem a usina" precisa da tarifa que paga quem não tem geração
própria. Na fatura SCEE ela não aparece: a linha "CONSUMO SCEE" usa a tarifa
da energia compensada, com a TE reduzida. A tarifa cheia vem da tabela
homologada pela ANEEL, ponderada pelos dias do ciclo em cada vigência — o
mesmo pró-rata que a distribuidora aplica quando um reajuste cai no meio do
ciclo.

Convenção de dias da Equatorial, conferida nas faturas reais: o consumo de um
ciclo vai do dia seguinte à leitura anterior até o dia da leitura atual. Com
o ciclo do domínio (``cycle_start`` = leitura anterior, ``cycle_end`` =
véspera da leitura atual), isso é ``cycle_start + 1`` até ``cycle_end + 1``.
Assim a média reproduz o preço impresso: nov/2024 (5 dias a 0,710630 e 26 a
0,745930) = 0,740236; nov/2025, tarifa SCEE (6 dias a 0,498120 e 27 a
0,613030) = 0,592137.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.tariffs.db_models import DistributorTariffRecord

# Única classe suportada hoje: residencial B1 convencional (a do cliente de
# referência). Outras classes e distribuidoras entram por importação de dados.
RESIDENTIAL_B1_CONVENTIONAL = "B1_RESIDENCIAL_CONVENCIONAL"


async def full_tariff_without_taxes(
    session: AsyncSession,
    *,
    distributor: str,
    cycle_start: date,
    cycle_end: date,
    tariff_class: str = RESIDENTIAL_B1_CONVENTIONAL,
) -> Decimal | None:
    """Tarifa cheia sem tributos (R$/kWh) do ciclo, ponderada por dia.

    ``None`` quando algum dia do ciclo não tem vigência cadastrada — nunca
    completa com outra vigência nem com a tarifa SCEE da fatura.
    """
    if cycle_end < cycle_start:
        raise ValueError("cycle end cannot precede start")
    rows = (
        await session.scalars(
            select(DistributorTariffRecord).where(
                DistributorTariffRecord.distributor == distributor,
                DistributorTariffRecord.tariff_class == tariff_class,
                DistributorTariffRecord.valid_from <= cycle_end + timedelta(days=1),
                DistributorTariffRecord.valid_to >= cycle_start + timedelta(days=1),
            )
        )
    ).all()
    total = Decimal("0")
    days = 0
    day = cycle_start + timedelta(days=1)
    last_day = cycle_end + timedelta(days=1)
    while day <= last_day:
        covering = [row for row in rows if row.valid_from <= day <= row.valid_to]
        if len(covering) != 1:
            return None  # dia sem vigência (ou vigências sobrepostas): sem palpite
        total += covering[0].full_brl_kwh
        days += 1
        day += timedelta(days=1)
    return (total / days).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
