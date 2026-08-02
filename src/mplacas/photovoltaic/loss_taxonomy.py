"""Evidence-aware taxonomy for daily photovoltaic loss signals."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum


LOSS_TAXONOMY_MODEL_VERSION = "MPLACAS_DAILY_LOSS_TAXONOMY_V1"


class LossCategory(StrEnum):
    COMMUNICATION = "COMMUNICATION"
    UNAVAILABILITY = "UNAVAILABILITY"
    CLIPPING = "CLIPPING"
    SOILING = "SOILING"
    SHADING = "SHADING"
    TEMPERATURE = "TEMPERATURE"
    DEGRADATION = "DEGRADATION"
    UNEXPLAINED = "UNEXPLAINED"


class EvidenceLevel(StrEnum):
    LIKELY = "LIKELY"
    POSSIBLE = "POSSIBLE"
    NOT_DETECTED = "NOT_DETECTED"
    NOT_ASSESSABLE = "NOT_ASSESSABLE"


@dataclass(frozen=True, slots=True)
class DailyLossTaxonomyInput:
    performance_ratio: Decimal
    temperature_corrected_performance_ratio: Decimal | None
    reporting_availability_ratio: Decimal | None
    data_quality_status: str
    measured_energy_kwh: Decimal
    poa_irradiation_kwh_m2: Decimal
    dc_capacity_kwp: Decimal
    ac_capacity_kw: Decimal | None
    baseline_median_performance_ratio: Decimal | None = None
    baseline_degradation_status: str | None = None
    baseline_degradation_percent: Decimal | None = None
    target_clear_sky_index: Decimal | None = None
    precipitation_sample_days: int = 0
    dry_days: int = 0


@dataclass(frozen=True, slots=True)
class LossAssessment:
    category: LossCategory
    evidence_level: EvidenceLevel
    estimated_loss_percent: Decimal | None
    evidence_codes: tuple[str, ...]
    limitation: str | None = None


def classify_daily_losses(data: DailyLossTaxonomyInput) -> tuple[LossAssessment, ...]:
    """Classify signals without turning daily proxies into confirmed root causes."""
    _validate(data)
    selected_pr = (
        data.temperature_corrected_performance_ratio or data.performance_ratio
    )
    shortfall = (
        (selected_pr / data.baseline_median_performance_ratio - Decimal(1))
        * Decimal(100)
        if data.baseline_median_performance_ratio is not None
        and data.baseline_median_performance_ratio > 0
        else None
    )

    communication = _communication(data)
    unavailability = _unavailability(data, shortfall)
    clipping = _clipping(data)
    soiling = _soiling(data, shortfall, communication)
    shading = LossAssessment(
        LossCategory.SHADING,
        EvidenceLevel.NOT_ASSESSABLE,
        None,
        ("INTERVAL_POWER_AND_SOLAR_GEOMETRY_PROFILE_UNAVAILABLE",),
        "daily aggregates cannot distinguish recurring geometric shading",
    )
    temperature = _temperature(data)
    degradation = _degradation(data)
    explained = any(
        item.evidence_level == EvidenceLevel.LIKELY
        for item in (communication, unavailability, temperature, degradation)
    )
    if shortfall is None:
        unexplained = LossAssessment(
            LossCategory.UNEXPLAINED,
            EvidenceLevel.NOT_ASSESSABLE,
            None,
            ("SEASONAL_BASELINE_UNAVAILABLE",),
        )
    elif shortfall <= Decimal("-5") and not explained:
        unexplained = LossAssessment(
            LossCategory.UNEXPLAINED,
            EvidenceLevel.POSSIBLE,
            _round(abs(shortfall)),
            ("ROBUST_BASELINE_SHORTFALL_WITHOUT_LIKELY_CAUSE",),
        )
    else:
        unexplained = LossAssessment(
            LossCategory.UNEXPLAINED,
            EvidenceLevel.NOT_DETECTED,
            None,
            ("NO_UNEXPLAINED_MATERIAL_SHORTFALL",),
        )
    return (
        communication,
        unavailability,
        clipping,
        soiling,
        shading,
        temperature,
        degradation,
        unexplained,
    )


def _communication(data: DailyLossTaxonomyInput) -> LossAssessment:
    if data.reporting_availability_ratio is None:
        return LossAssessment(
            LossCategory.COMMUNICATION,
            EvidenceLevel.NOT_ASSESSABLE,
            None,
            ("REPORTING_AVAILABILITY_PROXY_UNAVAILABLE",),
        )
    if data.data_quality_status == "INCOMPLETE" or data.reporting_availability_ratio < Decimal(
        "0.98"
    ):
        missing = (Decimal(1) - data.reporting_availability_ratio) * Decimal(100)
        return LossAssessment(
            LossCategory.COMMUNICATION,
            EvidenceLevel.LIKELY,
            _round(missing),
            ("INCOMPLETE_DAILY_DEVICE_REPORTING", "CAPACITY_WEIGHTED_REPORTING_GAP"),
            "estimated percentage is missing reporting capacity, not confirmed energy loss",
        )
    return LossAssessment(
        LossCategory.COMMUNICATION,
        EvidenceLevel.NOT_DETECTED,
        None,
        ("DAILY_DEVICE_REPORTING_COMPLETE",),
    )


def _unavailability(
    data: DailyLossTaxonomyInput, shortfall: Decimal | None
) -> LossAssessment:
    reporting_complete = (
        data.reporting_availability_ratio is not None
        and data.reporting_availability_ratio >= Decimal("0.98")
        and data.data_quality_status == "FINAL"
    )
    if reporting_complete and data.measured_energy_kwh == 0 and data.poa_irradiation_kwh_m2 >= 3:
        return LossAssessment(
            LossCategory.UNAVAILABILITY,
            EvidenceLevel.LIKELY,
            Decimal("100.00"),
            ("ZERO_ENERGY_WITH_COMPLETE_REPORTING", "MATERIAL_POA_IRRADIATION"),
            "interval operating states are unavailable",
        )
    if reporting_complete and shortfall is not None and shortfall <= Decimal("-15"):
        return LossAssessment(
            LossCategory.UNAVAILABILITY,
            EvidenceLevel.POSSIBLE,
            _round(abs(shortfall)),
            ("MATERIAL_BASELINE_SHORTFALL_WITH_COMPLETE_REPORTING",),
            "daily energy cannot separate outage from other loss mechanisms",
        )
    return LossAssessment(
        LossCategory.UNAVAILABILITY,
        EvidenceLevel.NOT_DETECTED,
        None,
        ("NO_DAILY_UNAVAILABILITY_SIGNAL",),
        "technical availability requires interval operating-state telemetry",
    )


def _clipping(data: DailyLossTaxonomyInput) -> LossAssessment:
    if data.ac_capacity_kw is None:
        return LossAssessment(
            LossCategory.CLIPPING,
            EvidenceLevel.NOT_ASSESSABLE,
            None,
            ("AC_CAPACITY_UNAVAILABLE", "INTERVAL_POWER_UNAVAILABLE"),
        )
    dc_ac_ratio = data.dc_capacity_kwp / data.ac_capacity_kw
    if (
        dc_ac_ratio >= Decimal("1.20")
        and data.target_clear_sky_index is not None
        and data.target_clear_sky_index >= Decimal("0.90")
    ):
        return LossAssessment(
            LossCategory.CLIPPING,
            EvidenceLevel.POSSIBLE,
            None,
            ("HIGH_DC_AC_RATIO", "HIGH_CLEAR_SKY_INDEX", "INTERVAL_POWER_UNAVAILABLE"),
            "daily energy and capacity ratio indicate risk, not confirmed clipping",
        )
    return LossAssessment(
        LossCategory.CLIPPING,
        EvidenceLevel.NOT_DETECTED,
        None,
        ("NO_DAILY_CLIPPING_RISK_SIGNAL",),
        "confirmation requires interval AC power plateau detection",
    )


def _soiling(
    data: DailyLossTaxonomyInput,
    shortfall: Decimal | None,
    communication: LossAssessment,
) -> LossAssessment:
    if data.precipitation_sample_days < 21:
        return LossAssessment(
            LossCategory.SOILING,
            EvidenceLevel.NOT_ASSESSABLE,
            None,
            ("INSUFFICIENT_PRECIPITATION_HISTORY",),
        )
    if (
        data.dry_days >= 21
        and shortfall is not None
        and shortfall <= Decimal("-3")
        and communication.evidence_level != EvidenceLevel.LIKELY
    ):
        return LossAssessment(
            LossCategory.SOILING,
            EvidenceLevel.POSSIBLE,
            _round(abs(shortfall)),
            ("EXTENDED_DRY_PERIOD", "ROBUST_BASELINE_SHORTFALL"),
            "rain history is a proxy; cleaning events and soiling sensors are unavailable",
        )
    return LossAssessment(
        LossCategory.SOILING,
        EvidenceLevel.NOT_DETECTED,
        None,
        ("NO_COMBINED_DRY_PERIOD_AND_SHORTFALL_SIGNAL",),
    )


def _temperature(data: DailyLossTaxonomyInput) -> LossAssessment:
    corrected = data.temperature_corrected_performance_ratio
    if corrected is None or corrected <= 0:
        return LossAssessment(
            LossCategory.TEMPERATURE,
            EvidenceLevel.NOT_ASSESSABLE,
            None,
            ("TEMPERATURE_CORRECTED_PR_UNAVAILABLE",),
        )
    thermal_loss = (corrected - data.performance_ratio) / corrected * Decimal(100)
    if thermal_loss >= Decimal("3"):
        level = EvidenceLevel.LIKELY
    elif thermal_loss >= Decimal("1"):
        level = EvidenceLevel.POSSIBLE
    else:
        level = EvidenceLevel.NOT_DETECTED
    return LossAssessment(
        LossCategory.TEMPERATURE,
        level,
        _round(max(thermal_loss, Decimal(0))) if level != EvidenceLevel.NOT_DETECTED else None,
        ("STANDARD_VS_TEMPERATURE_CORRECTED_PR_DELTA",),
        "thermal effect is modeled from daily ambient temperature and simplified NOCT",
    )


def _degradation(data: DailyLossTaxonomyInput) -> LossAssessment:
    if data.baseline_degradation_status is None:
        return LossAssessment(
            LossCategory.DEGRADATION,
            EvidenceLevel.NOT_ASSESSABLE,
            None,
            ("SEASONAL_DEGRADATION_BASELINE_UNAVAILABLE",),
        )
    if data.baseline_degradation_status == "DEGRADED":
        level = EvidenceLevel.LIKELY
    elif data.baseline_degradation_status == "WATCH":
        level = EvidenceLevel.POSSIBLE
    else:
        level = EvidenceLevel.NOT_DETECTED
    loss = (
        _round(abs(data.baseline_degradation_percent))
        if data.baseline_degradation_percent is not None
        and data.baseline_degradation_percent < 0
        and level != EvidenceLevel.NOT_DETECTED
        else None
    )
    return LossAssessment(
        LossCategory.DEGRADATION,
        level,
        loss,
        ("FROZEN_SEASONAL_BASELINE_COMPARISON",),
        "persistent loss signal is not a component-level root-cause diagnosis",
    )


def _validate(data: DailyLossTaxonomyInput) -> None:
    if data.performance_ratio < 0:
        raise ValueError("performance ratio cannot be negative")
    if data.measured_energy_kwh < 0 or data.poa_irradiation_kwh_m2 < 0:
        raise ValueError("energy and irradiation cannot be negative")
    if data.dc_capacity_kwp <= 0:
        raise ValueError("DC capacity must be positive")
    if data.ac_capacity_kw is not None and data.ac_capacity_kw <= 0:
        raise ValueError("AC capacity must be positive")
    if data.dry_days < 0 or data.precipitation_sample_days < 0:
        raise ValueError("climate sample counts cannot be negative")
    if data.dry_days > data.precipitation_sample_days:
        raise ValueError("dry days cannot exceed precipitation sample days")


def _round(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
