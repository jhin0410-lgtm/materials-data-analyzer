from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from materials_data_analyzer.research_loop.evidence_packet import canonical_sha256
from materials_data_analyzer.research_loop.in625_model_holdout_benchmark import (
    build_in625_ambench_holdout_contract,
)
from materials_data_analyzer.research_loop.in625_published_model_comparator import (
    acquire_kollmannsberger_retrospective_evidence,
    evaluate_kollmannsberger_retrospective_comparator,
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
                "calibration_case_ids": contract["partition"]["calibration_case_ids"],
                "holdout_case_ids": contract["partition"]["holdout_case_ids"],
            },
            sort_keys=True,
        )
    )
    return 0


def acquire(args: argparse.Namespace) -> int:
    evidence = acquire_kollmannsberger_retrospective_evidence()
    _write(args.output, evidence)
    sources = {
        item["source_id"]: item["sha256"]
        for item in evidence["source_bindings"]
    }
    print(
        json.dumps(
            {
                "output": str(args.output),
                "file_sha256": _file_sha(args.output),
                "object_sha256": canonical_sha256(evidence),
                "source_sha256_by_id": sources,
                "parameter_fit_case_ids": evidence["calibration_record"][
                    "parameter_fit_case_ids"
                ],
                "strict_blind_model_selection_established": evidence[
                    "retrospective_scope"
                ]["strict_prospective_holdout_model_selection_established"],
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
        label="holdout contract",
    )
    evidence = _validate_frozen(
        args.evidence,
        file_sha256=args.evidence_file_sha256,
        object_sha256=args.evidence_object_sha256,
        label="published comparator evidence",
    )
    result = evaluate_kollmannsberger_retrospective_comparator(
        contract,
        evidence,
        trusted_contract_sha256=args.contract_object_sha256,
        trusted_evidence_sha256=args.evidence_object_sha256,
        repository_root=str(args.repository_root),
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
                "width_mae_um": result["aggregate_ac_metrics"]["width_mae_um"],
                "depth_mae_um": result["aggregate_ac_metrics"]["depth_mae_um"],
                "strict_blind_model_selection_established": result[
                    "scientific_interpretation"
                ]["strict_blind_model_selection_established"],
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
        description=(
            "Run the provenance-bound retrospective Kollmannsberger AMB2018 "
            "published-model comparator."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    contract = sub.add_parser("freeze-contract")
    contract.add_argument("--repository-root", type=Path, required=True)
    contract.add_argument("--output", type=Path, required=True)
    contract.set_defaults(func=freeze_contract)

    acquisition = sub.add_parser("acquire")
    acquisition.add_argument("--output", type=Path, required=True)
    acquisition.set_defaults(func=acquire)

    scoring = sub.add_parser("evaluate")
    scoring.add_argument("--repository-root", type=Path, required=True)
    scoring.add_argument("--contract", type=Path, required=True)
    scoring.add_argument("--contract-file-sha256", required=True)
    scoring.add_argument("--contract-object-sha256", required=True)
    scoring.add_argument("--evidence", type=Path, required=True)
    scoring.add_argument("--evidence-file-sha256", required=True)
    scoring.add_argument("--evidence-object-sha256", required=True)
    scoring.add_argument("--output", type=Path, required=True)
    scoring.set_defaults(func=evaluate)
    return parser


def main() -> int:
    args = _parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
