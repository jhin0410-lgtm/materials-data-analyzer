"""Pinned execution-time verifier for the NIST structural simulation action."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from . import nist_structural_design_simulation_action as action
from .design_simulation import simulate_design_structure_file
from .kernel import load_research_state


def verify_nist_structural_design_simulation_report_pinned(
    report_file: str | Path,
    *,
    request_value: Mapping[str, Any],
    request_path: Path,
    request_record: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute one structural simulation against the already-authorized request snapshot."""
    report_path = Path(report_file).expanduser().resolve(strict=True)
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise action.NistStructuralSimulationActionError("invalid action report JSON") from exc
    if not isinstance(report, dict):
        raise action.NistStructuralSimulationActionError("action report root must be an object")
    if report.get("schema_version") != action.REPORT_SCHEMA_VERSION:
        raise action.NistStructuralSimulationActionError("invalid action report schema")
    if report.get("execution_status") != "completed":
        raise action.NistStructuralSimulationActionError("action report must be completed")
    if report.get("action_type") != action.ACTION_TYPE or report.get("action_version") != action.ACTION_VERSION:
        raise action.NistStructuralSimulationActionError("action report type/version mismatch")
    if report.get("action_id") != request_value.get("action_id"):
        raise action.NistStructuralSimulationActionError("action report action_id does not match pinned request")
    expected_record = dict(request_record)
    if report.get("request") != expected_record:
        raise action.NistStructuralSimulationActionError("action report request binding does not match pinned request")
    if expected_record.get("path") != str(request_path):
        raise action.NistStructuralSimulationActionError("pinned request path binding drifted")
    request = action._validate_request(request_value, base=request_path.parent)
    if request["action_type"] != action.ACTION_TYPE:
        raise action.NistStructuralSimulationActionError("pinned request action_type mismatch")
    if report.get("research_run") != str(request["research_run"]):
        raise action.NistStructuralSimulationActionError("action report research_run mismatch")

    expected_report_path = (
        request["research_run"] / "actions" / request["action_id"] / action.ACTION_REPORT_FILENAME
    ).resolve(strict=True)
    if report_path != expected_report_path:
        raise action.NistStructuralSimulationActionError("action report path escapes pinned action directory")
    output_path = (report_path.parent / action.OUTPUT_RELATIVE_PATH).resolve(strict=True)
    output_record = report.get("output")
    if not isinstance(output_record, Mapping) or output_record.get("path") != str(output_path):
        raise action.NistStructuralSimulationActionError("action output path binding mismatch")
    current_output = action._file_record(output_path)
    if output_record.get("sha256") != current_output["sha256"] or output_record.get("bytes") != current_output["bytes"]:
        raise action.NistStructuralSimulationActionError("action output bytes no longer match report")

    recomputed = simulate_design_structure_file(request["simulation_config"])
    try:
        current_output_value = json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise action.NistStructuralSimulationActionError("simulation output is invalid JSON") from exc
    if current_output_value != recomputed:
        raise action.NistStructuralSimulationActionError("simulation output is not recomputable from pinned config")
    if report.get("simulation_config") != action._file_record(request["simulation_config"]):
        raise action.NistStructuralSimulationActionError("simulation config bytes no longer match report")
    if report.get("outcome") != action._outcome(recomputed):
        raise action.NistStructuralSimulationActionError("reported outcome is not recomputable")

    boundary = report.get("scientific_boundary")
    expected_boundary = {
        "response_values_used": False,
        "response_values_synthesized": False,
        "predictive_model_fitted": False,
        "causal_effects_estimated": False,
        "engineering_decision_authorized": False,
        "real_experimental_evidence_created": False,
        "simulation_satisfies_physical_acquisition_requirement": False,
        "proposed_design_counts_are_synthetic_evidence": False,
    }
    if boundary != expected_boundary:
        raise action.NistStructuralSimulationActionError("action report widened the scientific boundary")
    if report.get("stop_reason") != action.STOP_REASON:
        raise action.NistStructuralSimulationActionError("action report terminal reason drifted")

    state = load_research_state(request["research_run"])
    if state.get("status") != "stopped" or state.get("stop", {}).get("reason_code") != action.STOP_REASON:
        raise action.NistStructuralSimulationActionError("bounded research run did not stop on physical evidence requirement")
    actions = state.get("actions")
    if not isinstance(actions, list):
        raise action.NistStructuralSimulationActionError("research action ledger is malformed")
    matches = [item for item in actions if isinstance(item, Mapping) and item.get("action_id") == request["action_id"]]
    if len(matches) != 1:
        raise action.NistStructuralSimulationActionError("research ledger must contain exactly one matching action")
    recorded = matches[0]
    if recorded.get("action_type") != action.ACTION_TYPE or recorded.get("status") != "completed" or recorded.get("cost_units") != 2:
        raise action.NistStructuralSimulationActionError("research ledger action contract mismatch")
    report_record = action._file_record(report_path)
    artifacts = recorded.get("artifacts")
    if not isinstance(artifacts, list) or not any(
        isinstance(item, Mapping)
        and item.get("path") == report_record["path"]
        and item.get("sha256") == report_record["sha256"]
        and item.get("bytes") == report_record["bytes"]
        for item in artifacts
    ):
        raise action.NistStructuralSimulationActionError("research ledger does not checksum-bind the action report")

    return {
        "valid": True,
        "execution_status": "completed",
        "action_id": request["action_id"],
        "action_type": action.ACTION_TYPE,
        "outcome": report["outcome"],
        "research_id": state["research_id"],
        "ledger_sha256": state["ledger_sha256"],
        "physical_evidence_requirement_satisfied": False,
        "scientific_evidence_upgraded": False,
    }


__all__ = ["verify_nist_structural_design_simulation_report_pinned"]
