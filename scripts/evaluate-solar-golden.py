from __future__ import annotations

import argparse
import json
from pathlib import Path

from mplacas.photovoltaic.golden_validation import (
    evaluate_golden_dataset,
    load_golden_dataset,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate one Mplacas solar golden dataset")
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    report = evaluate_golden_dataset(load_golden_dataset(args.dataset))
    payload = {
        "dataset_id": report.dataset_id,
        "expert_approved": report.expert_approved,
        "case_count": report.case_count,
        "release_gate_passed": report.release_gate_passed,
        "gate_failures": list(report.gate_failures),
        "metrics": [
            {
                "category": metric.category.value,
                "true_positive": metric.true_positive,
                "false_positive": metric.false_positive,
                "false_negative": metric.false_negative,
                "true_negative": metric.true_negative,
                "abstained": metric.abstained,
                "excluded": metric.excluded,
                "precision": str(metric.precision) if metric.precision is not None else None,
                "recall": str(metric.recall) if metric.recall is not None else None,
                "false_positive_rate": (
                    str(metric.false_positive_rate)
                    if metric.false_positive_rate is not None
                    else None
                ),
                "false_negative_rate": (
                    str(metric.false_negative_rate)
                    if metric.false_negative_rate is not None
                    else None
                ),
                "coverage": str(metric.coverage) if metric.coverage is not None else None,
            }
            for metric in report.metrics
        ],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if report.release_gate_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
