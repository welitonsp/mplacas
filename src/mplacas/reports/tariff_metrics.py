"""Métricas da tarifa usada na conta "sem a usina" (ADR-080).

Ficam no snapshot para rastreabilidade: quem lê o relatório sabe se a
economia saiu da tarifa cheia homologada ou, na falta dela, do preço da
própria fatura (que subestima a economia em faturas SCEE).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from mplacas.reports.contract import ReportMetric

_ENGINE_SOURCE = "MPLACAS_DETERMINISTIC_ENGINE"


class _HasSavingsTariff(Protocol):
    @property
    def savings_tariff_brl_kwh(self) -> Decimal | None: ...

    @property
    def savings_tariff_source(self) -> str | None: ...

    @property
    def flag_tariff_brl_kwh(self) -> Decimal | None: ...

    @property
    def non_energy_credits_brl(self) -> Decimal | None: ...


def savings_tariff_metrics(intelligence: _HasSavingsTariff) -> tuple[ReportMetric, ...]:
    tariff = intelligence.savings_tariff_brl_kwh
    return (
        ReportMetric(
            key="savings_tariff_brl_kwh",
            label="Tarifa usada na conta sem a usina",
            value="" if tariff is None else str(tariff),
            unit="BRL/kWh",
            nature="CALCULATED",
            source=_ENGINE_SOURCE,
        ),
        ReportMetric(
            key="savings_tariff_source",
            label="Origem da tarifa da conta sem a usina",
            value=intelligence.savings_tariff_source or "",
            unit=None,
            nature="ASSUMPTION",
            source=_ENGINE_SOURCE,
        ),
        # ADR-085: o que entrou e o que saiu da conta da economia, como lido
        # na fatura. Vazio quando a fatura não traz a linha.
        ReportMetric(
            key="flag_tariff_brl_kwh",
            label="Bandeira tarifária somada à conta sem a usina",
            value=""
            if intelligence.flag_tariff_brl_kwh is None
            else str(intelligence.flag_tariff_brl_kwh),
            unit="BRL/kWh",
            nature="MEASURED",
            source="UTILITY_BILL",
        ),
        ReportMetric(
            key="non_energy_credits_brl",
            label="Créditos da fatura que não vêm da usina (fora da economia)",
            value=""
            if intelligence.non_energy_credits_brl is None
            else str(intelligence.non_energy_credits_brl),
            unit="BRL",
            nature="MEASURED",
            source="UTILITY_BILL",
        ),
    )
