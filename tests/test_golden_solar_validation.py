from __future__ import annotations

import json
from pathlib import Path

import pytest

from mplacas.photovoltaic.golden_validation import (
    GOLDEN_SCHEMA_VERSION,
    evaluate_golden_dataset,
    load_golden_dataset,
)


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_DATASET = ROOT / "tests" / "golden" / "solar_loss_taxonomy_candidates_v1.json"


def test_synthetic_candidate_dataset_is_deterministic_but_not_release_eligible() -> None:
    dataset = load_golden_dataset(CANDIDATE_DATASET)
    report = evaluate_golden_dataset(dataset)

    assert dataset.schema_version == GOLDEN_SCHEMA_VERSION
    assert len(dataset.cases) == 4
    assert dataset.expert_approved is False
    assert report.release_gate_passed is False
    assert "dataset is not approved by a solar specialist" in report.gate_failures
    assert all(metric.false_positive == 0 for metric in report.metrics)
    assert all(metric.false_negative == 0 for metric in report.metrics)


def test_every_checked_in_solar_golden_dataset_obeys_contract() -> None:
    paths = sorted((ROOT / "tests" / "golden").glob("solar_*.json"))

    assert paths
    for path in paths:
        dataset = load_golden_dataset(path)
        report = evaluate_golden_dataset(dataset)
        if dataset.expert_approved:
            assert report.release_gate_passed, report.gate_failures


def test_loader_rejects_direct_identifiers_at_any_depth(tmp_path: Path) -> None:
    payload = json.loads(CANDIDATE_DATASET.read_text(encoding="utf-8"))
    payload["cases"][0]["inputs"]["device_serial"] = "REAL-SERIAL"
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="forbidden identifying fields: device_serial"):
        load_golden_dataset(path)


def test_approved_dataset_cannot_use_synthetic_cases(tmp_path: Path) -> None:
    payload = json.loads(CANDIDATE_DATASET.read_text(encoding="utf-8"))
    payload["expert_review"] = {
        "status": "APPROVED",
        "reviewer_role": "SOLAR_PERFORMANCE_ENGINEER",
        "reviewed_at": "2026-08-02T12:00:00-03:00",
        "evidence_ref": "review-record:example",
    }
    path = tmp_path / "fake-approved.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="only anonymized field cases"):
        load_golden_dataset(path)


def test_release_gate_requires_balanced_labels_for_every_category(tmp_path: Path) -> None:
    payload = json.loads(CANDIDATE_DATASET.read_text(encoding="utf-8"))
    payload["expert_review"] = {
        "status": "APPROVED",
        "reviewer_role": "SOLAR_PERFORMANCE_ENGINEER",
        "reviewed_at": "2026-08-02T12:00:00-03:00",
        "evidence_ref": "controlled-review:solar-golden-v1",
    }
    for case in payload["cases"]:
        case["source_kind"] = "ANONYMIZED_FIELD"
    path = tmp_path / "undersized-approved.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = evaluate_golden_dataset(load_golden_dataset(path))

    assert report.expert_approved is True
    assert report.release_gate_passed is False
    assert any(
        "requires at least 5 positive and 5 negative" in item
        for item in report.gate_failures
    )
