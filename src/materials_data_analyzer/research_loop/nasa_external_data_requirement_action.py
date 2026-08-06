"""Typed external-data requirement action for the NASA research loop."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from platform_core.output_safety import transactional_output_directory

from .action_registry import describe_action, load_action_registry
from .kernel import (
    ResearchLoopError,
    append_action,
    append_stop,
    load_research_state,
)
from .nasa_audit_executor import verify_nasa_audit_action_report
from .nasa_protocol_stratification_action import (
    verify_nasa_protocol_stratification_report,
)
from .nasa_target_reference_action import verify_nasa_target_reference_report

ACTION_TYPE = "external_data_requirement_generation"
ACTION_REPORT_FILENAME = "action_result.json"
REQUEST_SCHEMA_VERSION = "1.0"
REPORT_SCHEMA_VERSION = "1.0"
OUTPUT_RELATIVE_PATH = "reports/external_data_requirement.json"
STOP_REASON = "external_evidence_required"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_REQUEST_KEYS = {
    "schema_version",
    "action_id",
    "action_type",
    "research_run",
    "registry",
    "repository_root",
    "expected_registry_sha256",
}
_PROTOCOL_LIMIT_OUTCOMES = {
    "protocol_groups_too_small",
    "protocol_metadata_insufficient",
}


class NasaExternalDataRequirementActionError(ResearchLoopError):
    """Raised when requirement generation violates its fixed contract."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NasaExternalDataRequirementActionError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise NasaExternalDataRequirementActionError(
            f"invalid JSON in {path}: {exc}"
        ) from exc


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_record(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise FileNotFoundError(f"required file not found: {resolved}")
    return {
        "path": str(resolved),
        "bytes": resolved.stat().st_size,
        "sha256": _sha256_file(resolved),
    }


def _resolve_path(raw: Any, *, field: str, base: Path) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise NasaExternalDataRequirementActionError(
            f"{field} must be a non-empty path string"
        )
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve(strict=True)


def _validate_request(path: Path) -> dict[str, Any]:
    value = _load_json(path)
    if not isinstance(value, dict):
        raise NasaExternalDataRequirementActionError(
            "action request must be a JSON object"
        )
    missing = sorted(_REQUEST_KEYS - set(value))
    unknown = sorted(set(value) - _REQUEST_KEYS)
    if missing:
        raise NasaExternalDataRequirementActionError(
            "action request is missing required keys: " + ", ".join(missing)
        )
    if unknown:
        raise NasaExternalDataRequirementActionError(
            "action request has unknown keys: " + ", ".join(unknown)
        )
    if value["schema_version"] != REQUEST_SCHEMA_VERSION:
        raise NasaExternalDataRequirementActionError(
            f"unsupported request schema_version: {value['schema_version']!r}"
        )
    action_id = value["action_id"]
    if not isinstance(action_id, str) or not _SAFE_ID.fullmatch(action_id):
        raise NasaExternalDataRequirementActionError(
            "action_id must use only letters, digits, dot, underscore, or hyphen"
        )
    if value["action_type"] != ACTION_TYPE:
        raise NasaExternalDataRequirementActionError(
            f"this executor accepts only action_type={ACTION_TYPE!r}"
        )
    registry_sha = value["expected_registry_sha256"]
    if not isinstance(registry_sha, str) or not re.fullmatch(
        r"[0-9a-f]{64}", registry_sha
    ):
        raise NasaExternalDataRequirementActionError(
            "expected_registry_sha256 must be lowercase SHA-256 hex"
        )
    base = path.parent
    return {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "action_id": action_id,
        "action_type": ACTION_TYPE,
        "research_run": _resolve_path(
            value["research_run"], field="research_run", base=base
        ),
        "registry": _resolve_path(value["registry"], field="registry", base=base),
        "repository_root": _resolve_path(
            value["repository_root"], field="repository_root", base=base
        ),
        "expected_registry_sha256": registry_sha,
    }


def _action_report_path(
    state: dict[str, Any], action_type: str
) -> Path | None:
    actions = [
        action
        for action in state["actions"]
        if action["action_type"] == action_type
    ]
    if not actions:
        return None
    latest = actions[-1]
    if latest["status"] != "completed":
        raise NasaExternalDataRequirementActionError(
            f"latest {action_type} action must be completed"
        )
    matches = [
        Path(item["path"])
        for item in latest.get("artifacts", [])
        if Path(item["path"]).name == ACTION_REPORT_FILENAME
    ]
    if len(matches) != 1:
        raise NasaExternalDataRequirementActionError(
            f"completed {action_type} action must bind one action_result.json"
        )
    return matches[0].resolve(strict=True)


def _output_path(report: dict[str, Any], relative_path: str) -> Path:
    matches = [
        Path(item["path"])
        for item in report.get("outputs", [])
        if item.get("relative_path") == relative_path
    ]
    if len(matches) != 1:
        raise NasaExternalDataRequirementActionError(
            f"prior report must bind exactly one {relative_path}"
        )
    return matches[0].resolve(strict=True)


def _protocol_requirement(
    protocol_report_path: Path,
) -> tuple[dict[str, Any], list[Path]] | None:
    verified = verify_nasa_protocol_stratification_report(protocol_report_path)
    outcome = verified.get("outcome")
    if outcome not in _PROTOCOL_LIMIT_OUTCOMES:
        return None
    report = _load_json(protocol_report_path)
    if not isinstance(report, dict):
        raise NasaExternalDataRequirementActionError(
            "protocol action report must be an object"
        )
    summary = report.get("summary")
    if not isinstance(summary, dict):
        raise NasaExternalDataRequirementActionError(
            "protocol action report is missing summary"
        )
    metrics_path = _output_path(
        report,
        "protocol_stratification/protocol_group_metrics.csv",
    )
    with metrics_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    minimum = int(summary["minimum_evaluated_batteries_per_group"])
    group_requirements: list[dict[str, Any]] = []
    for row in rows:
        observed = int(row["evaluated_battery_count"])
        group_requirements.append(
            {
                "ambient_temperature_median_c": float(
                    row["ambient_temperature_median_c"]
                ),
                "currently_evaluated_batteries": observed,
                "minimum_evaluated_batteries": minimum,
                "minimum_additional_evaluated_batteries": max(
                    0, minimum - observed
                ),
            }
        )
    group_requirements.sort(
        key=lambda item: float(item["ambient_temperature_median_c"])
    )
    total_deficit = sum(
        int(item["minimum_additional_evaluated_batteries"])
        for item in group_requirements
    )
    if outcome == "protocol_groups_too_small" and total_deficit <= 0:
        raise NasaExternalDataRequirementActionError(
            "protocol outcome reports sparse groups but no group deficit exists"
        )

    requirement = {
        "schema_version": "1.0",
        "outcome": "minimum_external_cohort_contract_generated",
        "status": "Diagnostic",
        "current_evidence_level": "Unsupported",
        "blocker": outcome,
        "decision_use": (
            "Determine whether battery-level Ridge-minus-persistence MAE differs "
            "across exact source-recorded ambient-temperature groups."
        ),
        "required_cohort_role": "independent_external_or_predeclared_calibration",
        "protocol_field": "ambient_temperature_median_c",
        "protocol_unit": "degree_Celsius",
        "protocol_metadata_contract": {
            "battery_level": True,
            "finite_numeric_value_required": True,
            "source_recorded_value_required": True,
            "rounding_prohibited": True,
            "binning_prohibited": True,
            "filename_or_battery_id_inference_prohibited": True,
        },
        "minimum_group_contract": {
            "minimum_exact_groups": 2,
            "minimum_evaluated_batteries_per_exact_group": minimum,
            "group_requirements": group_requirements,
            "minimum_total_additional_evaluated_batteries": total_deficit,
            "eligibility_threshold_is_not_power_analysis": True,
        },
        "comparability_contract": {
            "explicit_source_cohort_identifier_required": True,
            "battery_disjoint_evaluation_required": True,
            "random_row_split_prohibited": True,
            "exact_horizon_definition_must_match": True,
            "target_and_reference_semantics_must_match": True,
            "units_must_be_explicit_and_harmonized_without_silent_conversion": True,
        },
        "provenance_contract": {
            "existing_NASA_batteries_may_not_be_relabelled_as_external": True,
            "source_license_and_acquisition_record_required": True,
            "sample_identity_and_processing_history_required": True,
            "measurement_conditions_and_exclusions_required": True,
        },
        "scientific_boundary": (
            "Meeting this contract only makes the predeclared diagnostic eligible. "
            "It does not prove statistical power, causality, transportability, or "
            "predictive validity and does not upgrade the current evidence level."
        ),
    }
    return requirement, [protocol_report_path, metrics_path]


def _target_requirement(
    target_report_path: Path,
) -> tuple[dict[str, Any], list[Path]] | None:
    verified = verify_nasa_target_reference_report(target_report_path)
    if verified.get("outcome") != "required_reference_metadata_missing":
        return None
    requirement = {
        "schema_version": "1.0",
        "outcome": "minimum_external_cohort_contract_generated",
        "status": "Diagnostic",
        "current_evidence_level": "Unsupported",
        "blocker": "required_reference_metadata_missing",
        "decision_use": (
            "Establish a defensible battery-level capacity reference before exact-"
            "horizon target normalization and model comparison."
        ),
        "required_cohort_role": "independent_external_or_predeclared_calibration",
        "required_metadata": [
            {
                "field": "reference_capacity_ah",
                "unit": "ampere_hour",
                "requirements": [
                    "positive_finite_numeric_value",
                    "battery_level_source_provenance",
                    "measurement_or_declaration_timing",
                    "definition_and_method",
                ],
            }
        ],
        "prohibited_substitutions": [
            "post_forecast_target_values",
            "filename_inference",
            "silent_target_repair",
            "relabeling_existing_evaluation_batteries_as_external",
        ],
        "scientific_boundary": (
            "Supplying metadata permits a predeclared sensitivity analysis only. "
            "It does not establish predictive validity or upgrade evidence."
        ),
    }
    return requirement, [target_report_path]


def _build_requirement(
    state: dict[str, Any],
) -> tuple[dict[str, Any], list[Path]]:
    protocol_path = _action_report_path(state, "protocol_stratification")
    if protocol_path is not None:
        result = _protocol_requirement(protocol_path)
        if result is not None:
            return result
    target_path = _action_report_path(state, "target_reference_sensitivity")
    if target_path is not None:
        result = _target_requirement(target_path)
        if result is not None:
            return result
    raise NasaExternalDataRequirementActionError(
        "verified state contains no supported external-data requirement trigger"
    )


def _preflight(request_path: Path) -> dict[str, Any]:
    request = _validate_request(request_path)
    research_run = request["research_run"]
    repository_root = request["repository_root"]
    if not research_run.is_dir() or not repository_root.is_dir():
        raise NasaExternalDataRequirementActionError(
            "research_run and repository_root must be directories"
        )
    state = load_research_state(research_run)
    if state["status"] != "active":
        raise NasaExternalDataRequirementActionError("research run is stopped")
    if any(
        action["action_id"] == request["action_id"]
        for action in state["actions"]
    ):
        raise NasaExternalDataRequirementActionError(
            f"duplicate action_id: {request['action_id']}"
        )
    action_directory = research_run / "actions" / request["action_id"]
    if action_directory.exists():
        raise FileExistsError(f"action output already exists: {action_directory}")
    registry = load_action_registry(
        request["registry"], repository_root=repository_root
    )
    if registry["registry_sha256"] != request["expected_registry_sha256"]:
        raise NasaExternalDataRequirementActionError(
            "action registry SHA-256 does not match the request"
        )
    contract = describe_action(registry, ACTION_TYPE)
    if contract["availability"] != "available":
        raise NasaExternalDataRequirementActionError(
            "registered external-data requirement action is not executable"
        )
    binding = contract["binding"]
    if (
        binding["kind"] != "source_script"
        or binding["path"]
        != "scripts/run_nasa_external_data_requirement_action.py"
    ):
        raise NasaExternalDataRequirementActionError(
            "external-data action binding does not match the fixed executor"
        )
    if state["budget"]["actions_remaining"] <= 0:
        raise NasaExternalDataRequirementActionError(
            "research action budget is exhausted"
        )
    if contract["cost_units"] > state["budget"]["cost_units_remaining"]:
        raise NasaExternalDataRequirementActionError(
            "research cost budget would be exceeded"
        )
    requirement, source_paths = _build_requirement(state)
    return {
        "request": request,
        "state": state,
        "registry": registry,
        "contract": contract,
        "requirement": requirement,
        "source_paths": source_paths,
    }


def execute_nasa_external_data_requirement_action(
    request_file: str | Path,
) -> dict[str, Any]:
    """Generate a minimum external-data contract and stop the bounded loop."""
    request_path = Path(request_file).expanduser().resolve(strict=True)
    preflight = _preflight(request_path)
    request = preflight["request"]
    contract = preflight["contract"]
    research_run: Path = request["research_run"]
    action_id = request["action_id"]
    action_directory = research_run / "actions" / action_id
    requirement_path = action_directory / OUTPUT_RELATIVE_PATH
    report_path = action_directory / ACTION_REPORT_FILENAME
    started_at = _utc_now()

    with transactional_output_directory(
        action_directory,
        protected_paths=(request_path, *preflight["source_paths"]),
        recognized_markers=(ACTION_REPORT_FILENAME,),
    ) as staging:
        staged_requirement = staging / OUTPUT_RELATIVE_PATH
        _write_json(staged_requirement, preflight["requirement"])
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "execution_status": "completed",
            "action_id": action_id,
            "action_type": ACTION_TYPE,
            "action_version": contract["version"],
            "cost_units": contract["cost_units"],
            "started_at_utc": started_at,
            "completed_at_utc": _utc_now(),
            "request": _file_record(request_path),
            "registry": {
                "registry_id": preflight["registry"]["registry_id"],
                "registry_path": preflight["registry"]["registry_path"],
                "registry_sha256": preflight["registry"]["registry_sha256"],
            },
            "research_run": str(research_run),
            "immutable_inputs": [
                _file_record(path) for path in preflight["source_paths"]
            ],
            "outcome": preflight["requirement"]["outcome"],
            "requirement": preflight["requirement"],
            "output": {
                "relative_path": OUTPUT_RELATIVE_PATH,
                **_file_record(staged_requirement),
                "path": str(requirement_path),
            },
            "stop_reason": STOP_REASON,
            "verification": {
                "requirement_names_blocker_and_decision_use": True,
                "required_metadata_and_units_are_explicit": True,
                "cohort_role_is_external_or_calibration": True,
                "no_existing_dataset_is_rebranded_as_external": True,
                "data_download_not_performed": True,
                "evidence_level_unchanged": True,
            },
        }
        _write_json(staging / ACTION_REPORT_FILENAME, report)

    append_action(
        research_run,
        action_id=action_id,
        action_type=ACTION_TYPE,
        status="completed",
        summary=(
            "Minimum external-data requirement contract generated; the current "
            "evidence remains Unsupported."
        ),
        cost_units=contract["cost_units"],
        artifact_paths=[report_path, requirement_path],
    )
    final_state = append_stop(
        research_run,
        reason_code=STOP_REASON,
        summary=(
            "The bounded loop requires independently sourced evidence satisfying "
            "the generated contract before further analysis."
        ),
    )
    return {
        "execution_status": "completed",
        "action_id": action_id,
        "outcome": preflight["requirement"]["outcome"],
        "action_report": str(report_path),
        "requirement_report": str(requirement_path),
        "research_state": final_state,
    }


def verify_nasa_external_data_requirement_report(
    report_file: str | Path,
) -> dict[str, Any]:
    """Recompute the requirement and verify output, ledger, and terminal state."""
    report_path = Path(report_file).expanduser().resolve(strict=True)
    report = _load_json(report_path)
    if not isinstance(report, dict):
        raise NasaExternalDataRequirementActionError(
            "action report must be a JSON object"
        )
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise NasaExternalDataRequirementActionError(
            "invalid external-data action report schema"
        )
    if report.get("execution_status") != "completed":
        raise NasaExternalDataRequirementActionError(
            "external-data action report must be completed"
        )
    if report.get("action_type") != ACTION_TYPE:
        raise NasaExternalDataRequirementActionError(
            "action report has the wrong action_type"
        )
    request_record = report.get("request")
    if not isinstance(request_record, dict) or _file_record(
        Path(request_record["path"])
    ) != request_record:
        raise NasaExternalDataRequirementActionError(
            "action request no longer matches the report"
        )
    for record in report.get("immutable_inputs", []):
        if not isinstance(record, dict) or _file_record(
            Path(record["path"])
        ) != record:
            raise NasaExternalDataRequirementActionError(
                "immutable input no longer matches the report"
            )

    research_run = Path(report["research_run"])
    state = load_research_state(research_run)
    requirement, _ = _build_requirement(state)
    if report.get("requirement") != requirement:
        raise NasaExternalDataRequirementActionError(
            "reported external-data requirement is not reproducible"
        )
    output_record = report.get("output")
    if not isinstance(output_record, dict):
        raise NasaExternalDataRequirementActionError(
            "action report is missing output binding"
        )
    output_path = Path(output_record["path"])
    recorded_file = {
        key: output_record[key] for key in ("path", "bytes", "sha256")
    }
    if _file_record(output_path) != recorded_file:
        raise NasaExternalDataRequirementActionError(
            "requirement output no longer matches the report"
        )
    if _load_json(output_path) != requirement:
        raise NasaExternalDataRequirementActionError(
            "requirement output is not reproducible"
        )

    matching = [
        action
        for action in state["actions"]
        if action["action_id"] == report["action_id"]
    ]
    if len(matching) != 1 or matching[0]["status"] != "completed":
        raise NasaExternalDataRequirementActionError(
            "research ledger does not contain the completed action"
        )
    if state["status"] != "stopped":
        raise NasaExternalDataRequirementActionError(
            "research loop was not stopped after requirement generation"
        )
    stop = state.get("stop")
    if not isinstance(stop, dict) or stop.get("reason_code") != STOP_REASON:
        raise NasaExternalDataRequirementActionError(
            "research loop has the wrong terminal reason"
        )
    return {
        "valid": True,
        "execution_status": "completed",
        "action_id": report["action_id"],
        "outcome": report["outcome"],
        "research_id": state["research_id"],
        "research_status": state["status"],
        "stop_reason": STOP_REASON,
        "ledger_sha256": state["ledger_sha256"],
        "action_report": str(report_path),
    }
