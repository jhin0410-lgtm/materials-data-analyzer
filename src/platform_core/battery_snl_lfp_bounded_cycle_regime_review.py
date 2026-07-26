from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
import zipfile

from src.platform_core._battery_snl_lfp_cycle_regime_io import (
    BULK_CANDIDATE_ROWS,
    CAPACITY_CHECK_CANDIDATE_ROWS,
    CONTRAST_FIELDS,
    CONTROL_CONTRAST_FIELDS,
    EXPECTED_CYCLE_HEADER_CHECKSUM,
    MAX_LINE_BYTES,
    MAX_ROWS,
    SELECTED_COLUMNS,
    canonical_checksum,
    decimal_value,
    failure_observation,
    read_cycle_sample,
    safe_entry_name,
    sha256_file,
)

VERSION = "2.6.9"
PACKAGE_ID = "battery_snl_lfp_bounded_cycle_regime_review_v1"
DEFAULT_CONFIG_PATH = "configs/battery_snl_lfp_bounded_cycle_regime_review.json"
DEFAULT_CONTRACT_PATH = "data/platform/battery_snl_lfp_bounded_cycle_regime_contract_v1.json"
DEFAULT_OUTPUT_ROOT = "outputs/v2_6_battery_snl_lfp_bounded_cycle_regime"
DEFAULT_TRACKED_SUMMARY = "data/processed/battery_v2_6_9_snl_lfp_bounded_cycle_regime_summary.json"
EXPECTED_ARCHIVE_PATH = "data/raw/battery_archive/SNL LFP.zip"
EXPECTED_ARCHIVE_SHA256 = "006a335cbcdabc858a85ab0cdbc59a7001150751cf22abe8a7132c85ef63223d"
EXPECTED_V268_CHECKSUM = "28c68acecdce55787189ddd981c097d1748504dab43b3777b896638652fb70f2"
REPRESENTATIVE_ENTRIES = (
    "SNL LFP/SNL_18650_LFP_25C_0-100_0.5-1C_a_cycle_data.csv",
    "SNL LFP/SNL_18650_LFP_25C_20-80_0.5-0.5C_a_cycle_data.csv",
    "SNL LFP/SNL_18650_LFP_25C_40-60_0.5-0.5C_a_cycle_data.csv",
)
FALSE_FLAGS = (
    "archive_extracted",
    "nonrepresentative_entry_read",
    "time_series_entry_read",
    "full_csv_read",
    "network_called",
    "credentials_read",
    "source_mutation_performed",
    "cohort_merge_performed",
    "model_trained",
    "model_evaluated",
    "metrics_recomputed",
    "physical_cell_binding_inferred",
    "cycle_command_binding_inferred",
    "instrument_channel_binding_inferred",
    "capacity_check_classification_promoted",
    "unit_conversion_performed",
    "data_imputation_performed",
    "row_exclusion_performed",
    "threshold_inference_performed",
    "unselected_raw_fields_retained",
)


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


@dataclass(frozen=True)
class CycleRegimeConfig:
    case_study_id: str
    bounded_source_id: str
    contract_path: str
    v2_6_8_summary_path: str
    archive_path: str
    output_root: str
    tracked_summary_path: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CycleRegimeConfig":
        required = {
            "schema_version", "package_id", "case_study_id", "bounded_source_id",
            "cycle_regime_contract_path", "v2_6_8_bounded_schema_summary_path",
            "expected_v2_6_8_checksum", "archive_path", "expected_archive_sha256",
            "representative_entries", "cycle_row_policy", "read_policy",
            "credential_policy", "output_root", "tracked_summary_path",
            "output_policy", "execution_mode", "dry_run",
        }
        if set(payload) != required:
            raise ValueError("config fields changed")
        if payload["schema_version"] != VERSION or payload["package_id"] != PACKAGE_ID:
            raise ValueError("unsupported bounded cycle-regime package")
        if payload["bounded_source_id"] != "snl_lfp_commercial_18650_study":
            raise ValueError("bounded source changed")
        if payload["expected_v2_6_8_checksum"] != EXPECTED_V268_CHECKSUM:
            raise ValueError("v2.6.8 checksum contract changed")
        if payload["expected_archive_sha256"] != EXPECTED_ARCHIVE_SHA256:
            raise ValueError("archive checksum contract changed")
        if tuple(payload["representative_entries"]) != REPRESENTATIVE_ENTRIES:
            raise ValueError("representative entry set changed")
        if payload["cycle_row_policy"] != {
            "capacity_check_candidate_row_count": CAPACITY_CHECK_CANDIDATE_ROWS,
            "bulk_candidate_row_count": BULK_CANDIDATE_ROWS,
            "max_data_rows_per_entry": MAX_ROWS,
            "max_line_bytes": MAX_LINE_BYTES,
            "retain_only_selected_measurement_fields": True,
            "preserve_exact_decimal_strings": True,
        }:
            raise ValueError("cycle-row policy changed")
        if payload["read_policy"] != {
            "allow_tracked_json_reads": True,
            "allow_archive_sha256": True,
            "allow_zip_central_directory": True,
            "allow_representative_cycle_entry_payload_read": True,
            "allow_csv_header_read": True,
            "allow_first_eight_cycle_rows": True,
            "allow_time_series_entry_read": False,
            "allow_nonrepresentative_entry_read": False,
            "allow_full_csv_read": False,
            "allow_archive_extraction": False,
        }:
            raise ValueError("read policy changed")
        if payload["credential_policy"] != {
            "store_credentials": False,
            "network_access_required": False,
        }:
            raise ValueError("credential policy changed")
        if payload["output_policy"] != "local_full_result_and_tracked_compact_summary":
            raise ValueError("output policy changed")
        if payload["execution_mode"] != "bounded_local_cycle_regime_review":
            raise ValueError("execution mode changed")
        if payload["dry_run"] is not False:
            raise ValueError("bounded cycle-regime review is not a dry run")

        contract = _relative("cycle_regime_contract_path", payload["cycle_regime_contract_path"])
        v268 = _relative(
            "v2_6_8_bounded_schema_summary_path",
            payload["v2_6_8_bounded_schema_summary_path"],
        )
        archive = _relative("archive_path", payload["archive_path"])
        output = _relative("output_root", payload["output_root"])
        tracked = _relative("tracked_summary_path", payload["tracked_summary_path"])
        if contract != DEFAULT_CONTRACT_PATH:
            raise ValueError("contract path changed")
        if archive != EXPECTED_ARCHIVE_PATH:
            raise ValueError("archive path changed")
        if output != DEFAULT_OUTPUT_ROOT or tracked != DEFAULT_TRACKED_SUMMARY:
            raise ValueError("output paths changed")
        return cls(
            case_study_id=str(payload["case_study_id"]),
            bounded_source_id=str(payload["bounded_source_id"]),
            contract_path=contract,
            v2_6_8_summary_path=v268,
            archive_path=archive,
            output_root=output,
            tracked_summary_path=tracked,
        )


def load_config(
    path: str | Path = DEFAULT_CONFIG_PATH,
    repo_root: str | Path = ".",
) -> CycleRegimeConfig:
    return CycleRegimeConfig.from_dict(_json(repo_path(repo_root, path)))


def validate_contract(contract: Mapping[str, Any], config: CycleRegimeConfig) -> None:
    required = {
        "schema_version", "contract_id", "bounded_source_id",
        "contract_recorded_on", "scientific_question", "source_sequence_basis",
        "archive_identity", "representative_selection", "representative_entries",
        "selected_measurement_fields", "candidate_assignment", "contrast_policy",
        "stop_rules", "claim_policy",
    }
    if set(contract) != required:
        raise ValueError("cycle-regime contract fields changed")
    if contract["schema_version"] != "1":
        raise ValueError("unsupported cycle-regime contract")
    if contract["contract_id"] != "battery_snl_lfp_bounded_cycle_regime_contract_v1":
        raise ValueError("contract id changed")
    if contract["bounded_source_id"] != config.bounded_source_id:
        raise ValueError("contract bounded source changed")
    if contract["archive_identity"] != {
        "archive_path": EXPECTED_ARCHIVE_PATH,
        "archive_sha256": EXPECTED_ARCHIVE_SHA256,
        "v2_6_8_compact_checksum": EXPECTED_V268_CHECKSUM,
        "cycle_data_header_checksum": EXPECTED_CYCLE_HEADER_CHECKSUM,
    }:
        raise ValueError("archive or upstream identity contract changed")
    entries = contract["representative_entries"]
    if tuple(item.get("entry_name") for item in entries) != REPRESENTATIVE_ENTRIES:
        raise ValueError("representative entry order changed")
    if contract["candidate_assignment"] != {
        "capacity_check_candidate_positions": [1, 2, 3],
        "bulk_cycle_candidate_positions": [4, 5, 6, 7, 8],
        "assignment_basis": (
            "source-declared round sequence; archive row ordering remains under review"
        ),
        "promote_candidates_to_confirmed_labels": False,
    }:
        raise ValueError("candidate assignment changed")
    expected_fields = [
        {"header": header, "field": field, "unit": unit}
        for header, field, unit in SELECTED_COLUMNS
    ]
    if contract["selected_measurement_fields"] != expected_fields:
        raise ValueError("selected measurement fields changed")
    if contract["contrast_policy"] != {
        "method": "exact_decimal_group_ranges_without_fitted_thresholds",
        "contrast_fields": list(CONTRAST_FIELDS),
        "control_contrast_fields": list(CONTROL_CONTRAST_FIELDS),
        "record_non_overlapping_ranges": True,
        "fit_or_infer_thresholds": False,
        "classify_rows_from_measurements": False,
    }:
        raise ValueError("contrast policy changed")
    if any(contract["claim_policy"].values()):
        raise ValueError("claim policy may not promote bounded evidence")


def verify_upstream(v268: Mapping[str, Any]) -> dict[str, Any]:
    if v268.get("deterministic_result_checksum") != EXPECTED_V268_CHECKSUM:
        raise ValueError("v2.6.8 checksum mismatch")
    if canonical_checksum(v268) != EXPECTED_V268_CHECKSUM:
        raise ValueError("v2.6.8 content checksum mismatch")
    decision = v268.get("schema_read_decision", {})
    if decision.get("overall_status") != "bounded_schema_observed_gate_not_passed":
        raise ValueError("v2.6.8 gate changed")
    if v268.get("archive_audit", {}).get("observed_archive_sha256") != EXPECTED_ARCHIVE_SHA256:
        raise ValueError("v2.6.8 archive identity changed")
    observations = {
        item.get("entry_name"): item
        for item in v268.get("file_observations", [])
        if item.get("file_kind") == "cycle_data"
    }
    for entry in REPRESENTATIVE_ENTRIES:
        item = observations.get(entry)
        if not item:
            raise ValueError(f"v2.6.8 cycle observation missing: {entry}")
        if item.get("header_checksum") != EXPECTED_CYCLE_HEADER_CHECKSUM:
            raise ValueError(f"v2.6.8 cycle header changed: {entry}")
        if item.get("read_status") != "bounded_schema_observed":
            raise ValueError(f"v2.6.8 cycle schema boundary changed: {entry}")
    return {
        "v2_6_8_checksum_verified": True,
        "archive_sha256_preserved": True,
        "representative_cycle_headers_verified": True,
        "prior_schema_gate_preserved": True,
        "model_or_metric_change_performed": False,
    }


def pending_result(
    config: CycleRegimeConfig,
    contract: Mapping[str, Any],
    preservation: Mapping[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": VERSION,
        "artifact_kind": "battery_snl_lfp_bounded_cycle_regime_result",
        "package_id": PACKAGE_ID,
        "case_study_id": config.case_study_id,
        "bounded_source_id": config.bounded_source_id,
        "contract_id": contract["contract_id"],
        "contract_checksum": canonical_checksum(contract),
        "archive_path": config.archive_path,
        "archive_audit": {
            "status": "pending_local_artifact",
            "archive_present": False,
            "expected_archive_sha256": EXPECTED_ARCHIVE_SHA256,
            "observed_archive_sha256": None,
            "central_directory_read": False,
        },
        "representative_read_summary": {
            "status": "pending_local_artifact",
            "declared_entry_count": len(REPRESENTATIVE_ENTRIES),
            "opened_entry_count": 0,
            "sample_cycle_row_count": 0,
            "evidence_recorded_count": 0,
            "contract_mismatch_count": 0,
        },
        "file_observations": [],
        "cycle_regime_decision": {
            "source_sequence_candidate_assignment": "pending_local_artifact",
            "within_file_cycle_regime_contrast": "not_established",
            "capacity_check_vs_bulk_cycle_discrimination": "not_established",
            "step_level_discrimination": "not_available_no_step_identifier",
            "physical_cell_to_entry": "not_established",
            "cycle_command_to_rows": "not_established",
            "instrument_channel_to_columns": "not_established",
            "official_distribution_snapshot": "not_established",
            "cross_cohort_comparability": "not_admitted",
            "predictive_validation": "blocked",
            "overall_status": "pending_local_artifact",
        },
        "preservation_checks": dict(preservation),
        "scientific_closeout": {
            "status": "inconclusive",
            "result": "pending_bounded_cycle_regime_review",
            "evidence_level": "contract_defined_without_local_cycle_rows",
            "strongest_evidence": (
                "The official source sequence and exact first-eight-row read boundary "
                "are predeclared against the v2.6.8 schema and archive identity."
            ),
            "primary_limitation": (
                "The ignored local archive is unavailable in CI, so no bounded cycle "
                "summary values or within-file contrasts have been observed."
            ),
            "suitable_for": ["bounded local cycle-regime review planning"],
            "unsuitable_for": [
                "confirmed capacity-check labels", "step classification",
                "cycle-command binding", "instrument-channel binding",
                "cohort comparison", "predictive validation", "engineering decisions",
            ],
        },
        "recommendations": [
            "run the bounded review in the local checkout containing SNL LFP.zip",
            "review exact selected cycle-summary values and range contrasts",
            "do not promote source-sequence candidates to confirmed labels",
        ],
        "source_references": {
            "contract": config.contract_path,
            "v2_6_8_summary": config.v2_6_8_summary_path,
        },
        "archive_bytes_read_for_checksum": False,
        "zip_central_directory_read": False,
        "representative_cycle_entry_payloads_read": False,
        "cycle_summary_rows_read": False,
        "selected_measurement_values_retained": False,
    }
    for flag in FALSE_FLAGS:
        result[flag] = False
    result["deterministic_result_checksum"] = canonical_checksum(result)
    return result


def build_result(
    config: CycleRegimeConfig,
    contract: Mapping[str, Any],
    v268: Mapping[str, Any],
    repo_root: str | Path = ".",
) -> dict[str, Any]:
    validate_contract(contract, config)
    preservation = verify_upstream(v268)
    archive_path = repo_path(repo_root, config.archive_path)
    if not archive_path.is_file():
        return pending_result(config, contract, preservation)

    observed_sha = sha256_file(archive_path)
    if observed_sha != EXPECTED_ARCHIVE_SHA256:
        raise ValueError("archive checksum mismatch before entry payload access")

    representatives = {item["entry_name"]: item for item in contract["representative_entries"]}
    observations: list[dict[str, Any]] = []
    opened: list[str] = []
    with zipfile.ZipFile(archive_path, "r") as archive:
        infos: dict[str, list[zipfile.ZipInfo]] = {}
        for info in archive.infolist():
            infos.setdefault(info.filename, []).append(info)
        for entry in REPRESENTATIVE_ENTRIES:
            matches = infos.get(entry, [])
            if len(matches) != 1:
                observations.append(
                    failure_observation(
                        entry,
                        str(representatives[entry]["protocol_family"]),
                        (
                            "representative_entry_missing"
                            if not matches
                            else "representative_entry_duplicated"
                        ),
                    )
                )
                continue
            info = matches[0]
            if not safe_entry_name(info.filename) or info.flag_bits & 0x1:
                observations.append(
                    failure_observation(
                        entry,
                        str(representatives[entry]["protocol_family"]),
                        "representative_entry_unsafe_or_encrypted",
                    )
                )
                continue
            opened.append(entry)
            observations.append(
                read_cycle_sample(
                    archive,
                    info,
                    representatives[entry],
                    MAX_LINE_BYTES,
                )
            )

    recorded = [
        item for item in observations
        if item.get("read_status") == "bounded_cycle_regime_evidence_recorded"
    ]
    contrast_observed = [
        item for item in recorded
        if item.get("cycle_regime_contrast", {}).get("contrast_status")
        == "bounded_regime_contrast_observed"
    ]
    all_recorded = len(recorded) == len(REPRESENTATIVE_ENTRIES)
    all_contrast = len(contrast_observed) == len(REPRESENTATIVE_ENTRIES)
    discrimination = (
        "candidate_supported_not_established"
        if all_recorded and all_contrast
        else "not_established"
    )
    result: dict[str, Any] = {
        "schema_version": VERSION,
        "artifact_kind": "battery_snl_lfp_bounded_cycle_regime_result",
        "package_id": PACKAGE_ID,
        "case_study_id": config.case_study_id,
        "bounded_source_id": config.bounded_source_id,
        "contract_id": contract["contract_id"],
        "contract_checksum": canonical_checksum(contract),
        "archive_path": config.archive_path,
        "archive_audit": {
            "status": "verified",
            "archive_present": True,
            "expected_archive_sha256": EXPECTED_ARCHIVE_SHA256,
            "observed_archive_sha256": observed_sha,
            "central_directory_read": True,
        },
        "representative_read_summary": {
            "status": (
                "bounded_cycle_regime_evidence_recorded"
                if all_recorded
                else "bounded_cycle_regime_contract_not_fully_satisfied"
            ),
            "declared_entry_count": len(REPRESENTATIVE_ENTRIES),
            "opened_entries": opened,
            "opened_entry_count": len(opened),
            "sample_cycle_row_count": sum(
                int(item.get("sample_data_rows_read", 0)) for item in observations
            ),
            "evidence_recorded_count": len(recorded),
            "contract_mismatch_count": len(observations) - len(recorded),
            "within_file_contrast_observed_count": len(contrast_observed),
            "capacity_check_candidate_rows_per_entry": CAPACITY_CHECK_CANDIDATE_ROWS,
            "bulk_candidate_rows_per_entry": BULK_CANDIDATE_ROWS,
            "max_data_rows_per_entry": MAX_ROWS,
            "max_line_bytes": MAX_LINE_BYTES,
        },
        "file_observations": observations,
        "cycle_regime_decision": {
            "source_sequence_candidate_assignment": "recorded_not_promoted",
            "within_file_cycle_regime_contrast": (
                "observed_all_representatives"
                if all_contrast
                else ("observed_partial" if contrast_observed else "not_observed")
            ),
            "capacity_check_vs_bulk_cycle_discrimination": discrimination,
            "step_level_discrimination": "not_available_no_step_identifier",
            "physical_cell_to_entry": "not_established",
            "cycle_command_to_rows": "not_established",
            "instrument_channel_to_columns": "not_established",
            "official_distribution_snapshot": "not_established",
            "cross_cohort_comparability": "not_admitted",
            "predictive_validation": "blocked",
            "overall_status": (
                "bounded_cycle_regime_evidence_recorded_gate_not_passed"
                if all_recorded
                else "bounded_cycle_regime_contract_not_fully_satisfied"
            ),
        },
        "preservation_checks": preservation,
        "scientific_closeout": {
            "status": "diagnostic" if all_recorded else "inconclusive",
            "result": (
                "bounded_cycle_regime_candidates_recorded"
                if all_recorded
                else "bounded_cycle_regime_review_incomplete"
            ),
            "evidence_level": (
                "official_round_sequence_plus_first_eight_cycle_summary_rows_in_three_representatives"
                if all_recorded
                else "incomplete_bounded_cycle_summary_evidence"
            ),
            "strongest_evidence": (
                "The exact first eight cycle-summary rows were recorded from each "
                "predeclared representative, preserving selected measurements as "
                "exact decimal strings and comparing candidate groups without a fitted threshold."
            ),
            "primary_limitation": (
                "Source-sequence positions are candidates rather than confirmed labels; "
                "no step identifier, command log, complete file, instrument mapping, "
                "or calibration evidence was reviewed."
            ),
            "suitable_for": [
                "bounded cycle-regime diagnostics",
                "capacity-check discrimination feasibility assessment",
                "next contract design",
            ],
            "unsuitable_for": [
                "confirmed capacity-check labels", "step classification",
                "cycle-command binding", "instrument-channel binding",
                "cohort comparison", "model evaluation", "engineering decisions",
            ],
        },
        "recommendations": [
            "review the exact candidate-group ranges before authorizing any larger read",
            "do not treat source-sequence candidates as confirmed capacity-check labels",
            "do not read time-series rows unless a separate step-level contract is justified",
            "do not merge cohorts or execute a model",
        ],
        "source_references": {
            "contract": config.contract_path,
            "v2_6_8_summary": config.v2_6_8_summary_path,
        },
        "archive_bytes_read_for_checksum": True,
        "zip_central_directory_read": True,
        "representative_cycle_entry_payloads_read": bool(opened),
        "cycle_summary_rows_read": bool(recorded),
        "selected_measurement_values_retained": bool(recorded),
    }
    for flag in FALSE_FLAGS:
        result[flag] = False
    result["deterministic_result_checksum"] = canonical_checksum(result)
    return result


def compact(result: Mapping[str, Any]) -> dict[str, Any]:
    keep = (
        "schema_version", "package_id", "case_study_id", "bounded_source_id",
        "contract_id", "contract_checksum", "archive_path", "archive_audit",
        "representative_read_summary", "cycle_regime_decision", "preservation_checks",
        "scientific_closeout", "recommendations", "source_references",
        "archive_bytes_read_for_checksum", "zip_central_directory_read",
        "representative_cycle_entry_payloads_read", "cycle_summary_rows_read",
        "selected_measurement_values_retained", *FALSE_FLAGS,
    )
    output = {key: result[key] for key in keep}
    output["artifact_kind"] = "battery_snl_lfp_bounded_cycle_regime_compact_summary"
    observation_keys = (
        "entry_name", "file_kind", "protocol_family", "read_status", "bytes_read",
        "header_checksum", "sample_data_rows_read", "sample_row_widths",
        "cycle_index_strictly_increasing", "selected_field_contract",
        "selected_cycle_rows", "cycle_regime_contrast",
        "selected_measurement_values_retained",
        "selected_values_preserved_as_exact_decimal_strings",
        "candidate_assignment_promoted", "full_file_read", "error",
    )
    output["file_observations"] = [
        {key: item[key] for key in observation_keys if key in item}
        for item in result["file_observations"]
    ]
    output["deterministic_result_checksum"] = canonical_checksum(output)
    return output


def validate_result(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != VERSION or payload.get("package_id") != PACKAGE_ID:
        raise ValueError("unsupported result")
    decision = payload.get("cycle_regime_decision", {})
    required_boundaries = {
        "physical_cell_to_entry": "not_established",
        "cycle_command_to_rows": "not_established",
        "instrument_channel_to_columns": "not_established",
        "official_distribution_snapshot": "not_established",
        "cross_cohort_comparability": "not_admitted",
        "predictive_validation": "blocked",
        "step_level_discrimination": "not_available_no_step_identifier",
    }
    for key, expected in required_boundaries.items():
        if decision.get(key) != expected:
            raise ValueError(f"scientific boundary changed: {key}")
    if decision.get("capacity_check_vs_bulk_cycle_discrimination") not in {
        "not_established", "candidate_supported_not_established",
    }:
        raise ValueError("capacity-check discrimination was promoted")
    if any(payload.get(flag) is not False for flag in FALSE_FLAGS):
        raise ValueError("prohibited execution flag changed")

    allowed_entries = set(REPRESENTATIVE_ENTRIES)
    for item in payload.get("file_observations", []):
        if item.get("entry_name") not in allowed_entries:
            raise ValueError("nonrepresentative observation recorded")
        if item.get("file_kind", "cycle_data") != "cycle_data":
            raise ValueError("time-series observation recorded")
        if item.get("sample_data_rows_read", 0) > MAX_ROWS:
            raise ValueError("bounded row limit exceeded")
        if item.get("full_file_read") is True:
            raise ValueError("full file read was performed")
        rows = item.get("selected_cycle_rows", [])
        if rows and len(rows) != MAX_ROWS:
            raise ValueError("selected cycle-row evidence is incomplete")
        for position, row in enumerate(rows, start=1):
            if row.get("row_position") != position:
                raise ValueError("cycle-row position changed")
            expected_candidate = (
                "capacity_check_candidate"
                if position <= CAPACITY_CHECK_CANDIDATE_ROWS
                else "bulk_cycle_candidate"
            )
            if row.get("source_sequence_candidate") != expected_candidate:
                raise ValueError("source-sequence candidate assignment changed")
            if row.get("candidate_assignment_promoted") is not False:
                raise ValueError("candidate assignment was promoted")
            selected = row.get("selected_values", {})
            if set(selected) != {field for _, field, _ in SELECTED_COLUMNS}:
                raise ValueError("selected measurement field set changed")
            for field, value in selected.items():
                decimal_value(str(value), field)
        contrast = item.get("cycle_regime_contrast")
        if contrast:
            if contrast.get("threshold_fitted_or_inferred") is not False:
                raise ValueError("contrast threshold was fitted or inferred")
            if contrast.get("candidate_labels_promoted") is not False:
                raise ValueError("candidate labels were promoted")
    if payload.get("deterministic_result_checksum") != canonical_checksum(payload):
        raise ValueError("deterministic result checksum mismatch")


def execute(
    config: CycleRegimeConfig,
    repo_root: str | Path = ".",
    write_outputs: bool = True,
) -> dict[str, Any]:
    contract = _json(repo_path(repo_root, config.contract_path))
    v268 = _json(repo_path(repo_root, config.v2_6_8_summary_path))
    result = build_result(config, contract, v268, repo_root)
    validate_result(result)
    if write_outputs:
        output_root = repo_path(repo_root, config.output_root)
        output_root.mkdir(parents=True, exist_ok=True)
        (output_root / "bounded_cycle_regime_result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tracked = repo_path(repo_root, config.tracked_summary_path)
        tracked.parent.mkdir(parents=True, exist_ok=True)
        compact_result = compact(result)
        validate_result(compact_result)
        tracked.write_text(
            json.dumps(compact_result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return result


def preview(config: CycleRegimeConfig, repo_root: str | Path = ".") -> dict[str, Any]:
    contract = _json(repo_path(repo_root, config.contract_path))
    validate_contract(contract, config)
    return {
        "schema_version": VERSION,
        "package_id": PACKAGE_ID,
        "bounded_source_id": config.bounded_source_id,
        "archive_path": config.archive_path,
        "archive_present": repo_path(repo_root, config.archive_path).is_file(),
        "representative_entries": list(REPRESENTATIVE_ENTRIES),
        "capacity_check_candidate_positions": [1, 2, 3],
        "bulk_cycle_candidate_positions": [4, 5, 6, 7, 8],
        "selected_measurement_fields": [field for _, field, _ in SELECTED_COLUMNS],
        "max_data_rows_per_entry": MAX_ROWS,
        "max_line_bytes": MAX_LINE_BYTES,
        "allowed_reads": [
            "archive SHA-256 stream",
            "ZIP central directory",
            "three exact representative cycle-data entry payloads",
            "one header and exactly the first eight cycle-summary rows per entry",
        ],
        "prohibited_reads": [
            "time-series entries", "nonrepresentative entries", "complete CSV files",
            "archive extraction", "fitted or inferred classification thresholds",
            "network", "credentials",
        ],
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
            "deterministic_result_checksum": value["deterministic_result_checksum"],
        }
    print(
        json.dumps(value, ensure_ascii=False, sort_keys=True)
        if args.json
        else json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
