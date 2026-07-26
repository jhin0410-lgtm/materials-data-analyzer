from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from . import battery_michigan_formation_deepblue_metadata_retrieval_gate as gate

EXPECTED_FAILURE_CHECKSUM = "5b43bec9448c339b0a6cc958f7af321a44d16b0acffc66099e7436d07975e7f2"
OBSERVED_ERROR_CATEGORY = "http_status_403"
OBSERVED_OVERALL_STATUS = "provider_metadata_endpoint_access_denied_gate_not_passed"


def build_result(
    contract: Mapping[str, Any],
    evidence: Mapping[str, Any],
    preservation: Mapping[str, Any],
) -> dict[str, Any]:
    result = gate._base_result(
        gate.canonical_checksum(contract),
        gate.canonical_checksum(evidence),
        preservation,
    )
    result.update(
        {
            "retrieval_status": "failed",
            "error_category": OBSERVED_ERROR_CATEGORY,
            "network_call_count": 1,
            "network_called": True,
            "dataset_response": None,
            "file_set_records": [],
            "metadata_completeness": {
                "file_set_ids_recovered": False,
                "labels_recovered": False,
                "sizes_recovered": False,
                "mime_types_recovered": False,
                "repository_checksums_recovered": False,
                "original_checksums_recovered": False,
            },
            "access_observation": {
                "endpoint_kind": "official_dataset_metadata_json",
                "http_status": 403,
                "observation_scope": "user_reported_local_execution_context",
                "response_body_retained": False,
                "credentials_sent": False,
                "redirect_followed": False,
            },
            "decision": {
                "provider_dataset_identity": "documented_not_api_verified",
                "top_level_file_set_metadata": "access_denied_for_observed_execution_context",
                "internal_provider_manifest": "not_established",
                "local_archive_binding": "not_established",
                "provider_to_standardized_row_binding": "not_established",
                "cross_cohort_comparability": "not_admitted",
                "predictive_validation": "blocked",
                "overall_status": OBSERVED_OVERALL_STATUS,
            },
            "scientific_closeout": {
                "status": "inconclusive",
                "result": "payload_free_metadata_retrieval_access_denied",
                "strongest_evidence": (
                    "A bounded HTTPS GET to the official Deep Blue dataset metadata endpoint "
                    "returned HTTP 403 in the user-reported local execution context; no response "
                    "body was retained."
                ),
                "primary_limitation": (
                    "No dataset-specific metadata body was retrieved, and one observed HTTP 403 "
                    "does not establish that the provider API is globally inaccessible."
                ),
                "suitable_for": [
                    "source-access diagnostics",
                    "metadata-gate stop decision",
                    "provenance-preserving failure reporting",
                ],
                "unsuitable_for": [
                    "provider file-set identity claims",
                    "provider-to-local binding",
                    "cross-cohort comparability",
                    "predictive validation",
                    "model training or evaluation",
                ],
            },
        }
    )
    result["deterministic_result_checksum"] = gate.canonical_checksum(result)
    return result


def validate_result(value: Mapping[str, Any]) -> None:
    if value.get("schema_version") != gate.VERSION or value.get("package_id") != gate.PACKAGE_ID:
        raise ValueError("unsupported access-closeout result")
    if value.get("deterministic_result_checksum") != EXPECTED_FAILURE_CHECKSUM:
        raise ValueError("unexpected access-closeout checksum")
    if gate.canonical_checksum(value) != EXPECTED_FAILURE_CHECKSUM:
        raise ValueError("access-closeout content checksum mismatch")
    for flag in gate.PROHIBITED_TRUE_FLAGS:
        if value.get(flag) is not False:
            raise ValueError(f"prohibited result flag promoted: {flag}")
    if value.get("retrieval_status") != "failed":
        raise ValueError("retrieval failure status changed")
    if value.get("error_category") != OBSERVED_ERROR_CATEGORY:
        raise ValueError("observed error category changed")
    if value.get("network_called") is not True or value.get("network_call_count") != 1:
        raise ValueError("observed network-call audit changed")
    if value.get("dataset_response") is not None or value.get("file_set_records") != []:
        raise ValueError("provider metadata was claimed despite access denial")
    expected_observation = {
        "endpoint_kind": "official_dataset_metadata_json",
        "http_status": 403,
        "observation_scope": "user_reported_local_execution_context",
        "response_body_retained": False,
        "credentials_sent": False,
        "redirect_followed": False,
    }
    if value.get("access_observation") != expected_observation:
        raise ValueError("access observation changed")
    decision = value.get("decision", {})
    if decision.get("overall_status") != OBSERVED_OVERALL_STATUS:
        raise ValueError("access-closeout decision changed")
    if decision.get("top_level_file_set_metadata") != "access_denied_for_observed_execution_context":
        raise ValueError("metadata access result changed")
    if decision.get("internal_provider_manifest") != "not_established":
        raise ValueError("internal manifest claim was promoted")
    if decision.get("cross_cohort_comparability") != "not_admitted":
        raise ValueError("comparability boundary changed")
    if decision.get("predictive_validation") != "blocked":
        raise ValueError("predictive-validation boundary changed")
    if value.get("scientific_closeout", {}).get("status") != "inconclusive":
        raise ValueError("scientific closeout changed")


def execute(*, repo_root: str | Path = ".", write_outputs: bool = False) -> dict[str, Any]:
    config = gate.load_config(repo_root=repo_root)
    contract = gate._json(gate.repo_path(repo_root, config["contract_path"]))
    evidence = gate._json(gate.repo_path(repo_root, config["api_evidence_path"]))
    upstream = gate._json(gate.repo_path(repo_root, config["v2_6_12_provider_package_summary_path"]))
    gate.validate_contract(contract)
    gate.validate_api_evidence(evidence)
    preservation = gate.verify_upstream(upstream)
    result = build_result(contract, evidence, preservation)
    validate_result(result)
    if write_outputs:
        text = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        output_root = gate.repo_path(repo_root, config["output_root"])
        output_root.mkdir(parents=True, exist_ok=True)
        (output_root / "deepblue_metadata_access_closeout.json").write_text(text, encoding="utf-8")
        gate.repo_path(repo_root, config["tracked_summary_path"]).write_text(text, encoding="utf-8")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="v2.6.13 Deep Blue metadata access-denial closeout")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("render")
    validate = sub.add_parser("validate")
    validate.add_argument("result_path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "render":
        payload = execute(repo_root=args.repo_root, write_outputs=True)
    else:
        payload = gate._json(gate.repo_path(args.repo_root, args.result_path))
        validate_result(payload)
        payload = {
            "valid": True,
            "retrieval_status": "failed",
            "error_category": OBSERVED_ERROR_CATEGORY,
            "deterministic_result_checksum": EXPECTED_FAILURE_CHECKSUM,
        }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True) if args.json else json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
