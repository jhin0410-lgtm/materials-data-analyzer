from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

VERSION = "2.6.14"
PACKAGE_ID = "battery_v2_6_external_evidence_line_closeout_v1"
MANIFEST_ID = "battery_v2_6_external_evidence_line_manifest_v1"
CONTRACT_ID = "battery_v2_6_external_evidence_line_closeout_contract_v1"

DEFAULT_CONFIG_PATH = "configs/battery_v2_6_external_evidence_line_closeout.json"
DEFAULT_MANIFEST_PATH = "data/platform/battery_v2_6_external_evidence_line_manifest_v1.json"
DEFAULT_CONTRACT_PATH = "data/platform/battery_v2_6_external_evidence_line_closeout_contract_v1.json"
DEFAULT_OUTPUT_ROOT = "outputs/v2_6_battery_external_evidence_line_closeout"
DEFAULT_TRACKED_SUMMARY = "data/processed/battery_v2_6_14_external_evidence_line_closeout_summary.json"

EXPECTED_MANIFEST_CHECKSUM = "c9222eeea7d57cb3d92322a6e5f13760848a64d6f87a0d9bdf92649d1628afbc"
EXPECTED_CONTRACT_CHECKSUM = "0b33557f292f8f3d42d88bbbd0e072d4608f0d8dac510cda1ad78503c523d55a"
EXPECTED_RESULT_CHECKSUM = "07f35860b13f911437aba07cf383e105425cb6ae15b8fb0b602b4359d4193614"

PROHIBITED_TRUE_FLAGS = (
    "network_called", "credentials_read", "raw_data_read", "archive_read",
    "csv_payload_read", "source_mutation_performed", "cohort_merge_performed",
    "model_trained", "model_evaluated", "metrics_recomputed",
    "threshold_fitting_performed",
)


def canonical_checksum(payload: Mapping[str, Any]) -> str:
    core = copy.deepcopy(dict(payload))
    core.pop("deterministic_result_checksum", None)
    text = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _relative(name: str, value: Any) -> str:
    text = str(value).replace("\\", "/")
    path = Path(text)
    if path.is_absolute() or re.match(r"^[A-Za-z]:", text) or ".." in path.parts:
        raise ValueError(f"{name} must be repository-relative and non-traversing")
    return path.as_posix()


def repo_path(root: str | Path, value: str | Path) -> Path:
    base = Path(root).resolve()
    target = (Path(root) / value).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {value}") from exc
    return target


def load_config(path: str | Path = DEFAULT_CONFIG_PATH, repo_root: str | Path = ".") -> dict[str, Any]:
    value = _json(repo_path(repo_root, path))
    required = {
        "schema_version", "package_id", "case_study_id", "manifest_path",
        "contract_path", "expected_manifest_checksum", "expected_contract_checksum",
        "execution_policy", "credential_policy", "output_root", "tracked_summary_path",
        "output_policy", "execution_mode", "dry_run",
    }
    if set(value) != required:
        raise ValueError("config fields changed")
    if value["schema_version"] != VERSION or value["package_id"] != PACKAGE_ID:
        raise ValueError("unsupported closeout package")
    if value["expected_manifest_checksum"] != EXPECTED_MANIFEST_CHECKSUM:
        raise ValueError("manifest checksum contract changed")
    if value["expected_contract_checksum"] != EXPECTED_CONTRACT_CHECKSUM:
        raise ValueError("contract checksum contract changed")
    expected_policy = {
        "network_access": False, "credential_access": False, "raw_data_read": False,
        "archive_read": False, "csv_payload_read": False, "source_mutation": False,
        "cohort_merge": False, "model_training": False, "model_evaluation": False,
        "metric_recomputation": False, "threshold_fitting": False,
    }
    if value["execution_policy"] != expected_policy:
        raise ValueError("execution policy changed")
    if value["credential_policy"] != {"store_credentials": False, "network_access_required": False}:
        raise ValueError("credential policy changed")
    expected_paths = {
        "manifest_path": DEFAULT_MANIFEST_PATH, "contract_path": DEFAULT_CONTRACT_PATH,
        "output_root": DEFAULT_OUTPUT_ROOT, "tracked_summary_path": DEFAULT_TRACKED_SUMMARY,
    }
    for key, expected in expected_paths.items():
        if _relative(key, value[key]) != expected:
            raise ValueError(f"{key} changed")
    if value["output_policy"] != "tracked_compact_summary_and_local_full_result":
        raise ValueError("output policy changed")
    if value["execution_mode"] != "verify" or value["dry_run"] is not False:
        raise ValueError("execution mode changed")
    return value


def validate_manifest(value: Mapping[str, Any]) -> None:
    if value.get("manifest_id") != MANIFEST_ID:
        raise ValueError("manifest identity changed")
    if canonical_checksum(value) != EXPECTED_MANIFEST_CHECKSUM:
        raise ValueError("manifest checksum mismatch")
    stages = value.get("stages")
    if not isinstance(stages, list) or len(stages) != 13:
        raise ValueError("manifest stage count changed")
    if [item.get("version") for item in stages] != [f"2.6.{number}" for number in range(1, 14)]:
        raise ValueError("manifest stage order changed")
    if len({item.get("artifact_path") for item in stages}) != 13:
        raise ValueError("manifest artifact paths are not unique")
    if len({item.get("expected_checksum") for item in stages}) != 13:
        raise ValueError("manifest checksums are not unique")
    if any(value.get("claim_policy", {}).values()):
        raise ValueError("manifest claim policy was promoted")


def validate_contract(value: Mapping[str, Any]) -> None:
    if value.get("contract_id") != CONTRACT_ID:
        raise ValueError("contract identity changed")
    if canonical_checksum(value) != EXPECTED_CONTRACT_CHECKSUM:
        raise ValueError("contract checksum mismatch")
    if value.get("upstream_identity", {}) != {
        "manifest_checksum": EXPECTED_MANIFEST_CHECKSUM, "stage_count": 13,
        "first_stage": "2.6.1", "last_stage": "2.6.13", "platform_version": "2.4.0",
    }:
        raise ValueError("contract upstream identity changed")
    if any(value.get("execution_policy", {}).values()):
        raise ValueError("contract execution policy was promoted")
    if value.get("required_final_decisions", {}) != {
        "evidence_line_integrity": "verified", "ridge_generalization": "unsupported",
        "cross_cohort_comparability": "not_established", "external_cohort_admission": "not_admitted",
        "predictive_validation_readiness": "not_ready", "provider_to_local_binding": "not_established",
        "engineering_decision_readiness": "not_ready",
        "overall_status": "v2_6_external_evidence_line_closed_predictive_validation_not_ready",
    }:
        raise ValueError("required final decisions changed")


def _verify_stage(stage: Mapping[str, Any], *, repo_root: str | Path) -> dict[str, Any]:
    path = _relative("artifact_path", stage["artifact_path"])
    artifact = _json(repo_path(repo_root, path))
    expected = stage["expected_checksum"]
    if artifact.get("deterministic_result_checksum") != expected:
        raise ValueError(f"{stage['version']} embedded checksum mismatch")
    if canonical_checksum(artifact) != expected:
        raise ValueError(f"{stage['version']} canonical checksum mismatch")
    if artifact.get("schema_version") != stage["version"]:
        raise ValueError(f"{stage['version']} schema version mismatch")
    return {
        "version": stage["version"], "artifact_path": path, "verified_checksum": expected,
        "stage_role": stage["stage_role"], "scientific_status": stage["scientific_status"],
        "decision_status": stage["decision_status"], "primary_blocker": stage["primary_blocker"],
    }


def build_result(manifest: Mapping[str, Any], contract: Mapping[str, Any], *, repo_root: str | Path = ".") -> dict[str, Any]:
    stage_results = [_verify_stage(stage, repo_root=repo_root) for stage in manifest["stages"]]
    result = {
        "schema_version": VERSION,
        "artifact_kind": "battery_v2_6_external_evidence_line_closeout_summary",
        "package_id": PACKAGE_ID,
        "case_study_id": "battery_v2_6_external_evidence_line",
        "manifest_id": MANIFEST_ID,
        "manifest_checksum": canonical_checksum(manifest),
        "contract_id": CONTRACT_ID,
        "contract_checksum": canonical_checksum(contract),
        "stage_count": 13,
        "verified_stage_count": len(stage_results),
        "stage_checksum_failures": [],
        "stage_results": stage_results,
        "software_validation": {
            "status": "supported",
            "basis": "all_13_tracked_upstream_artifacts_match_their_canonical_checksums",
            "public_version_preserved": "2.4.0",
            "existing_model_or_metric_changed": False,
        },
        "decision": {
            "evidence_line_integrity": "verified",
            "registered_nasa_warm_start_benchmark": "preserved",
            "persistence_baseline_scope": "registered_nasa_warm_start_benchmark_only",
            "ridge_generalization": "unsupported",
            "cross_cohort_comparability": "not_established",
            "external_cohort_admission": "not_admitted",
            "predictive_validation_readiness": "not_ready",
            "provider_to_local_binding": "not_established",
            "engineering_decision_readiness": "not_ready",
            "overall_status": "v2_6_external_evidence_line_closed_predictive_validation_not_ready",
        },
        "scientific_closeout": {
            "status": "inconclusive",
            "result": "evidence_line_integrity_supported_predictive_validation_readiness_not_established",
            "strongest_evidence": "Thirteen checksum-bound tracked artifacts preserve the registered benchmark, diagnostics, comparability audits, source-binding attempts, bounded reads, and provider-access closeout without silent scientific promotion.",
            "primary_limitation": "No external cohort has source-backed compatible chemistry, nominal capacity, commanded protocols, cutoff policy, calibration or uncertainty, target definition, stable source snapshot, and provider-to-local binding sufficient for independent predictive validation.",
            "what_would_change_conclusion": list(contract["reopen_conditions"]),
            "suitable_for": ["software and provenance closeout", "portfolio evidence-line documentation", "future source-admission planning"],
            "unsuitable_for": ["external predictive-validation claims", "cross-cohort model comparison", "mechanism or causal claims", "engineering or production decisions"],
        },
        "next_action": {
            "v2_6_status": "closed",
            "automatic_next_feature_stage_authorized": False,
            "recommended_direction": "preserve_this_closeout_and_move_to_a_separate_end_to_end_case_study_or_reopen_only_when_predeclared_source_evidence_exists",
        },
        "network_called": False, "credentials_read": False, "raw_data_read": False,
        "archive_read": False, "csv_payload_read": False, "source_mutation_performed": False,
        "cohort_merge_performed": False, "model_trained": False, "model_evaluated": False,
        "metrics_recomputed": False, "threshold_fitting_performed": False,
    }
    result["deterministic_result_checksum"] = canonical_checksum(result)
    return result


def validate_result(value: Mapping[str, Any]) -> None:
    if value.get("schema_version") != VERSION or value.get("package_id") != PACKAGE_ID:
        raise ValueError("unsupported closeout result")
    if value.get("deterministic_result_checksum") != EXPECTED_RESULT_CHECKSUM or canonical_checksum(value) != EXPECTED_RESULT_CHECKSUM:
        raise ValueError("closeout checksum mismatch")
    if value.get("stage_count") != 13 or value.get("verified_stage_count") != 13 or value.get("stage_checksum_failures") != []:
        raise ValueError("stage verification changed")
    if [item.get("version") for item in value.get("stage_results", [])] != [f"2.6.{number}" for number in range(1, 14)]:
        raise ValueError("stage result order changed")
    for flag in PROHIBITED_TRUE_FLAGS:
        if value.get(flag) is not False:
            raise ValueError(f"prohibited flag promoted: {flag}")
    decision = value.get("decision", {})
    expected = {
        "evidence_line_integrity": "verified", "ridge_generalization": "unsupported",
        "cross_cohort_comparability": "not_established", "external_cohort_admission": "not_admitted",
        "predictive_validation_readiness": "not_ready", "provider_to_local_binding": "not_established",
        "engineering_decision_readiness": "not_ready",
        "overall_status": "v2_6_external_evidence_line_closed_predictive_validation_not_ready",
    }
    for key, expected_value in expected.items():
        if decision.get(key) != expected_value:
            raise ValueError(f"final decision changed: {key}")
    if value.get("software_validation", {}).get("status") != "supported":
        raise ValueError("software validation changed")
    if value.get("scientific_closeout", {}).get("status") != "inconclusive":
        raise ValueError("scientific closeout changed")
    if value.get("next_action", {}).get("automatic_next_feature_stage_authorized") is not False:
        raise ValueError("automatic continuation was promoted")


def execute(config: Mapping[str, Any], *, repo_root: str | Path = ".", write_outputs: bool = False) -> dict[str, Any]:
    manifest = _json(repo_path(repo_root, config["manifest_path"]))
    contract = _json(repo_path(repo_root, config["contract_path"]))
    validate_manifest(manifest)
    validate_contract(contract)
    result = build_result(manifest, contract, repo_root=repo_root)
    validate_result(result)
    if write_outputs:
        output_root = repo_path(repo_root, config["output_root"])
        output_root.mkdir(parents=True, exist_ok=True)
        text = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        (output_root / "external_evidence_line_closeout_result.json").write_text(text, encoding="utf-8")
        repo_path(repo_root, config["tracked_summary_path"]).write_text(text, encoding="utf-8")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="v2.6.14 Battery external-evidence line closeout")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preview")
    sub.add_parser("run")
    validate = sub.add_parser("validate")
    validate.add_argument("result_path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate":
        value = _json(repo_path(args.repo_root, args.result_path))
        validate_result(value)
        payload = {"valid": True, "deterministic_result_checksum": value["deterministic_result_checksum"], "overall_status": value["decision"]["overall_status"]}
    else:
        config = load_config(args.config, repo_root=args.repo_root)
        payload = execute(config, repo_root=args.repo_root, write_outputs=args.command == "run")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True) if args.json else json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
