"""Robust, contamination-resistant seasonal PV performance baseline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal


BASELINE_MODEL_VERSION = "MPLACAS_SEASONAL_PR_BASELINE_V1"
BASELINE_METRIC_NATURE = "TEMPERATURE_CORRECTED_PR_PREFERRED"
CLEAR_SKY_INDEX_NATURE = "EMPIRICAL_SEASONAL_POA_P90"
REFERENCE_WINDOW_DAYS = 366
MINIMUM_BASELINE_SAMPLES = 12
MINIMUM_COMPARISON_SAMPLES = 7
MINIMUM_REPORTING_AVAILABILITY = Decimal("0.95")
MINIMUM_CLEAR_SKY_INDEX = Decimal("0.65")
MAXIMUM_CLEAR_SKY_INDEX = Decimal("1.25")
MAD_SCALE = Decimal("1.4826")
MAD_LIMIT = Decimal("3")


class InsufficientBaselineData(ValueError):
    """Raised when a defensible seasonal comparison cannot yet be produced."""


@dataclass(frozen=True, slots=True)
class SeasonalPerformanceObservation:
    observation_date: date
    poa_irradiation_kwh_m2: Decimal
    performance_ratio: Decimal
    temperature_corrected_performance_ratio: Decimal | None
    reporting_availability_ratio: Decimal | None
    data_quality_status: str
    quality_flags: tuple[str, ...] = ()

    @property
    def selected_performance_ratio(self) -> Decimal:
        return self.temperature_corrected_performance_ratio or self.performance_ratio


@dataclass(frozen=True, slots=True)
class SeasonalBaselineResult:
    observation_date: date
    season_key: str
    reference_start_date: date
    reference_end_date: date
    baseline_sample_count: int
    baseline_excluded_count: int
    comparison_start_date: date
    comparison_sample_count: int
    clear_sky_poa_p90_kwh_m2: Decimal
    target_clear_sky_index: Decimal | None
    baseline_median_performance_ratio: Decimal
    baseline_mad: Decimal
    baseline_q10: Decimal
    baseline_q90: Decimal
    comparison_median_performance_ratio: Decimal
    degradation_percent: Decimal
    annualized_degradation_percent: Decimal | None
    degradation_status: str
    quality_flags: tuple[str, ...]


def calculate_seasonal_baseline(
    observations: tuple[SeasonalPerformanceObservation, ...],
    *,
    target_date: date,
) -> SeasonalBaselineResult:
    """Compare one season with a frozen first-year reference cohort.

    Only observations at or before ``target_date`` are considered. The first
    eligible observation anchors a 366-day reference window; later degraded
    production can therefore never be learned back into the reference.
    """
    eligible = sorted(
        (row for row in observations if row.observation_date <= target_date and _eligible(row)),
        key=lambda row: row.observation_date,
    )
    if not eligible:
        raise InsufficientBaselineData("no eligible final performance observations")

    reference_start = eligible[0].observation_date
    reference_end = reference_start + timedelta(days=REFERENCE_WINDOW_DAYS - 1)
    if target_date <= reference_end:
        raise InsufficientBaselineData("frozen reference year is not complete")

    seasonal_reference = tuple(
        row
        for row in eligible
        if row.observation_date <= reference_end and row.observation_date.month == target_date.month
    )
    if len(seasonal_reference) < MINIMUM_BASELINE_SAMPLES:
        raise InsufficientBaselineData("insufficient seasonal reference samples")

    clear_sky_envelope = _quantile(
        tuple(row.poa_irradiation_kwh_m2 for row in seasonal_reference), Decimal("0.90")
    )
    if clear_sky_envelope <= 0:
        raise InsufficientBaselineData("seasonal clear-sky envelope is unavailable")

    irradiance_reference = tuple(
        row for row in seasonal_reference if _clear_sky_eligible(row, clear_sky_envelope)
    )
    robust_reference = _mad_filter(irradiance_reference)
    if len(robust_reference) < MINIMUM_BASELINE_SAMPLES:
        raise InsufficientBaselineData("insufficient robust baseline samples")

    comparison = tuple(
        row
        for row in eligible
        if reference_end < row.observation_date <= target_date
        and row.observation_date.month == target_date.month
        and _clear_sky_eligible(row, clear_sky_envelope)
    )
    comparison = _mad_filter(comparison)
    if len(comparison) < MINIMUM_COMPARISON_SAMPLES:
        raise InsufficientBaselineData("insufficient uncontaminated comparison samples")

    baseline_values = tuple(row.selected_performance_ratio for row in robust_reference)
    comparison_values = tuple(row.selected_performance_ratio for row in comparison)
    baseline_median = _median(baseline_values)
    comparison_median = _median(comparison_values)
    degradation = (comparison_median / baseline_median - Decimal(1)) * Decimal(100)
    reference_midpoint = _median_ordinal(robust_reference)
    comparison_midpoint = _median_ordinal(comparison)
    elapsed_days = comparison_midpoint - reference_midpoint
    annualized: Decimal | None = None
    if elapsed_days >= 180 and comparison_median > 0:
        years = Decimal(elapsed_days) / Decimal("365.2425")
        annualized = Decimal(
            str((float(comparison_median / baseline_median) ** (1 / float(years)) - 1) * 100)
        )

    target = next((row for row in reversed(eligible) if row.observation_date == target_date), None)
    target_csi = (
        target.poa_irradiation_kwh_m2 / clear_sky_envelope if target is not None else None
    )
    excluded = len(seasonal_reference) - len(robust_reference)
    flags = ["BASELINE_REFERENCE_WINDOW_FROZEN", "SEASONAL_MONTH_BUCKET"]
    if len(irradiance_reference) < len(seasonal_reference):
        flags.append("LOW_IRRADIANCE_REFERENCE_DAYS_EXCLUDED")
    if len(robust_reference) < len(irradiance_reference):
        flags.append("ROBUST_MAD_OUTLIERS_EXCLUDED")

    return SeasonalBaselineResult(
        observation_date=target_date,
        season_key=f"MONTH_{target_date.month:02d}",
        reference_start_date=reference_start,
        reference_end_date=reference_end,
        baseline_sample_count=len(robust_reference),
        baseline_excluded_count=excluded,
        comparison_start_date=min(row.observation_date for row in comparison),
        comparison_sample_count=len(comparison),
        clear_sky_poa_p90_kwh_m2=_round(clear_sky_envelope, "0.001"),
        target_clear_sky_index=_round(target_csi, "0.0001") if target_csi is not None else None,
        baseline_median_performance_ratio=_round(baseline_median, "0.0001"),
        baseline_mad=_round(_mad(baseline_values), "0.0001"),
        baseline_q10=_round(_quantile(baseline_values, Decimal("0.10")), "0.0001"),
        baseline_q90=_round(_quantile(baseline_values, Decimal("0.90")), "0.0001"),
        comparison_median_performance_ratio=_round(comparison_median, "0.0001"),
        degradation_percent=_round(degradation, "0.01"),
        annualized_degradation_percent=(
            _round(annualized, "0.01") if annualized is not None else None
        ),
        degradation_status=_status(degradation),
        quality_flags=tuple(flags),
    )


def _eligible(row: SeasonalPerformanceObservation) -> bool:
    ratio = row.selected_performance_ratio
    return (
        row.data_quality_status == "FINAL"
        and row.reporting_availability_ratio is not None
        and row.reporting_availability_ratio >= MINIMUM_REPORTING_AVAILABILITY
        and row.poa_irradiation_kwh_m2 > 0
        and Decimal(0) < ratio <= Decimal("1.20")
        and not any(flag.startswith("PERFORMANCE_RATIO_ABOVE") for flag in row.quality_flags)
    )


def _clear_sky_eligible(
    row: SeasonalPerformanceObservation, envelope: Decimal
) -> bool:
    index = row.poa_irradiation_kwh_m2 / envelope
    return MINIMUM_CLEAR_SKY_INDEX <= index <= MAXIMUM_CLEAR_SKY_INDEX


def _mad_filter(
    rows: tuple[SeasonalPerformanceObservation, ...],
) -> tuple[SeasonalPerformanceObservation, ...]:
    if not rows:
        return ()
    values = tuple(row.selected_performance_ratio for row in rows)
    center = _median(values)
    mad = _mad(values)
    if mad == 0:
        lower = _quantile(values, Decimal("0.10"))
        upper = _quantile(values, Decimal("0.90"))
        return tuple(
            row for row in rows if lower <= row.selected_performance_ratio <= upper
        )
    limit = MAD_LIMIT * MAD_SCALE * mad
    return tuple(row for row in rows if abs(row.selected_performance_ratio - center) <= limit)


def _median(values: tuple[Decimal, ...]) -> Decimal:
    return _quantile(values, Decimal("0.50"))


def _mad(values: tuple[Decimal, ...]) -> Decimal:
    center = _median(values)
    return _median(tuple(abs(value - center) for value in values))


def _quantile(values: tuple[Decimal, ...], quantile: Decimal) -> Decimal:
    if not values:
        raise ValueError("quantile requires at least one value")
    ordered = sorted(values)
    position = quantile * Decimal(len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - Decimal(lower)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _median_ordinal(rows: tuple[SeasonalPerformanceObservation, ...]) -> int:
    return int(_median(tuple(Decimal(row.observation_date.toordinal()) for row in rows)))


def _status(degradation_percent: Decimal) -> str:
    if degradation_percent <= Decimal("-5"):
        return "DEGRADED"
    if degradation_percent <= Decimal("-3"):
        return "WATCH"
    return "STABLE"


def _round(value: Decimal, quantum: str) -> Decimal:
    return value.quantize(Decimal(quantum), rounding=ROUND_HALF_UP)
