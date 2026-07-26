from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

VERSION = "2.6.10"
PACKAGE_ID = "battery_snl_lfp_transition_artifact_evidence_gate_v1"
CONTRACT_ID = "battery_snl_lfp_transition_artifact_evidence_contract_v1"
DEFAULT_CONFIG_PATH = "configs/examples/battery_snl_lfp_transition_artifact_evidence_gate.json"
DEFAULT_CONTRACT_PATH = "data/platform/battery_snl_lfp_transition_artifact_evidence_contract_v1.json"
DEFAULT_OUTPUT_ROOT = "outputs/v2_6_battery_snl_lfp_transition_artifact_evidence"
DEFAULT_TRACKED_SUMMARY = "data/processed/battery_v2_6_10_snl_lfp_transition_artifact_evidence_summary.json"
V265_SUMMARY_PATH = "data/processed/battery_v2_6_5_snl_lfp_source_evidence_summary.json"
V269_SUMMARY_PATH = "data/processed/battery_v2_6_9_snl_lfp_bounded_cycle_regime_summary.json"
EXPECTED_V265_CHECKSUM = "b6e0c950f11cb1edfbd3afdd15776af25c76b092d130d6038b6653ecd63ba846"
EXPECTED_V269_CHECKSUM = "dc6c7c4046d81ddf879c2f1538eab75708dd387f7d9d940adc0c6dfc2c3e01dc"
EXPECTED_ARCHIVE_SHA256 = "006a335cbcdabc858a85ab0cdbc59a7001150751cf22abe8a7132c85ef63223d"
REPRESENTATIVE_ENTRIES = (
    "SNL LFP/SNL_18650_LFP_25C_0-100_0.5-1C_a_cycle_data.csv",
    "SNL LFP/SNL_18650_LFP_25C_20-80_0.5-0.5C_a_cycle_data.csv",
    "SNL LFP/SNL_18650_LFP_25C_40-60_0.5-0.5C_a_cycle_data.csv",
)
AUDIT_FIELDS = (
    "min_current_a", "max_current_a", "min_voltage_v", "max_voltage_v",
    "charge_capacity_ah", "discharge_capacity_ah",
)
FALSE_FLAGS = (
    "network_called", "credentials_read", "archive_read", "csv_payload_read",
    "time_series_entry_read", "threshold_inference_performed",
    "row_classification_promoted", "cycle_command_binding_inferred",
    "step_identity_inferred", "instrument_channel_binding_inferred",
    "physical_cell_binding_inferred", "official_snapshot_inferred",
    "cohort_merge_performed", "model_trained", "model_evaluated",
    "metrics_recomputed", "source_mutation_performed",
)


def canonical_checksum(payload: Mapping[str, Any]) -> str:
    core = dict(payload)
    core.pop("deterministic_result_checksum", None)
    text = json.dumps(
        core, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    )
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


def load_config(
    path: str | Path = DEFAULT_CONFIG_PATH,
    repo_root: str | Path = ".",
) -> dict[str, Any]:
    payload = _json(repo_path(repo_root, path))
    required = {
        "schema_version", "package_id", "case_study_id", "bounded_source_id",
        "contract_path", "v2_6_5_source_evidence_summary_path",
        "v2_6_9_cycle_regime_summary_path", "expected_v2_6_5_checksum",
        "expected_v2_6_9_checksum", "execution_policy", "credential_policy",
        "output_root", "tracked_summary_path", "output_policy", "dry_run",
    }
    if set(payload) != required:
        raise ValueError("config fields changed")
    if payload["schema_version"] != VERSION or payload["package_id"] != PACKAGE_ID:
        raise ValueError("unsupported transition-artifact evidence package")
    if payload["bounded_source_id"] != "snl_lfp_commercial_18650_study":
        raise ValueError("bounded source changed")
    if payload["expected_v2_6_5_checksum"] != EXPECTED_V265_CHECKSUM:
        raise ValueError("v2.6.5 checksum contract changed")
    if payload["expected_v2_6_9_checksum"] != EXPECTED_V269_CHECKSUM:
        raise ValueError("v2.6.9 checksum contract changed")
    if payload["execution_policy"] != {
        "archive_read": False, "csv_payload_read": False,
        "metric_recomputation": False, "model_execution": False,
        "network_access": False, "threshold_fitting": False,
        "time_series_read": False,
    }:
        raise ValueError("execution policy changed")
    if payload["credential_policy"] != {
        "network_access_required": False, "store_credentials": False,
    }:
        raise ValueError("credential policy changed")
    checks = {
        "contract_path": DEFAULT_CONTRACT_PATH,
        "v2_6_5_source_evidence_summary_path": V265_SUMMARY_PATH,
        "v2_6_9_cycle_regime_summary_path": V269_SUMMARY_PATH,
        "output_root": DEFAULT_OUTPUT_ROOT,
        "tracked_summary_path": DEFAULT_TRACKED_SUMMARY,
    }
    for key, expected in checks.items():
        if _relative(key, payload[key]) != expected:
            raise ValueError(f"{key} changed")
    if payload["output_policy"] != "tracked_compact_summary_and_local_full_result":
        raise ValueError("output policy changed")
    if payload["dry_run"] is not False:
        raise ValueError("evidence gate is not a dry run")
    return payload


def validate_contract(contract: Mapping[str, Any], config: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "contract_id", "bounded_source_id",
        "contract_recorded_on", "scientific_question", "upstream_identity",
        "source_evidence", "representative_scope", "decision_policy",
        "claim_policy", "stop_rules",
    }
    if set(contract) != required:
        raise ValueError("transition-evidence contract fields changed")
    if contract["schema_version"] != "1" or contract["contract_id"] != CONTRACT_ID:
        raise ValueError("unsupported transition-evidence contract")
    if contract["bounded_source_id"] != config["bounded_source_id"]:
        raise ValueError("contract bounded source changed")
    if contract["upstream_identity"] != {
        "archive_sha256": EXPECTED_ARCHIVE_SHA256,
        "v2_6_5_source_evidence_checksum": EXPECTED_V265_CHECKSUM,
        "v2_6_9_cycle_regime_checksum": EXPECTED_V269_CHECKSUM,
    }:
        raise ValueError("upstream identity contract changed")
    source = contract["source_evidence"]
    if source["document_id"] != "battery_archive_snl_study_page":
        raise ValueError("source document changed")
    if source["url"] != "https://www.batteryarchive.org/snl_study.html":
        raise ValueError("source URL changed")
    if source["evidence_scope"] != "study_level_transition_artifact":
        raise ValueError("source evidence scope changed")
    if source["versioned_page_snapshot"] or source["local_document_copy_committed"]:
        raise ValueError("source page may not be promoted to a snapshot")
    scope = contract["representative_scope"]
    if tuple(scope["entries"]) != REPRESENTATIVE_ENTRIES:
        raise ValueError("representative entries changed")
    if scope["row4_position"] != 4 or scope["comparison_positions"] != [5, 6, 7, 8]:
        raise ValueError("transition-row positions changed")
    if tuple(scope["audit_fields"]) != AUDIT_FIELDS:
        raise ValueError("audit fields changed")
    if scope["method"] != "exact_decimal_row4_against_positions_5_to_8_ranges":
        raise ValueError("transition audit method changed")
    policy = contract["decision_policy"]
    if policy != {
        "all_representatives_must_have_row4_outside_at_least_one_comparison_range": True,
        "allowed_consistency_status": "transition_consistent_not_row_bound",
        "capacity_check_labels_may_be_promoted": False,
        "document_transition_artifact_note_required": True,
        "exact_row_identity_may_be_established": False,
        "threshold_fitting_allowed": False,
        "time_series_read_may_be_authorized": False,
    }:
        raise ValueError("decision policy changed")
    if any(contract["claim_policy"].values()):
        raise ValueError("claim policy may not promote transition evidence")


def verify_upstream(
    v265: Mapping[str, Any],
    v269: Mapping[str, Any],
) -> dict[str, Any]:
    if v265.get("deterministic_result_checksum") != EXPECTED_V265_CHECKSUM:
        raise ValueError("v2.6.5 checksum mismatch")
    if canonical_checksum(v265) != EXPECTED_V265_CHECKSUM:
        raise ValueError("v2.6.5 content checksum mismatch")
    if v265.get("recovery_decision", {}).get("overall_status") != (
        "source_evidence_recovered_gate_not_passed"
    ):
        raise ValueError("v2.6.5 source boundary changed")
    if v269.get("deterministic_result_checksum") != EXPECTED_V269_CHECKSUM:
        raise ValueError("v2.6.9 checksum mismatch")
    if canonical_checksum(v269) != EXPECTED_V269_CHECKSUM:
        raise ValueError("v2.6.9 content checksum mismatch")
    decision = v269.get("cycle_regime_decision", {})
    if decision.get("capacity_check_vs_bulk_cycle_discrimination") != (
        "candidate_supported_not_established"
    ):
        raise ValueError("v2.6.9 candidate boundary changed")
    if decision.get("overall_status") != (
        "bounded_cycle_regime_evidence_recorded_gate_not_passed"
    ):
        raise ValueError("v2.6.9 overall boundary changed")
    return {
        "archive_sha256_preserved": True,
        "model_or_metric_change_performed": False,
        "v2_6_5_checksum_verified": True,
        "v2_6_9_candidate_status_preserved": True,
        "v2_6_9_checksum_verified": True,
    }


def _decimal(value: Any, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be an exact decimal string") from exc
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    return number


def audit_row4(observation: Mapping[str, Any]) -> dict[str, Any]:
    rows = observation.get("selected_cycle_rows", [])
    if len(rows) != 8:
        raise ValueError("v2.6.9 must contain exactly eight selected rows")
    for position, row in enumerate(rows, start=1):
        if row.get("row_position") != position:
            raise ValueError("v2.6.9 row positions changed")
        if row.get("candidate_assignment_promoted") is not False:
            raise ValueError("v2.6.9 candidate assignment was promoted")
    row4 = rows[3]["selected_values"]
    comparison = rows[4:8]
    field_audits: list[dict[str, Any]] = []
    outside_fields: list[str] = []
    for field in AUDIT_FIELDS:
        row4_text = str(row4[field])
        row4_value = _decimal(row4_text, field)
        values = [_decimal(row["selected_values"][field], field) for row in comparison]
        minimum, maximum = min(values), max(values)
        outside = row4_value < minimum or row4_value > maximum
        if outside:
            outside_fields.append(field)
        field_audits.append({
            "direction": (
                "below" if row4_value < minimum
                else "above" if row4_value > maximum
                else "within"
            ),
            "field": field,
            "positions_5_to_8_range": {
                "maximum": format(maximum, "f"),
                "minimum": format(minimum, "f"),
            },
            "row4_outside_positions_5_to_8_range": outside,
            "row4_value": row4_text,
        })
    return {
        "audit_status": (
            "row4_transition_contrast_observed"
            if outside_fields else "row4_no_transition_contrast_observed"
        ),
        "comparison_positions": [5, 6, 7, 8],
        "entry_name": observation["entry_name"],
        "field_audits": field_audits,
        "method": "exact_decimal_row4_against_positions_5_to_8_ranges",
        "outside_range_field_count": len(outside_fields),
        "outside_range_fields": outside_fields,
        "protocol_family": observation["protocol_family"],
        "row4_identity_promoted": False,
        "row4_position": 4,
        "threshold_fitted_or_inferred": False,
    }


def build_result(
    config: Mapping[str, Any],
    contract: Mapping[str, Any],
    v265: Mapping[str, Any],
    v269: Mapping[str, Any],
) -> dict[str, Any]:
    validate_contract(contract, config)
    preservation = verify_upstream(v265, v269)
    observations = v269.get("file_observations", [])
    if tuple(item.get("entry_name") for item in observations) != REPRESENTATIVE_ENTRIES:
        raise ValueError("v2.6.9 representative observation set changed")
    audits = [audit_row4(item) for item in observations]
    observed = sum(
        item["audit_status"] == "row4_transition_contrast_observed"
        for item in audits
    )
    all_observed = observed == 3
    common_fields = sorted(set(audits[0]["outside_range_fields"]).intersection(
        *(set(item["outside_range_fields"]) for item in audits[1:])
    ))
    result: dict[str, Any] = {
        "artifact_kind": "battery_snl_lfp_transition_artifact_evidence_gate_result",
        "bounded_source_id": config["bounded_source_id"],
        "case_study_id": config["case_study_id"],
        "contract_checksum": canonical_checksum(contract),
        "contract_id": CONTRACT_ID,
        "package_id": PACKAGE_ID,
        "preservation_checks": preservation,
        "recommendations": [
            "do not expand to time-series solely to label row 4",
            "require provider-issued conversion mapping, step metadata, or command logs before exact row classification",
            "if no provider-backed row mapping exists, retain the diagnostic boundary and close this evidence path",
            "do not merge cohorts or execute predictive validation",
        ],
        "row4_transition_audits": audits,
        "schema_version": VERSION,
        "scientific_closeout": {
            "evidence_level": "official_study_artifact_note_plus_checksum_bound_row4_contrasts_in_three_representatives",
            "primary_limitation": "The source note is study-level and does not identify an exact CSV row, conversion boundary, step command, or instrument channel; row 4 remains transition-consistent rather than confirmed.",
            "result": (
                "source_transition_artifact_consistent_with_row4_pattern_not_row_bound"
                if all_observed else "source_transition_artifact_not_consistently_observed"
            ),
            "status": "diagnostic" if all_observed else "inconclusive",
            "strongest_evidence": "The official Battery Archive study page attributes periodic spikes to transitions between the three-cycle capacity check and normal cycling, while row 4 lies outside the positions 5-8 range in selected measurements for all three representatives.",
            "suitable_for": [
                "transition-artifact provenance closeout",
                "bounded row-identity limitation assessment",
                "decision not to expand payload reads without provider metadata",
            ],
            "unsuitable_for": [
                "confirmed capacity-check labels", "row4 command or step identity",
                "universal cycle classifier", "time-series command reconstruction",
                "cross-cohort comparison", "model evaluation", "engineering decisions",
            ],
        },
        "source_evidence_audit": {
            "document_id": "battery_archive_snl_study_page",
            "documented_scope": "study_level_transition_between_capacity_check_and_normal_cycling",
            "documented_transition_artifact": True,
            "exact_csv_row_binding_established": False,
            "publisher": "Battery Archive",
            "retrieved_on": "2026-07-26",
            "status": "official_transition_artifact_note_recovered",
            "url": "https://www.batteryarchive.org/snl_study.html",
            "versioned_page_snapshot": False,
        },
        "source_references": {
            "contract": config["contract_path"],
            "v2_6_5_summary": config["v2_6_5_source_evidence_summary_path"],
            "v2_6_9_summary": config["v2_6_9_cycle_regime_summary_path"],
        },
        "transition_artifact_decision": {
            "capacity_check_vs_bulk_cycle_discrimination": "candidate_supported_not_established",
            "cross_cohort_comparability": "not_admitted",
            "cycle_command_to_rows": "not_established",
            "instrument_channel_to_columns": "not_established",
            "official_distribution_snapshot": "not_established",
            "official_transition_artifact_evidence": "recovered_document_level",
            "overall_status": (
                "transition_artifact_consistency_recorded_gate_not_passed"
                if all_observed
                else "transition_artifact_consistency_not_supported_gate_not_passed"
            ),
            "physical_cell_to_entry": "not_established",
            "predictive_validation": "blocked",
            "row4_exact_identity": "not_established",
            "row4_to_source_transition_binding": (
                "transition_consistent_not_row_bound"
                if all_observed else "transition_consistency_not_supported"
            ),
            "row4_transition_pattern": (
                "observed_all_representatives"
                if all_observed else "not_observed_all_representatives"
            ),
            "step_level_discrimination": "not_available_no_step_identifier",
            "time_series_read_gate": "not_authorized_no_provider_step_or_command_binding",
        },
        "transition_summary": {
            "all_representatives_have_row4_contrast": all_observed,
            "common_outside_range_fields": common_fields,
            "positions_4_to_8_homogeneous_bulk_regime_established": False,
            "representative_entry_count": 3,
            "row4_contrast_observed_count": observed,
            "universal_numeric_threshold_defined": False,
        },
    }
    for flag in FALSE_FLAGS:
        result[flag] = False
    result["deterministic_result_checksum"] = canonical_checksum(result)
    return result


def compact(result: Mapping[str, Any]) -> dict[str, Any]:
    output = dict(result)
    output["artifact_kind"] = "battery_snl_lfp_transition_artifact_evidence_gate_compact_summary"
    output["deterministic_result_checksum"] = canonical_checksum(output)
    return output


def validate_result(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != VERSION or payload.get("package_id") != PACKAGE_ID:
        raise ValueError("unsupported result")
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("contract id changed")
    if any(payload.get(flag) is not False for flag in FALSE_FLAGS):
        raise ValueError("prohibited execution flag changed")
    decision = payload.get("transition_artifact_decision", {})
    required = {
        "capacity_check_vs_bulk_cycle_discrimination": "candidate_supported_not_established",
        "cross_cohort_comparability": "not_admitted",
        "cycle_command_to_rows": "not_established",
        "instrument_channel_to_columns": "not_established",
        "official_distribution_snapshot": "not_established",
        "physical_cell_to_entry": "not_established",
        "predictive_validation": "blocked",
        "row4_exact_identity": "not_established",
        "step_level_discrimination": "not_available_no_step_identifier",
        "time_series_read_gate": "not_authorized_no_provider_step_or_command_binding",
    }
    for key, expected in required.items():
        if decision.get(key) != expected:
            raise ValueError(f"scientific boundary changed: {key}")
    if decision.get("row4_to_source_transition_binding") not in {
        "transition_consistent_not_row_bound", "transition_consistency_not_supported",
    }:
        raise ValueError("row4 transition evidence was promoted")
    audits = payload.get("row4_transition_audits", [])
    if tuple(item.get("entry_name") for item in audits) != REPRESENTATIVE_ENTRIES:
        raise ValueError("row4 audit representative set changed")
    for item in audits:
        if item.get("row4_position") != 4 or item.get("comparison_positions") != [5, 6, 7, 8]:
            raise ValueError("row4 audit positions changed")
        if item.get("threshold_fitted_or_inferred") is not False:
            raise ValueError("threshold was fitted or inferred")
        if item.get("row4_identity_promoted") is not False:
            raise ValueError("row4 identity was promoted")
        fields = item.get("field_audits", [])
        if tuple(field.get("field") for field in fields) != AUDIT_FIELDS:
            raise ValueError("row4 audit field set changed")
        for field in fields:
            _decimal(field["row4_value"], field["field"])
            _decimal(field["positions_5_to_8_range"]["minimum"], field["field"])
            _decimal(field["positions_5_to_8_range"]["maximum"], field["field"])
    if payload.get("deterministic_result_checksum") != canonical_checksum(payload):
        raise ValueError("deterministic result checksum mismatch")


def execute(
    config: Mapping[str, Any],
    repo_root: str | Path = ".",
    write_outputs: bool = True,
) -> dict[str, Any]:
    contract = _json(repo_path(repo_root, config["contract_path"]))
    v265 = _json(repo_path(repo_root, config["v2_6_5_source_evidence_summary_path"]))
    v269 = _json(repo_path(repo_root, config["v2_6_9_cycle_regime_summary_path"]))
    result = build_result(config, contract, v265, v269)
    validate_result(result)
    if write_outputs:
        output_root = repo_path(repo_root, config["output_root"])
        output_root.mkdir(parents=True, exist_ok=True)
        (output_root / "transition_artifact_evidence_result.json").write_text(
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


def preview(config: Mapping[str, Any], repo_root: str | Path = ".") -> dict[str, Any]:
    contract = _json(repo_path(repo_root, config["contract_path"]))
    validate_contract(contract, config)
    return {
        "allowed_reads": [
            "tracked v2.6.5 source-evidence summary",
            "tracked v2.6.9 cycle-regime summary",
            "tracked transition-artifact evidence contract",
        ],
        "audit_fields": list(AUDIT_FIELDS),
        "bounded_source_id": config["bounded_source_id"],
        "comparison_positions": [5, 6, 7, 8],
        "package_id": PACKAGE_ID,
        "prohibited_reads": [
            "raw archive bytes", "CSV payloads", "time-series entries",
            "network", "credentials",
        ],
        "representative_entries": list(REPRESENTATIVE_ENTRIES),
        "row4_position": 4,
        "schema_version": VERSION,
        "source_document_id": "battery_archive_snl_study_page",
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
            "deterministic_result_checksum": value["deterministic_result_checksum"],
            "valid": True,
        }
    print(
        json.dumps(value, ensure_ascii=False, sort_keys=True)
        if args.json
        else json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
