"""Pinned independent verifier for the NIST response-free structural simulation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .action_registry import describe_action, load_action_registry
from .design_simulation import simulate_design_structure_file
from .kernel import load_research_state
from .nist_structural_design_action import (
    ACTION_TYPE,
    ACTION_VERSION,
    OUTPUT_RELATIVE_PATH,
    REPORT_SCHEMA_VERSION,
    NistStructuralDesignActionError,
    _file_record,
    _validate_request,
    _verify_result_boundary,
)


def _load_json(path: Path) -> dict[str, Any]:
    def reject(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise NistStructuralDesignActionError(f"duplicate JSON key is not allowed: {key}")
            out[key] = value
        return out

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject)
    except json.JSONDecodeError as exc:
        raise NistStructuralDesignActionError("invalid NIST action report JSON") from exc
    if not isinstance(value, dict):
        raise NistStructuralDesignActionError("NIST action report root must be an object")
    return value


def verify_nist_structural_design_report_pinned(
    report_file: str | Path,
    *,
    request_value: Mapping[str, Any],
    request_path: Path,
    request_record: Mapping[str, Any],
) -> dict[str, Any]:
    report_path = Path(report_file).expanduser().resolve(strict=True)
    report = _load_json(report_path)
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise NistStructuralDesignActionError("NIST action report schema drifted")
    if report.get("execution_status") != "completed" or report.get("action_type") != ACTION_TYPE:
        raise NistStructuralDesignActionError("NIST action report status/type drifted")
    if report.get("action_version") != ACTION_VERSION or report.get("cost_units") != 1:
        raise NistStructuralDesignActionError("NIST action report version/cost drifted")
    if report.get("request") != dict(request_record):
        raise NistStructuralDesignActionError("report request binding differs from pinned request")
    if request_record.get("path") != str(request_path):
        raise NistStructuralDesignActionError("pinned request path binding drifted")
    request = _validate_request(request_value, base=request_path.parent)
    if request["action_id"] != report.get("action_id"):
        raise NistStructuralDesignActionError("pinned request action_id drifted")
    expected_report = (
        request["research_run"] / "actions" / request["action_id"] / "action_result.json"
    ).resolve(strict=True)
    if report_path != expected_report:
        raise NistStructuralDesignActionError("NIST report path escapes expected action directory")

    registry = load_action_registry(request["registry"], repository_root=request["repository_root"])
    if registry["registry_sha256"] != request["expected_registry_sha256"]:
        raise NistStructuralDesignActionError("NIST execution registry changed")
    contract = describe_action(registry, ACTION_TYPE)
    if contract["version"] != ACTION_VERSION or contract["cost_units"] != 1:
        raise NistStructuralDesignActionError("NIST execution contract drifted")

    spec_record = _file_record(request["simulation_spec"])
    if report.get("immutable_inputs") != [spec_record]:
        raise NistStructuralDesignActionError("NIST simulation spec binding drifted")
    if spec_record["sha256"] != request["expected_simulation_spec_sha256"]:
        raise NistStructuralDesignActionError("NIST simulation spec checksum drifted")

    recomputed = simulate_design_structure_file(request["simulation_spec"])
    _verify_result_boundary(recomputed)
    if report.get("simulation_result") != recomputed:
        raise NistStructuralDesignActionError("NIST simulation result is not reproducible")

    output = report.get("output")
    if not isinstance(output, Mapping) or output.get("relative_path") != OUTPUT_RELATIVE_PATH:
        raise NistStructuralDesignActionError("NIST simulation output binding is malformed")
    output_path = Path(str(output.get("path"))).resolve(strict=True)
    expected_output = (
        request["research_run"] / "actions" / request["action_id"] / OUTPUT_RELATIVE_PATH
    ).resolve(strict=True)
    if output_path != expected_output:
        raise NistStructuralDesignActionError("NIST simulation output path drifted")
    current_output = _file_record(output_path)
    recorded_output = {key: output[key] for key in ("path", "bytes", "sha256")}
    if current_output != recorded_output:
        raise NistStructuralDesignActionError("NIST simulation output bytes drifted")
    if _load_json(output_path) != recomputed:
        raise NistStructuralDesignActionError("NIST simulation output content is not reproducible")

    physical = report.get("physical_evidence_requirement")
    if not isinstance(physical, Mapping):
        raise NistStructuralDesignActionError("physical evidence requirement is missing")
    if (
        physical.get("satisfied") is not False
        or physical.get("required_real_trace_count") != 9
        or physical.get("synthetic_or_simulated_trace_substitution_allowed") is not False
    ):
        raise NistStructuralDesignActionError("physical evidence requirement was improperly promoted")
    conditions = physical.get("required_new_conditions")
    expected_conditions = [
        {"actual_laser_power_w": 137.9, "scan_speed_mm_s": 800.0, "minimum_traces": 3},
        {"actual_laser_power_w": 137.9, "scan_speed_mm_s": 1200.0, "minimum_traces": 3},
        {"actual_laser_power_w": 179.2, "scan_speed_mm_s": 400.0, "minimum_traces": 3},
    ]
    if conditions != expected_conditions:
        raise NistStructuralDesignActionError("physical Stage 1 condition contract drifted")
    if report.get("scientific_evidence_upgraded") is not False:
        raise NistStructuralDesignActionError("simulation cannot upgrade scientific evidence")

    state = load_research_state(request["research_run"])
    matches = [
        item for item in state["actions"]
        if item.get("action_id") == request["action_id"]
    ]
    if len(matches) != 1:
        raise NistStructuralDesignActionError("ledger must contain exactly one NIST action")
    action = matches[0]
    if action.get("action_type") != ACTION_TYPE or action.get("status") != "completed" or action.get("cost_units") != 1:
        raise NistStructuralDesignActionError("ledger NIST action contract drifted")
    expected_artifacts = [_file_record(report_path), _file_record(output_path)]
    if action.get("artifacts") != expected_artifacts:
        raise NistStructuralDesignActionError("ledger artifacts do not checksum-bind NIST outputs")

    return {
        "valid": True,
        "execution_status": "completed",
        "action_id": request["action_id"],
        "action_report": str(report_path),
        "research_id": state["research_id"],
        "research_status": state["status"],
        "ledger_sha256": state["ledger_sha256"],
        "physical_evidence_requirement_satisfied": False,
        "required_real_trace_count": 9,
        "scientific_evidence_upgraded": False,
    }


__all__ = ["verify_nist_structural_design_report_pinned"]
