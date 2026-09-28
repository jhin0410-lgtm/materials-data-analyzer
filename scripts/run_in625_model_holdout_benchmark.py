from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from materials_data_analyzer.research_loop.evidence_packet import canonical_sha256
from materials_data_analyzer.research_loop.in625_model_holdout_benchmark import (
    build_case_b_persistence_baseline,
    build_in625_ambench_holdout_contract,
    evaluate_in625_ambench_holdout_predictions,
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} must contain one JSON object")
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _validate_frozen(
    path: Path,
    *,
    file_sha256: str,
    object_sha256: str,
    label: str,
) -> dict[str, Any]:
    observed_file = _file_sha(path)
    _require(
        observed_file == file_sha256,
        f"{label} file changed after freeze: {observed_file}",
    )
    value = _load(path)
    observed_object = canonical_sha256(value)
    _require(
        observed_object == object_sha256,
        f"{label} object changed after freeze: {observed_object}",
    )
    return value


def freeze_contract(args: argparse.Namespace) -> int:
    contract = build_in625_ambench_holdout_contract(args.repository_root)
    _write(args.output, contract)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "file_sha256": _file_sha(args.output),
                "object_sha256": canonical_sha256(contract),
                "calibration_cases": contract["partition"]["calibration_case_ids"],
                "holdout_cases": contract["partition"]["holdout_case_ids"],
                "holdout_response_values_exposed": contract["partition"][
                    "holdout_response_values_exposed_in_contract"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


def freeze_baseline(args: argparse.Namespace) -> int:
    contract = _validate_frozen(
        args.contract,
        file_sha256=args.contract_file_sha256,
        object_sha256=args.contract_object_sha256,
        label="benchmark contract",
    )
    prediction = build_case_b_persistence_baseline(
        contract,
        trusted_contract_sha256=args.contract_object_sha256,
    )
    _write(args.output, prediction)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "file_sha256": _file_sha(args.output),
                "object_sha256": canonical_sha256(prediction),
                "model_class": prediction["model"]["model_class"],
                "fit_response_cases": prediction["calibration_provenance"][
                    "response_case_ids_used_for_fit"
                ],
                "holdout_response_values_consumed_before_prediction_freeze": prediction[
                    "calibration_provenance"
                ]["holdout_response_values_consumed_before_prediction_freeze"],
            },
            sort_keys=True,
        )
    )
    return 0


def evaluate(args: argparse.Namespace) -> int:
    contract = _validate_frozen(
        args.contract,
        file_sha256=args.contract_file_sha256,
        object_sha256=args.contract_object_sha256,
        label="benchmark contract",
    )
    prediction = _validate_frozen(
        args.prediction,
        file_sha256=args.prediction_file_sha256,
        object_sha256=args.prediction_object_sha256,
        label="prediction",
    )
    result = evaluate_in625_ambench_holdout_predictions(
        contract,
        prediction,
        trusted_contract_sha256=args.contract_object_sha256,
        trusted_prediction_sha256=args.prediction_object_sha256,
        repository_root=args.repository_root,
    )
    _write(args.output, result)
    by_case = {item["case_id"]: item for item in result["case_metrics"]}
    print(
        json.dumps(
            {
                "output": str(args.output),
                "file_sha256": _file_sha(args.output),
                "object_sha256": canonical_sha256(result),
                "A_width_abs_error_um": by_case["A"]["responses"]["width"][
                    "absolute_error_um"
                ],
                "A_depth_abs_error_um": by_case["A"]["responses"]["depth"][
                    "absolute_error_um"
                ],
                "C_width_abs_error_um": by_case["C"]["responses"]["width"][
                    "absolute_error_um"
                ],
                "C_depth_abs_error_um": by_case["C"]["responses"]["depth"][
                    "absolute_error_um"
                ],
                "holdout_width_mae_um": result["aggregate_holdout_metrics"][
                    "width_mae_um"
                ],
                "holdout_depth_mae_um": result["aggregate_holdout_metrics"][
                    "depth_mae_um"
                ],
                "calibration_case_included_in_holdout_metric": result[
                    "aggregate_holdout_metrics"
                ]["calibration_case_included"],
                "scientific_status_promoted": result["scientific_boundary"][
                    "scientific_status_promoted"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Staged NIST AM-Bench Case-B calibration / A-C holdout benchmark."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    freeze = sub.add_parser("freeze-contract")
    freeze.add_argument("--repository-root", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    freeze.set_defaults(func=freeze_contract)

    baseline = sub.add_parser("freeze-baseline")
    baseline.add_argument("--contract", type=Path, required=True)
    baseline.add_argument("--contract-file-sha256", required=True)
    baseline.add_argument("--contract-object-sha256", required=True)
    baseline.add_argument("--output", type=Path, required=True)
    baseline.set_defaults(func=freeze_baseline)

    scoring = sub.add_parser("evaluate")
    scoring.add_argument("--repository-root", type=Path, required=True)
    scoring.add_argument("--contract", type=Path, required=True)
    scoring.add_argument("--contract-file-sha256", required=True)
    scoring.add_argument("--contract-object-sha256", required=True)
    scoring.add_argument("--prediction", type=Path, required=True)
    scoring.add_argument("--prediction-file-sha256", required=True)
    scoring.add_argument("--prediction-object-sha256", required=True)
    scoring.add_argument("--output", type=Path, required=True)
    scoring.set_defaults(func=evaluate)
    return parser


def main() -> int:
    args = _parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
