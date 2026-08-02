"""Versioned golden-dataset contract and classification quality metrics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from mplacas.photovoltaic.loss_taxonomy import (
    DailyLossTaxonomyInput,
    EvidenceLevel,
    LossCategory,
    classify_daily_losses,
)


GOLDEN_SCHEMA_VERSION = "MPLACAS_SOLAR_GOLDEN_V1"
FORBIDDEN_IDENTIFIER_KEYS = frozenset(
    {
        "plant_name",
        "organization_name",
        "device_serial",
        "provider_account",
        "latitude",
        "longitude",
        "address",
        "customer_name",
    }
)


class GroundTruthLabel(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NOT_ASSESSABLE = "NOT_ASSESSABLE"


class ReviewStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"


@dataclass(frozen=True, slots=True)
class ExpertReview:
    status: ReviewStatus
    reviewer_role: str | None
    reviewed_at: datetime | None
    evidence_ref: str | None


@dataclass(frozen=True, slots=True)
class GoldenCase:
    case_id: str
    source_kind: str
    inputs: DailyLossTaxonomyInput
    expected_labels: dict[LossCategory, GroundTruthLabel]


@dataclass(frozen=True, slots=True)
class GoldenDataset:
    schema_version: str
    dataset_id: str
    description: str
    review: ExpertReview
    cases: tuple[GoldenCase, ...]

    @property
    def expert_approved(self) -> bool:
        return self.review.status == ReviewStatus.APPROVED


@dataclass(frozen=True, slots=True)
class CategoryMetrics:
    category: LossCategory
    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int
    abstained: int
    excluded: int
    precision: Decimal | None
    recall: Decimal | None
    false_positive_rate: Decimal | None
    false_negative_rate: Decimal | None
    coverage: Decimal | None


@dataclass(frozen=True, slots=True)
class GoldenEvaluationReport:
    dataset_id: str
    expert_approved: bool
    case_count: int
    metrics: tuple[CategoryMetrics, ...]
    release_gate_passed: bool
    gate_failures: tuple[str, ...]


def load_golden_dataset(path: Path) -> GoldenDataset:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("golden dataset root must be an object")
    _reject_identifiers(payload)
    if payload.get("schema_version") != GOLDEN_SCHEMA_VERSION:
        raise ValueError("unsupported golden dataset schema version")
    dataset_id = _required_text(payload, "dataset_id")
    description = _required_text(payload, "description")
    review_payload = payload.get("expert_review")
    if not isinstance(review_payload, dict):
        raise ValueError("expert_review must be an object")
    review = _parse_review(review_payload)
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("golden dataset must contain cases")
    cases = tuple(_parse_case(item) for item in raw_cases)
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("golden case IDs must be unique")
    if review.status == ReviewStatus.APPROVED:
        if any(case.source_kind != "ANONYMIZED_FIELD" for case in cases):
            raise ValueError("approved datasets may contain only anonymized field cases")
        if review.reviewed_at is None or review.reviewed_at.tzinfo is None:
            raise ValueError("approved review requires timezone-aware reviewed_at")
        if not review.reviewer_role or not review.evidence_ref:
            raise ValueError("approved review requires reviewer role and evidence reference")
    return GoldenDataset(
        schema_version=GOLDEN_SCHEMA_VERSION,
        dataset_id=dataset_id,
        description=description,
        review=review,
        cases=cases,
    )


def evaluate_golden_dataset(dataset: GoldenDataset) -> GoldenEvaluationReport:
    counters = {
        category: {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "abstained": 0, "excluded": 0}
        for category in LossCategory
    }
    for case in dataset.cases:
        predicted = {
            assessment.category: assessment.evidence_level
            for assessment in classify_daily_losses(case.inputs)
        }
        for category in LossCategory:
            expected = case.expected_labels[category]
            level = predicted[category]
            if expected == GroundTruthLabel.NOT_ASSESSABLE:
                counters[category]["excluded"] += 1
                continue
            predicted_positive = level in (EvidenceLevel.LIKELY, EvidenceLevel.POSSIBLE)
            if level == EvidenceLevel.NOT_ASSESSABLE:
                counters[category]["abstained"] += 1
            if expected == GroundTruthLabel.POSITIVE:
                counters[category]["tp" if predicted_positive else "fn"] += 1
            else:
                counters[category]["fp" if predicted_positive else "tn"] += 1

    metrics = tuple(_metrics(category, counters[category]) for category in LossCategory)
    failures = _gate_failures(dataset, metrics)
    return GoldenEvaluationReport(
        dataset_id=dataset.dataset_id,
        expert_approved=dataset.expert_approved,
        case_count=len(dataset.cases),
        metrics=metrics,
        release_gate_passed=not failures,
        gate_failures=failures,
    )


def _metrics(category: LossCategory, counts: dict[str, int]) -> CategoryMetrics:
    tp, fp = counts["tp"], counts["fp"]
    fn, tn = counts["fn"], counts["tn"]
    labeled = tp + fp + fn + tn
    return CategoryMetrics(
        category=category,
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        true_negative=tn,
        abstained=counts["abstained"],
        excluded=counts["excluded"],
        precision=_ratio(tp, tp + fp),
        recall=_ratio(tp, tp + fn),
        false_positive_rate=_ratio(fp, fp + tn),
        false_negative_rate=_ratio(fn, tp + fn),
        coverage=_ratio(labeled - counts["abstained"], labeled),
    )


def _gate_failures(
    dataset: GoldenDataset, metrics: tuple[CategoryMetrics, ...]
) -> tuple[str, ...]:
    failures: list[str] = []
    if not dataset.expert_approved:
        failures.append("dataset is not approved by a solar specialist")
    for metric in metrics:
        positives = metric.true_positive + metric.false_negative
        negatives = metric.false_positive + metric.true_negative
        prefix = metric.category.value
        if positives < 5 or negatives < 5:
            failures.append(f"{prefix}: requires at least 5 positive and 5 negative labels")
            continue
        for name, value, minimum in (
            ("precision", metric.precision, Decimal("0.80")),
            ("recall", metric.recall, Decimal("0.80")),
            ("coverage", metric.coverage, Decimal("0.90")),
        ):
            if value is None or value < minimum:
                failures.append(f"{prefix}: {name} below {minimum}")
        for name, value, maximum in (
            ("false_positive_rate", metric.false_positive_rate, Decimal("0.20")),
            ("false_negative_rate", metric.false_negative_rate, Decimal("0.20")),
        ):
            if value is None or value > maximum:
                failures.append(f"{prefix}: {name} above {maximum}")
    return tuple(failures)


def _parse_review(payload: dict[str, Any]) -> ExpertReview:
    status_raw = payload.get("status")
    if not isinstance(status_raw, str):
        raise ValueError("invalid expert review status")
    try:
        status = ReviewStatus(status_raw)
    except ValueError as exc:
        raise ValueError("invalid expert review status") from exc
    reviewed_at_raw = payload.get("reviewed_at")
    reviewed_at = (
        datetime.fromisoformat(reviewed_at_raw) if isinstance(reviewed_at_raw, str) else None
    )
    return ExpertReview(
        status=status,
        reviewer_role=_optional_text(payload.get("reviewer_role")),
        reviewed_at=reviewed_at,
        evidence_ref=_optional_text(payload.get("evidence_ref")),
    )


def _parse_case(payload: Any) -> GoldenCase:
    if not isinstance(payload, dict):
        raise ValueError("golden case must be an object")
    case_id = _required_text(payload, "case_id")
    source_kind = _required_text(payload, "source_kind")
    if source_kind not in {"SYNTHETIC_REGRESSION", "ANONYMIZED_FIELD"}:
        raise ValueError("invalid golden case source_kind")
    inputs = payload.get("inputs")
    labels = payload.get("expected_labels")
    if not isinstance(inputs, dict) or not isinstance(labels, dict):
        raise ValueError("golden case inputs and expected_labels must be objects")
    if set(labels) != {category.value for category in LossCategory}:
        raise ValueError("every loss category requires one expected label")
    return GoldenCase(
        case_id=case_id,
        source_kind=source_kind,
        inputs=DailyLossTaxonomyInput(
            performance_ratio=_decimal(inputs, "performance_ratio"),
            temperature_corrected_performance_ratio=_optional_decimal(
                inputs, "temperature_corrected_performance_ratio"
            ),
            reporting_availability_ratio=_optional_decimal(
                inputs, "reporting_availability_ratio"
            ),
            data_quality_status=_required_text(inputs, "data_quality_status"),
            measured_energy_kwh=_decimal(inputs, "measured_energy_kwh"),
            poa_irradiation_kwh_m2=_decimal(inputs, "poa_irradiation_kwh_m2"),
            dc_capacity_kwp=_decimal(inputs, "dc_capacity_kwp"),
            ac_capacity_kw=_optional_decimal(inputs, "ac_capacity_kw"),
            baseline_median_performance_ratio=_optional_decimal(
                inputs, "baseline_median_performance_ratio"
            ),
            baseline_degradation_status=_optional_text(
                inputs.get("baseline_degradation_status")
            ),
            baseline_degradation_percent=_optional_decimal(
                inputs, "baseline_degradation_percent"
            ),
            target_clear_sky_index=_optional_decimal(inputs, "target_clear_sky_index"),
            precipitation_sample_days=_integer(inputs, "precipitation_sample_days"),
            dry_days=_integer(inputs, "dry_days"),
        ),
        expected_labels={
            category: GroundTruthLabel(labels[category.value]) for category in LossCategory
        },
    )


def _reject_identifiers(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_IDENTIFIER_KEYS.intersection(value)
        if forbidden:
            raise ValueError(f"forbidden identifying fields: {', '.join(sorted(forbidden))}")
        for nested in value.values():
            _reject_identifiers(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_identifiers(nested)


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _decimal(payload: dict[str, Any], key: str) -> Decimal:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a decimal string")
    return Decimal(value)


def _optional_decimal(payload: dict[str, Any], key: str) -> Decimal | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a decimal string or null")
    return Decimal(value)


def _integer(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    return value


def _ratio(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001"))
