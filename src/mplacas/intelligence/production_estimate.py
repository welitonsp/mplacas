"""Produção estimada para dias sem leitura do inversor (ADR-082).

Quando a usina fica sem internet, o inversor continua gerando, mas a
NEPViewer não registra o dia — e nunca vai registrar. Sem estimativa, o ciclo
fica com produção (e autoconsumo, e economia) menor que a real.

Estimativa, nesta ordem de preferência:

1. **Sol do dia × rendimento da própria usina.** Para cada dia sem leitura com
   irradiação conhecida, produção = irradiação do dia × mediana do rendimento
   (kWh produzidos ÷ kWh/m² de sol) dos dias medidos vizinhos. É a própria
   usina medindo a si mesma: sujeira, sombra e perdas já estão no rendimento.
2. **Piso pelo medidor da distribuidora**, só em ciclo com dia sem leitura: o
   total nunca fica abaixo da energia que o medidor registrou saindo para a
   rede, porque o que foi injetado foi, necessariamente, produzido.

Tudo é marcado como estimado; nada vira "medido".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from statistics import median

# Mínimo de dias medidos (com sol conhecido) para confiar no rendimento.
MINIMUM_REFERENCE_DAYS = 5
_KWH = Decimal("0.001")


@dataclass(frozen=True, slots=True)
class ProductionEstimate:
    measured_kwh: Decimal
    estimated_kwh: Decimal
    estimated_days: int
    # Dias sem leitura que não puderam ser estimados (sem sol conhecido ou
    # sem rendimento de referência).
    unestimated_days: int
    # Quanto o piso do medidor acrescentou ao total (0 quando não atuou).
    meter_floor_kwh: Decimal
    yield_kwh_per_kwh_m2: Decimal | None

    @property
    def total_kwh(self) -> Decimal:
        return self.measured_kwh + self.estimated_kwh + self.meter_floor_kwh

    @property
    def is_estimated(self) -> bool:
        return self.estimated_days > 0 or self.meter_floor_kwh > 0


def reference_yield(
    measured: dict[date, Decimal],
    irradiation: dict[date, Decimal],
) -> Decimal | None:
    """Mediana de kWh/(kWh/m²) dos dias com leitura e sol conhecidos."""
    ratios = [
        energy / irradiation[day]
        for day, energy in measured.items()
        if energy > 0 and irradiation.get(day) is not None and irradiation[day] > 0
    ]
    if len(ratios) < MINIMUM_REFERENCE_DAYS:
        return None
    return Decimal(median(ratios)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def estimate_cycle_production(
    *,
    cycle_days: list[date],
    measured: dict[date, Decimal],
    irradiation: dict[date, Decimal],
    reference_measured: dict[date, Decimal],
    meter_generation_kwh: Decimal | None,
) -> ProductionEstimate:
    """Produção do ciclo com os dias sem leitura estimados.

    ``measured`` são os dias do ciclo com leitura utilizável;
    ``reference_measured`` são os dias medidos da janela de referência (o
    ciclo e seus vizinhos), usados só para o rendimento.
    """
    measured_kwh = sum((measured[day] for day in cycle_days if day in measured), Decimal("0"))
    missing = [day for day in cycle_days if day not in measured]
    ratio = reference_yield(reference_measured, irradiation) if missing else None

    estimated = Decimal("0")
    estimated_days = 0
    for day in missing:
        sun = irradiation.get(day)
        # Sol zero ou desconhecido não vira "dia estimado": não há base física.
        if ratio is None or sun is None or sun <= 0:
            continue
        estimated += sun * ratio
        estimated_days += 1
    estimated = estimated.quantize(_KWH, rounding=ROUND_HALF_UP)

    floor = Decimal("0")
    # Só em ciclo com dia sem leitura: num ciclo completo, produção abaixo do
    # medidor é divergência a mostrar (inversor subnotificando, recorte de
    # datas), não algo a esconder com o piso.
    if (
        missing
        and meter_generation_kwh is not None
        and measured_kwh + estimated < meter_generation_kwh
    ):
        floor = (meter_generation_kwh - measured_kwh - estimated).quantize(
            _KWH, rounding=ROUND_HALF_UP
        )
    return ProductionEstimate(
        measured_kwh=measured_kwh,
        estimated_kwh=estimated,
        estimated_days=estimated_days,
        unestimated_days=len(missing) - estimated_days,
        meter_floor_kwh=floor,
        yield_kwh_per_kwh_m2=ratio,
    )
