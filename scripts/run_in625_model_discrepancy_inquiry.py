from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from materials_data_analyzer.research_loop.evidence_packet import canonical_sha256
from materials_data_analyzer.research_loop.in625_model_discrepancy_inquiry import (
    run_in625_model_discrepancy_inquiry,
)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} must contain one JSON object")
    return value


def _sha(value: str, label: str) -> str:
    if (
        len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise RuntimeError(f"{label} must be lowercase SHA-256")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Feed a frozen IN625 retrospective comparator into critic/planning."
    )
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--evaluation-file-sha256", required=True)
    parser.add_argument("--evaluation-object-sha256", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    expected_file = _sha(args.evaluation_file_sha256, "evaluation file SHA-256")
    observed_file = hashlib.sha256(args.evaluation.read_bytes()).hexdigest()
    if observed_file != expected_file:
        raise RuntimeError(
            f"evaluation file changed after freeze: expected {expected_file}, observed {observed_file}"
        )

    evaluation = _load_json(args.evaluation)
    expected_object = _sha(args.evaluation_object_sha256, "evaluation object SHA-256")
    observed_object = canonical_sha256(evaluation)
    if observed_object != expected_object:
        raise RuntimeError(
            "evaluation object changed after freeze: "
            f"expected {expected_object}, observed {observed_object}"
        )

    result = run_in625_model_discrepancy_inquiry(
        evaluation,
        trusted_evaluation_sha256=expected_object,
        output_root=args.output_root,
    )
    selected = result["plan"]["selected_next_action"]
    print(
        json.dumps(
            {
                "inquiry_sha256": result["inquiry_sha256"],
                "hypothesis_count": len(result["competing_hypotheses"]),
                "critic_report_sha256": result["ancestry"]["critic_report_sha256"],
                "candidate_action_count": len(result["plan"]["ranked_actions"]),
                "selected_action_id": selected["action_id"],
                "selected_action_class": selected["action_class"],
                "selected_utility": selected["utility_score"],
                "prospective_blind_validation_established": result[
                    "bounded_interpretation"
                ]["prospective_blind_validation_established"],
                "scientific_status_promoted": result["authority_boundary"][
                    "scientific_status_promoted"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
