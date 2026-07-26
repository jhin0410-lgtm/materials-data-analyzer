from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

VERSION = "2.6.11"
PACKAGE_ID = "battery_external_cohort_next_source_selection_gate_v1"
CONTRACT_ID = "battery_external_cohort_next_source_selection_contract_v1"
REGISTER_ID = "battery_external_cohort_source_candidate_register_v1"
DEFAULT_CONFIG_PATH = "configs/examples/battery_external_cohort_next_source_selection_gate.json"
DEFAULT_CONTRACT_PATH = "data/platform/battery_external_cohort_next_source_selection_contract_v1.json"
DEFAULT_REGISTER_PATH = "data/platform/battery_external_cohort_source_candidate_register_v1.json"
DEFAULT_V264_PATH = "data/processed/battery_v2_6_4_external_cohort_admission_summary.json"
DEFAULT_V2610_PATH = "data/processed/battery_v2_6_10_snl_lfp_transition_artifact_evidence_summary.json"
DEFAULT_OUTPUT_ROOT = "outputs/v2_6_battery_next_source_selection"
DEFAULT_TRACKED_SUMMARY = "data/processed/battery_v2_6_11_external_cohort_next_source_selection_summary.json"
EXPECTED_V264_CHECKSUM = "2776bc152c0e4655f0c90ec6513883aea3758cac7fac687e02e5685c72dfdb6f"
EXPECTED_V2610_CHECKSUM = "0093de000c25cfcbbd36eaf8216eabc7fb3bc3db23b724dbffcb69b4d77ddf28"
EXPECTED_REGISTER_CHECKSUM = "fc0a863cd80756fee7048682fc2c0d13b876d5ee6442b889daa1bc30b1fa8b00"
EXPECTED_CONTRACT_CHECKSUM = "c960b21fc061393d4ebeba5e9a6a5f2d105c25da1514f8017feee0deef339079"
SELECTED_ARCHIVE = "Michigan Formation.zip"
CANDIDATE_ARCHIVES = (
    "CALCE.zip", "HNEI.zip", "Michigan Expansion.zip",
    "Michigan Formation.zip", "Oxford.zip", "SNL LFP.zip",
    "SNL NCA.zip", "SNL NMC.zip", "UL-Purdue.zip",
)
FALSE_FLAGS = (
    "network_called", "credentials_read", "raw_archive_read",
    "local_archive_payload_read", "provider_raw_bundle_downloaded",
    "provider_file_payload_read", "filename_metadata_inferred",
    "missing_metadata_inferred", "cross_cohort_comparability_promoted",
    "candidate_admitted", "cohort_merge_performed", "model_trained",
    "model_evaluated", "metrics_recomputed", "source_mutation_performed",
)
COMPACT_ASSESSMENT_KEYS = (
    "archive_name", "disposition", "stable_dataset_record", "dataset_doi",
    "dataset_version", "detailed_readme_declared", "raw_cycler_data_declared",
    "cell_tracker_declared", "test_schedule_declared", "source_code_declared",
    "local_to_source_binding", "hard_gate_passed",
)


def canonical_checksum(payload: Mapping[str, Any]) -> str:
    core = copy.deepcopy(dict(payload))
    core.pop("deterministic_result_checksum", None)
    text = json.dumps(core, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)
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


def load_config(path: str | Path = DEFAULT_CONFIG_PATH,
                repo_root: str | Path = ".") -> dict[str, Any]:
    value = _json(repo_path(repo_root, path))
    required = {
        "schema_version", "package_id", "case_study_id", "candidate_bundle_id",
        "contract_path", "candidate_register_path",
        "v2_6_4_external_cohort_admission_summary_path",
        "v2_6_10_snl_lfp_closeout_summary_path", "expected_v2_6_4_checksum",
        "expected_v2_6_10_checksum", "execution_policy", "credential_policy",
        "output_root", "tracked_summary_path", "output_policy",
        "execution_mode", "dry_run",
    }
    if set(value) != required:
        raise ValueError("config fields changed")
    if value["schema_version"] != VERSION or value["package_id"] != PACKAGE_ID:
        raise ValueError("unsupported selection package")
    if value["candidate_bundle_id"] != "battery_archive_local_bundle_v1":
        raise ValueError("candidate bundle changed")
    if value["expected_v2_6_4_checksum"] != EXPECTED_V264_CHECKSUM:
        raise ValueError("v2.6.4 checksum contract changed")
    if value["expected_v2_6_10_checksum"] != EXPECTED_V2610_CHECKSUM:
        raise ValueError("v2.6.10 checksum contract changed")
    expected_policy = {
        "cohort_merge": False, "local_archive_payload_read": False,
        "metric_recomputation": False, "model_execution": False,
        "network_access": False, "provider_raw_bundle_download": False,
        "raw_archive_read": False,
    }
    if value["execution_policy"] != expected_policy:
        raise ValueError("execution policy changed")
    if value["credential_policy"] != {
        "network_access_required": False, "store_credentials": False
    }:
        raise ValueError("credential policy changed")
    paths = {
        "contract_path": DEFAULT_CONTRACT_PATH,
        "candidate_register_path": DEFAULT_REGISTER_PATH,
        "v2_6_4_external_cohort_admission_summary_path": DEFAULT_V264_PATH,
        "v2_6_10_snl_lfp_closeout_summary_path": DEFAULT_V2610_PATH,
        "output_root": DEFAULT_OUTPUT_ROOT,
        "tracked_summary_path": DEFAULT_TRACKED_SUMMARY,
    }
    for key, expected in paths.items():
        if _relative(key, value[key]) != expected:
            raise ValueError(f"{key} changed")
    if value["output_policy"] != "tracked_compact_summary_and_local_full_result":
        raise ValueError("output policy changed")
    if value["execution_mode"] != "verify" or value["dry_run"] is not False:
        raise ValueError("execution mode changed")
    return value


def _hard_gate(candidate: Mapping[str, Any]) -> bool:
    source = candidate["official_source_record"]
    return all((
        candidate["disposition"] == "selected_for_bounded_source_binding_only",
        source["stable_dataset_record"] is True,
        bool(source["dataset_doi"]),
        source["detailed_readme_declared"] is True,
        source["raw_cycler_data_declared"] is True,
        source["cell_tracker_declared"] is True,
        source["test_schedule_declared"] is True,
        source["source_code_declared"] is True,
    ))


def validate_register(value: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "register_id", "candidate_bundle_id", "retrieved_on",
        "candidate_count", "selection_question", "authoritative_source_policy",
        "candidates", "claim_policy",
    }
    if set(value) != required or value["schema_version"] != "1":
        raise ValueError("candidate register fields changed")
    if value["register_id"] != REGISTER_ID or value["candidate_count"] != 9:
        raise ValueError("candidate register identity changed")
    candidates = value["candidates"]
    if tuple(item.get("archive_name") for item in candidates) != CANDIDATE_ARCHIVES:
        raise ValueError("candidate archive set or order changed")
    if any(value["claim_policy"].values()):
        raise ValueError("candidate register claim policy was promoted")
    for item in candidates:
        inventory = item["local_inventory"]
        if inventory["entry_count"] != (
            inventory["cycle_file_count"] + inventory["timeseries_file_count"]
        ):
            raise ValueError("candidate inventory pair counts changed")
    if canonical_checksum(value) != EXPECTED_REGISTER_CHECKSUM:
        raise ValueError("candidate register checksum mismatch")


def validate_contract(value: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "contract_id", "contract_recorded_on",
        "candidate_bundle_id", "scientific_question", "upstream_identity",
        "hard_gate", "selection_policy", "next_authorized_scope",
        "stop_rules", "claim_policy",
    }
    if set(value) != required or value["schema_version"] != "1":
        raise ValueError("selection contract fields changed")
    if value["contract_id"] != CONTRACT_ID:
        raise ValueError("selection contract identity changed")
    if value["upstream_identity"] != {
        "candidate_register_checksum": EXPECTED_REGISTER_CHECKSUM,
        "v2_6_10_snl_lfp_closeout_checksum": EXPECTED_V2610_CHECKSUM,
        "v2_6_4_external_cohort_admission_checksum": EXPECTED_V264_CHECKSUM,
    }:
        raise ValueError("selection upstream identity changed")
    gate = value["hard_gate"]
    true_keys = (
        "stable_dataset_record_required", "dataset_doi_required",
        "detailed_readme_required", "raw_cycler_data_declaration_required",
        "cell_tracker_declaration_required", "test_schedule_declaration_required",
        "source_code_declaration_required",
    )
    if any(gate[key] is not True for key in true_keys):
        raise ValueError("hard-gate evidence requirements changed")
    if gate["required_disposition"] != "selected_for_bounded_source_binding_only":
        raise ValueError("hard-gate disposition changed")
    if gate["exact_local_archive_binding_required_for_selection"]:
        raise ValueError("selection was promoted to exact local binding")
    if gate["cross_cohort_admission_allowed"] or gate["predictive_validation_allowed"]:
        raise ValueError("admission boundary changed")
    policy = value["selection_policy"]
    if policy["selected_archive"] != SELECTED_ARCHIVE:
        raise ValueError("selected archive changed")
    if policy["selection_scope"] != "bounded_official_source_package_binding_only":
        raise ValueError("selection scope changed")
    if policy["weighted_score_allowed"] is not False:
        raise ValueError("weighted scoring is not allowed")
    for key in (
        "cross_cohort_admission_allowed", "raw_dataset_download_allowed",
        "local_archive_payload_read_allowed",
        "model_or_metric_execution_allowed",
    ):
        if policy[key] is not False:
            raise ValueError("selection execution boundary changed")
    if any(value["claim_policy"].values()):
        raise ValueError("selection claim policy was promoted")
    if canonical_checksum(value) != EXPECTED_CONTRACT_CHECKSUM:
        raise ValueError("selection contract checksum mismatch")


def verify_upstream(v264: Mapping[str, Any],
                    v2610: Mapping[str, Any]) -> dict[str, Any]:
    if v264.get("deterministic_result_checksum") != EXPECTED_V264_CHECKSUM:
        raise ValueError("v2.6.4 checksum mismatch")
    if canonical_checksum(v264) != EXPECTED_V264_CHECKSUM:
        raise ValueError("v2.6.4 content checksum mismatch")
    if v264.get("admission_decision", {}).get("overall_status") != (
        "not_admitted_for_cross_cohort_validation"
    ):
        raise ValueError("v2.6.4 admission boundary changed")
    if v2610.get("deterministic_result_checksum") != EXPECTED_V2610_CHECKSUM:
        raise ValueError("v2.6.10 checksum mismatch")
    if canonical_checksum(v2610) != EXPECTED_V2610_CHECKSUM:
        raise ValueError("v2.6.10 content checksum mismatch")
    decision = v2610.get("transition_artifact_decision", {})
    if decision.get("overall_status") != (
        "transition_artifact_consistency_recorded_gate_not_passed"
    ):
        raise ValueError("v2.6.10 closeout boundary changed")
    if decision.get("time_series_read_gate") != (
        "not_authorized_no_provider_step_or_command_binding"
    ):
        raise ValueError("v2.6.10 read gate changed")
    return {
        "model_or_metric_change_performed": False,
        "snl_lfp_evidence_line": "closed_at_diagnostic_boundary",
        "v2_6_10_checksum_verified": True,
        "v2_6_10_snl_lfp_status":
            "transition_artifact_consistency_recorded_gate_not_passed",
        "v2_6_4_checksum_verified": True,
        "v2_6_4_overall_status":
            "not_admitted_for_cross_cohort_validation",
    }


def assessments(register: Mapping[str, Any]) -> list[dict[str, Any]]:
    output = []
    for item in register["candidates"]:
        source = item["official_source_record"]
        output.append({
            "archive_name": item["archive_name"],
            "source_family": item["source_family"],
            "disposition": item["disposition"],
            "stable_dataset_record": source["stable_dataset_record"],
            "dataset_doi": source["dataset_doi"],
            "dataset_version": source["dataset_version"],
            "detailed_readme_declared": source["detailed_readme_declared"],
            "raw_cycler_data_declared": source["raw_cycler_data_declared"],
            "cell_tracker_declared": source["cell_tracker_declared"],
            "test_schedule_declared": source["test_schedule_declared"],
            "source_code_declared": source["source_code_declared"],
            "local_to_source_binding": item["local_to_source_binding"],
            "hard_gate_passed": _hard_gate(item),
            "blocking_field_reduction": item["blocking_field_reduction"],
            "rationale": item["rationale"],
        })
    return output


def build_result(config: Mapping[str, Any], contract: Mapping[str, Any],
                 register: Mapping[str, Any], v264: Mapping[str, Any],
                 v2610: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_register(register)
    candidate_rows = assessments(register)
    selected = [row["archive_name"] for row in candidate_rows
                if row["hard_gate_passed"]]
    if selected != [SELECTED_ARCHIVE]:
        raise ValueError("hard gate did not select exactly Michigan Formation.zip")
    dispositions = [row["disposition"] for row in candidate_rows]
    result: dict[str, Any] = {
        "schema_version": VERSION,
        "artifact_kind":
            "battery_external_cohort_next_source_selection_gate_result",
        "package_id": PACKAGE_ID,
        "case_study_id": config["case_study_id"],
        "candidate_bundle_id": config["candidate_bundle_id"],
        "contract_id": CONTRACT_ID,
        "contract_checksum": canonical_checksum(contract),
        "candidate_register_id": REGISTER_ID,
        "candidate_register_checksum": canonical_checksum(register),
        "upstream_checks": verify_upstream(v264, v2610),
        "candidate_summary": {
            "candidate_count": len(candidate_rows),
            "selected_count":
                dispositions.count("selected_for_bounded_source_binding_only"),
            "reserve_count":
                sum(value.startswith("reserve_") for value in dispositions),
            "closed_count":
                sum(value.startswith("closed_") for value in dispositions),
            "hold_count":
                sum(value.startswith("hold_") for value in dispositions),
            "hard_gate_pass_count": len(selected),
        },
        "candidate_assessments": candidate_rows,
        "selection_decision": {
            "selected_archive": SELECTED_ARCHIVE,
            "selected_source_family": "University of Michigan Fast Formation",
            "selection_status": "selected_for_bounded_source_binding_only",
            "selection_basis":
                "official dataset DOI plus provider-declared README, raw Maccor "
                "data, cell trackers, test schedules, and source code",
            "local_archive_to_official_dataset_binding": "not_established",
            "provider_package_to_cycle_row_binding": "not_established",
            "cross_cohort_comparability": "not_admitted",
            "predictive_validation": "blocked",
            "raw_dataset_download": "not_authorized",
            "local_archive_payload_read": "not_authorized",
            "overall_status":
                "next_source_candidate_selected_gate_not_passed",
        },
        "next_authorized_scope": contract["next_authorized_scope"],
        "scientific_closeout": {
            "status": "diagnostic",
            "result":
                "michigan_formation_selected_for_bounded_source_binding_only",
            "evidence_level":
                "official_provider_dataset_record_with_declared_metadata_and_"
                "schedule_artifacts_without_local_archive_binding",
            "strongest_evidence":
                "The University of Michigan Deep Blue record identifies a stable "
                "dataset DOI and declares a detailed README, raw Maccor data, cell "
                "tracker files, test schedules, source code, cell chemistry, nominal "
                "capacity, formation groups, and cycling temperatures.",
            "primary_limitation":
                "No checksum or filename map yet binds the local Michigan "
                "Formation.zip entries to the provider package, and no provider "
                "schedule is bound to standardized CSV cycles or rows.",
            "suitable_for": [
                "bounded provider metadata inventory",
                "source-package-to-local-archive binding design",
                "test-schedule provenance review",
            ],
            "unsuitable_for": [
                "raw data analysis", "cross-cohort equivalence",
                "target harmonization", "predictive validation",
                "model training or evaluation",
                "mechanism or engineering claims",
            ],
            "what_would_change_conclusion": [
                "provider file inventory and stable file identities",
                "cell tracker schema and local cell-ID mapping",
                "test schedule schema and command semantics",
                "documented conversion path from provider raw files to Battery "
                "Archive standardized CSVs",
                "prospective target and comparability contracts",
            ],
        },
        "recommendations": [
            "close the SNL LFP payload-expansion path at its diagnostic boundary",
            "perform a bounded Michigan Formation provider metadata and schedule "
            "inventory without downloading the raw 2.37 GB data bundle",
            "do not infer local file binding from the archive name alone",
            "do not admit, merge, train, or evaluate until source binding and "
            "comparability are prospectively passed",
        ],
        "source_references": {
            "v2_6_4_summary": DEFAULT_V264_PATH,
            "v2_6_10_summary": DEFAULT_V2610_PATH,
            "candidate_register": DEFAULT_REGISTER_PATH,
            "contract": DEFAULT_CONTRACT_PATH,
            "battery_archive_inventory": "docs/BATTERY_ARCHIVE_DATA_AUDIT.md",
            "battery_archive_studies":
                "https://batteryarchive.org/study_summaries.html",
            "michigan_formation_provider_record":
                "https://deepblue.lib.umich.edu/data/concern/data_sets/b2773w109",
            "oxford_provider_record":
                "https://ora.ox.ac.uk/objects/"
                "uuid:03ba4b01-cfed-46d3-9b1a-7d4a7bdf6fac",
            "michigan_expansion_provider_record":
                "https://deepblue.lib.umich.edu/data/concern/data_sets/5d86p0488",
        },
    }
    for flag in FALSE_FLAGS:
        result[flag] = False
    result["deterministic_result_checksum"] = canonical_checksum(result)
    return result


def compact(result: Mapping[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(dict(result))
    output["artifact_kind"] = (
        "battery_external_cohort_next_source_selection_gate_compact_summary"
    )
    output["candidate_assessments"] = [
        {key: row[key] for key in COMPACT_ASSESSMENT_KEYS}
        for row in result["candidate_assessments"]
    ]
    output["deterministic_result_checksum"] = canonical_checksum(output)
    return output


def validate_result(value: Mapping[str, Any]) -> None:
    if value.get("schema_version") != VERSION or value.get("package_id") != PACKAGE_ID:
        raise ValueError("unsupported selection result")
    if value.get("contract_checksum") != EXPECTED_CONTRACT_CHECKSUM:
        raise ValueError("selection contract checksum changed")
    if value.get("candidate_register_checksum") != EXPECTED_REGISTER_CHECKSUM:
        raise ValueError("candidate register checksum changed")
    decision = value.get("selection_decision", {})
    expected = {
        "selected_archive": SELECTED_ARCHIVE,
        "selection_status": "selected_for_bounded_source_binding_only",
        "local_archive_to_official_dataset_binding": "not_established",
        "provider_package_to_cycle_row_binding": "not_established",
        "cross_cohort_comparability": "not_admitted",
        "predictive_validation": "blocked",
        "raw_dataset_download": "not_authorized",
        "local_archive_payload_read": "not_authorized",
        "overall_status": "next_source_candidate_selected_gate_not_passed",
    }
    for key, expected_value in expected.items():
        if decision.get(key) != expected_value:
            raise ValueError(f"selection boundary changed: {key}")
    if value.get("candidate_summary") != {
        "candidate_count": 9, "selected_count": 1, "reserve_count": 1,
        "closed_count": 1, "hold_count": 6, "hard_gate_pass_count": 1,
    }:
        raise ValueError("candidate summary changed")
    rows = value.get("candidate_assessments", [])
    if [row.get("archive_name") for row in rows] != list(CANDIDATE_ARCHIVES):
        raise ValueError("candidate assessments changed")
    if [row.get("archive_name") for row in rows if row.get("hard_gate_passed")] != [
        SELECTED_ARCHIVE
    ]:
        raise ValueError("hard-gate selection changed")
    if value.get("upstream_checks", {}).get("snl_lfp_evidence_line") != (
        "closed_at_diagnostic_boundary"
    ):
        raise ValueError("SNL LFP evidence line was reopened")
    if any(value.get(flag) is not False for flag in FALSE_FLAGS):
        raise ValueError("prohibited execution flag changed")
    if value.get("deterministic_result_checksum") != canonical_checksum(value):
        raise ValueError("deterministic result checksum mismatch")


def execute(config: Mapping[str, Any], repo_root: str | Path = ".",
            write_outputs: bool = True) -> dict[str, Any]:
    contract = _json(repo_path(repo_root, config["contract_path"]))
    register = _json(repo_path(repo_root, config["candidate_register_path"]))
    v264 = _json(repo_path(
        repo_root, config["v2_6_4_external_cohort_admission_summary_path"]
    ))
    v2610 = _json(repo_path(
        repo_root, config["v2_6_10_snl_lfp_closeout_summary_path"]
    ))
    result = build_result(config, contract, register, v264, v2610)
    validate_result(result)
    if write_outputs:
        root = repo_path(repo_root, config["output_root"])
        root.mkdir(parents=True, exist_ok=True)
        (root / "next_source_selection_result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tracked = compact(result)
        validate_result(tracked)
        path = repo_path(repo_root, config["tracked_summary_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(tracked, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return result


def preview(config: Mapping[str, Any],
            repo_root: str | Path = ".") -> dict[str, Any]:
    contract = _json(repo_path(repo_root, config["contract_path"]))
    register = _json(repo_path(repo_root, config["candidate_register_path"]))
    validate_contract(contract)
    validate_register(register)
    selected = [row["archive_name"] for row in assessments(register)
                if row["hard_gate_passed"]]
    return {
        "schema_version": VERSION, "package_id": PACKAGE_ID,
        "candidate_count": 9, "selected_candidates": selected,
        "selection_scope": "bounded_official_source_package_binding_only",
        "network_access": False, "raw_dataset_download": False,
        "local_archive_payload_read": False, "model_execution": False,
        "write_outputs": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preview")
    sub.add_parser("run")
    validator = sub.add_parser("validate")
    validator.add_argument("result_path")
    args = parser.parse_args(argv)
    config = load_config(args.config, args.repo_root)
    if args.command == "preview":
        value = preview(config, args.repo_root)
    elif args.command == "run":
        value = execute(config, args.repo_root, True)
    else:
        value = _json(repo_path(args.repo_root, args.result_path))
        validate_result(value)
        value = {
            "valid": True,
            "deterministic_result_checksum":
                value["deterministic_result_checksum"],
        }
    print(json.dumps(value, ensure_ascii=False, sort_keys=True)
          if args.json else
          json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
