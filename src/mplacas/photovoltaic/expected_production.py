"""Pure formula for expected daily PV production (ADR-068).

This module intentionally does no I/O: it composes three already-computed
``Decimal`` quantities into one number. The multiplication used to live in
the frontend (`photovoltaic-contracts.ts::deriveExpectedDailyProduction`,
removed by ADR-068 Etapa C) — a direct violation of ADR-012 ("regras e
cálculos energéticos continuam exclusivamente no backend determinístico").
Moving it here does not change the formula or any number a user sees; it
only changes where the multiplication happens.

Kept out of `seasonal_baseline.py` on purpose: that module owns a
*persisted* model (`BASELINE_MODEL_VERSION`), while this is a value derived
at read time from two different tables. A future change to this formula
(e.g. the P1-02 fix referenced in ADR-068) only needs to bump
`EXPECTED_PRODUCTION_MODEL_VERSION` here, without touching the persisted
baseline model version.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


EXPECTED_PRODUCTION_MODEL_VERSION = "MPLACAS_EXPECTED_DAILY_PRODUCTION_V1"
EXPECTED_PRODUCTION_NATURE = "SEASONAL_CLEAR_SKY_P90_ENVELOPE"


@dataclass(frozen=True, slots=True)
class ExpectedDailyProduction:
    expected_daily_production_kwh: Decimal
    dc_capacity_kwp: Decimal
    clear_sky_poa_p90_kwh_m2: Decimal
    baseline_median_performance_ratio: Decimal
    model_version: str
    nature: str


def calculate_expected_daily_production(
    *,
    dc_capacity_kwp: Decimal | None,
    clear_sky_poa_p90_kwh_m2: Decimal | None,
    baseline_median_performance_ratio: Decimal | None,
) -> ExpectedDailyProduction | None:
    """`dc_capacity_kwp × clear_sky_poa_p90_kwh_m2 × baseline_median_performance_ratio`.

    Returns ``None`` when any input is missing or not strictly positive, or
    when the product itself is not strictly positive. The result is
    quantized to `0.001` kWh with `ROUND_HALF_UP`, matching
    `seasonal_baseline._round`.
    """
    if dc_capacity_kwp is None or dc_capacity_kwp <= 0:
        return None
    if clear_sky_poa_p90_kwh_m2 is None or clear_sky_poa_p90_kwh_m2 <= 0:
        return None
    if baseline_median_performance_ratio is None or baseline_median_performance_ratio <= 0:
        return None

    product = dc_capacity_kwp * clear_sky_poa_p90_kwh_m2 * baseline_median_performance_ratio
    if product <= 0:
        return None

    return ExpectedDailyProduction(
        expected_daily_production_kwh=_round(product, "0.001"),
        dc_capacity_kwp=dc_capacity_kwp,
        clear_sky_poa_p90_kwh_m2=clear_sky_poa_p90_kwh_m2,
        baseline_median_performance_ratio=baseline_median_performance_ratio,
        model_version=EXPECTED_PRODUCTION_MODEL_VERSION,
        nature=EXPECTED_PRODUCTION_NATURE,
    )


def _round(value: Decimal, quantum: str) -> Decimal:
    return value.quantize(Decimal(quantum), rounding=ROUND_HALF_UP)
