"""Métricas de qualidade do ciclo no relatório mensal.

Inclui, desde o ADR-082, quanto da produção do ciclo foi estimado (dias sem
leitura do inversor estimados pelo sol, e piso pelo medidor da distribuidora)
— para que nenhum número estimado apareça como medido.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from mplacas.reports.contract import ReportMetric

_ENGINE_SOURCE = "MPLACAS_DETERMINISTIC_ENGINE"


class _Quality(Protocol):
    @property
    def missing_days(self) -> int: ...

    @property
    def provisional_days(self) -> int: ...

    @property
    def incomplete_days(self) -> int: ...

    @property
    def unavailable_days(self) -> int: ...


def _count(key: str, label: str, value: int) -> ReportMetric:
    return ReportMetric(
        key=key,
        label=label,
        value=str(value),
        unit="days",
        nature="QUALITY_COUNT",
        source=_ENGINE_SOURCE,
    )


def project_quality(quality: _Quality) -> tuple[ReportMetric, ...]:
    metrics = [
        _count("missing_days", "Dias ausentes", quality.missing_days),
        _count("provisional_days", "Dias provisórios", quality.provisional_days),
        _count("incomplete_days", "Dias incompletos", quality.incomplete_days),
        _count("unavailable_days", "Dias indisponíveis", quality.unavailable_days),
    ]
    estimated_days = getattr(quality, "estimated_days", 0)
    estimated_kwh = getattr(quality, "estimated_production_kwh", Decimal("0"))
    floor_kwh = getattr(quality, "meter_floor_kwh", Decimal("0"))
    metrics += [
        _count("estimated_production_days", "Dias com produção estimada pelo sol", estimated_days),
        ReportMetric(
            key="estimated_production_kwh",
            label="Produção estimada (dias sem leitura)",
            value=str(estimated_kwh),
            unit="kWh",
            nature="ESTIMATED",
            source=_ENGINE_SOURCE,
        ),
        ReportMetric(
            key="meter_floor_kwh",
            label="Produção acrescentada pelo piso do medidor",
            value=str(floor_kwh),
            unit="kWh",
            nature="ESTIMATED",
            source=_ENGINE_SOURCE,
        ),
    ]
    return tuple(metrics)
