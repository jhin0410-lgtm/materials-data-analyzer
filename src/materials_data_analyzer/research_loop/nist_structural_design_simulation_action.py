"""Typed, response-free NIST AM-Bench structural design simulation action."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from platform_core.output_safety import transactional_output_directory

from .action_registry import describe_action, load_action_registry
from .design_simulation import simulate_design_structure_file
from .kernel import ResearchLoopError, append_action_and_stop, load_research_state
from .nist_structural_research import ACTION_TYPE, ACTION_VERSION, RESEARCH_ID

ACTION_REPORT_FILENAME = "action_result.json"
OUTPUT_RELATIVE_PATH = "structural_design_simulation.json"
REPORT_SCHEMA_VERSION = "1.0"
REQUEST_SCHEMA_VERSION = "1.0"
STOP_REASON = "physical_evidence_required"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_REQUEST_KEYS = {
    "schema_version",
    "action_id",
    "action_type",
    "research_run",
    "simulation_config",
    "registry",
    "repository_root",
    "expected_registry_sha256",
}
_FIXED_BOUNDARY = {
    "response_values_used": False,
    "synthetic_response_generated": False,
    "coefficients_estimated": False,
    "effect_sizes_estimated": False,
    "predictions_generated": False,
    "causal_effects_inferred": False,
    "optimization_performed": False,
    "engineering_decision_made": False,
}


class NistStructuralSimulationActionError(ResearchLoopError):
    """Raised when the bounded structural simulation action drifts."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _file_record(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    return {"path": str(resolved), "sha256": _sha256(resolved), "bytes": resolved.stat().st_size}


def _request_record(record: Mapping[str, Any], request_path: Path) -> dict[str, Any]:
    expected = _file_record(request_path)
    normalized = {
        "path": record.get("path"),
        "sha256": record.get("sha256"),
        "bytes": record.get("bytes"),
    }
    if normalized != expected:
        raise NistStructuralSimulationActionError("pinned request record does not match exact request bytes")
    return expected


def _path(raw: object, *, base: Path, field: str, directory: bool = False) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise NistStructuralSimulationActionError(f"{field} must be a non-empty path string")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    resolved = candidate.resolve(strict=True)
    if directory and not resolved.is_dir():
        raise NistStructuralSimulationActionError(f"{field} must resolve to a directory")
    if not directory and not resolved.is_file():
        raise NistStructuralSimulationActionError(f"{field} must resolve to a file")
    return resolved


def _validate_request(value: Mapping[str, Any], *, base: Path) -> dict[str, Any]:
    if set(value) != _REQUEST_KEYS:
        raise NistStructuralSimulationActionError("execution request has an invalid field set")
    if value.get("schema_version") != REQUEST_SCHEMA_VERSION:
        raise NistStructuralSimulationActionError("unsupported execution request schema")
    if value.get("action_type") != ACTION_TYPE:
        raise NistStructuralSimulationActionError("execution request action_type mismatch")
    action_id = value.get("action_id")
    if not isinstance(action_id, str) or _SAFE_ID.fullmatch(action_id) is None:
        raise NistStructuralSimulationActionError("execution request action_id is invalid")
    root = _path(value.get("repository_root"), base=base, field="repository_root", directory=True)
    run = _path(value.get("research_run"), base=base, field="research_run", directory=True)
    registry = _path(value.get("registry"), base=base, field="registry")
    config = _path(value.get("simulation_config"), base=base, field="simulation_config")
    try:
        registry.relative_to(root)
        config.relative_to(root)
    except ValueError as exc:
        raise NistStructuralSimulationActionError("registry and simulation_config must remain inside repository_root") from exc
    expected_sha = value.get("expected_registry_sha256")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64 or any(c not in "0123456789abcdef" for c in expected_sha):
        raise NistStructuralSimulationActionError("expected_registry_sha256 must be lowercase SHA-256 hex")
    return {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "action_id": action_id,
        "action_type": ACTION_TYPE,
        "repository_root": root,
        "research_run": run,
        "registry": registry,
        "simulation_config": config,
        "expected_registry_sha256": expected_sha,
    }


def _preflight(request_path: Path, request_value: Mapping[str, Any]) -> dict[str, Any]:
    request = _validate_request(request_value, base=request_path.parent)
    state = load_research_state(request["research_run"])
    if state.get("research_id") != RESEARCH_ID or state.get("status") != "active":
        raise NistStructuralSimulationActionError("research run is not the active frozen NIST structural run")
    if state.get("actions") != []:
        raise NistStructuralSimulationActionError("NIST structural run permits exactly one action")
    registry = load_action_registry(request["registry"], repository_root=request["repository_root"])
    if registry.get("registry_sha256") != request["expected_registry_sha256"]:
        raise NistStructuralSimulationActionError("action registry does not match pinned expected SHA-256")
    contract = describe_action(registry, ACTION_TYPE)
    if contract.get("version") != ACTION_VERSION or contract.get("availability") != "available":
        raise NistStructuralSimulationActionError("NIST structural action contract is not executable")
    if contract.get("category") != "simulation" or contract.get("cost_units") != 2:
        raise NistStructuralSimulationActionError("NIST structural action category or cost drifted")
    binding = contract.get("binding")
    if not isinstance(binding, Mapping) or binding.get("kind") != "source_script" or binding.get("path") != "src/materials_data_analyzer/research_loop/design_simulation.py":
        raise NistStructuralSimulationActionError("NIST structural action binding drifted")
    simulation = simulate_design_structure_file(request["simulation_config"])
    boundary = simulation.get("scientific_boundary")
    if not isinstance(boundary, Mapping):
        raise NistStructuralSimulationActionError("simulation omitted scientific boundary")
    for key, expected in _FIXED_BOUNDARY.items():
        if boundary.get(key) is not expected:
            raise NistStructuralSimulationActionError(f"simulation widened scientific authority: {key}")
    return {"request": request, "state": state, "registry": registry, "contract": contract, "simulation": simulation}


def _outcome(simulation: Mapping[str, Any]) -> str:
    after = simulation.get("after_proposal")
    if not isinstance(after, Mapping) or not isinstance(after.get("models"), list):
        return "structural_simulation_inconclusive"
    interaction = [item for item in after["models"] if isinstance(item, Mapping) and item.get("model") == "interaction"]
    if len(interaction) != 1:
        return "structural_simulation_inconclusive"
    return (
        "interaction_structurally_estimable_after_proposed_augmentation"
        if interaction[0].get("full_column_rank") is True
        else "interaction_remains_structurally_unestimable"
    )


def execute_nist_structural_design_simulation_action_preparsed(
    request_value: Mapping[str, Any],
    *,
    request_path: str | Path,
    request_record: Mapping[str, Any],
) -> dict[str, Any]:
    """Execute exactly one response-free structural simulation and stop the bounded run."""
    pinned_path = Path(request_path)
    if not pinned_path.is_absolute():
        raise NistStructuralSimulationActionError("pinned request_path must be absolute")
    pinned_record = _request_record(request_record, pinned_path)
    preflight = _preflight(pinned_path, request_value)
    request = preflight["request"]
    run: Path = request["research_run"]
    action_id = request["action_id"]
    action_directory = run / "actions" / action_id
    output_path = action_directory / OUTPUT_RELATIVE_PATH
    report_path = action_directory / ACTION_REPORT_FILENAME
    started = _utc_now()
    outcome = _outcome(preflight["simulation"])

    with transactional_output_directory(
        action_directory,
        protected_paths=(pinned_path, request["simulation_config"], request["registry"]),
        recognized_markers=(ACTION_REPORT_FILENAME,),
    ) as staging:
        staged_output = staging / OUTPUT_RELATIVE_PATH
        _write_json(staged_output, preflight["simulation"])
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "execution_status": "completed",
            "action_id": action_id,
            "action_type": ACTION_TYPE,
            "action_version": ACTION_VERSION,
            "cost_units": 2,
            "started_at_utc": started,
            "completed_at_utc": _utc_now(),
            "request": dict(pinned_record),
            "registry": {
                "registry_id": preflight["registry"]["registry_id"],
                "registry_path": preflight["registry"]["registry_path"],
                "registry_sha256": preflight["registry"]["registry_sha256"],
            },
            "research_run": str(run),
            "simulation_config": _file_record(request["simulation_config"]),
            "outcome": outcome,
            "output": {
                "relative_path": OUTPUT_RELATIVE_PATH,
                "path": str(output_path),
                "sha256": _sha256(staged_output),
                "bytes": staged_output.stat().st_size,
            },
            "scientific_boundary": {
                "response_values_used": False,
                "response_values_synthesized": False,
                "predictive_model_fitted": False,
                "causal_effects_estimated": False,
                "engineering_decision_authorized": False,
                "real_experimental_evidence_created": False,
                "simulation_satisfies_physical_acquisition_requirement": False,
                "proposed_design_counts_are_synthetic_evidence": False,
            },
            "stop_reason": STOP_REASON,
        }
        _write_json(staging / ACTION_REPORT_FILENAME, report)

    final_state = append_action_and_stop(
        run,
        action_id=action_id,
        action_type=ACTION_TYPE,
        status="completed",
        summary=(
            "Response-free design structure simulated and independently auditable; no measured "
            "trace or response evidence was created."
        ),
        cost_units=2,
        reason_code=STOP_REASON,
        stop_summary=(
            "Structural design uncertainty is reduced. Scientific progression still requires "
            "the nine authoritative physical traces defined by NIST AM-Bench issue #76."
        ),
        artifact_paths=[report_path, output_path],
    )
    return {
        "execution_status": "completed",
        "action_id": action_id,
        "outcome": outcome,
        "action_report": str(report_path),
        "simulation_output": str(output_path),
        "research_state": final_state,
    }


def verify_nist_structural_design_simulation_report(
    report_file: str | Path,
    *,
    request_value: Mapping[str, Any] | None = None,
    request_path: str | Path | None = None,
    request_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Recompute the simulation and verify report, output, request, registry, and ledger binding."""
    report_path = Path(report_file).expanduser().resolve(strict=True)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise NistStructuralSimulationActionError("invalid structural simulation action report")
    if report.get("execution_status") != "completed" or report.get("action_type") != ACTION_TYPE:
        raise NistStructuralSimulationActionError("structural simulation report identity mismatch")
    if report.get("action_version") != ACTION_VERSION or report.get("cost_units") != 2:
        raise NistStructuralSimulationActionError("structural simulation report contract mismatch")
    if report.get("stop_reason") != STOP_REASON:
        raise NistStructuralSimulationActionError("structural simulation report stop reason mismatch")
    boundary = report.get("scientific_boundary")
    required_boundary = {
        "response_values_used": False,
        "response_values_synthesized": False,
        "predictive_model_fitted": False,
        "causal_effects_estimated": False,
        "engineering_decision_authorized": False,
        "real_experimental_evidence_created": False,
        "simulation_satisfies_physical_acquisition_requirement": False,
        "proposed_design_counts_are_synthetic_evidence": False,
    }
    if boundary != required_boundary:
        raise NistStructuralSimulationActionError("structural simulation report widened scientific boundary")

    if request_value is None or request_path is None or request_record is None:
        request_binding = report.get("request")
        if not isinstance(request_binding, Mapping):
            raise NistStructuralSimulationActionError("report omitted request binding")
        pinned_path = Path(str(request_binding.get("path", ""))).expanduser().resolve(strict=True)
        raw = pinned_path.read_bytes()
        try:
            pinned_value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NistStructuralSimulationActionError("bound request is no longer valid JSON") from exc
        if not isinstance(pinned_value, dict):
            raise NistStructuralSimulationActionError("bound request root must remain an object")
        request_value = pinned_value
        request_path = pinned_path
        request_record = {"path": str(pinned_path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    pinned_path = Path(request_path).expanduser().resolve(strict=True)
    pinned_record = _request_record(request_record, pinned_path)
    if report.get("request") != pinned_record:
        raise NistStructuralSimulationActionError("report request binding mismatch")
    preflight = _preflight_for_verification(pinned_path, request_value)
    request = preflight["request"]
    if report.get("action_id") != request["action_id"] or report.get("research_run") != str(request["research_run"]):
        raise NistStructuralSimulationActionError("report does not match pinned action/run")
    expected_report = (request["research_run"] / "actions" / request["action_id"] / ACTION_REPORT_FILENAME).resolve(strict=True)
    if report_path != expected_report:
        raise NistStructuralSimulationActionError("report path is not the pinned action report path")
    expected_output = (report_path.parent / OUTPUT_RELATIVE_PATH).resolve(strict=True)
    output_record = report.get("output")
    if not isinstance(output_record, Mapping) or output_record.get("path") != str(expected_output):
        raise NistStructuralSimulationActionError("report output binding mismatch")
    if output_record.get("sha256") != _sha256(expected_output) or output_record.get("bytes") != expected_output.stat().st_size:
        raise NistStructuralSimulationActionError("simulation output bytes drifted")
    actual_output = json.loads(expected_output.read_text(encoding="utf-8"))
    if actual_output != preflight["simulation"]:
        raise NistStructuralSimulationActionError("simulation output is not recomputable from pinned config")
    if report.get("simulation_config") != _file_record(request["simulation_config"]):
        raise NistStructuralSimulationActionError("simulation config binding drifted")
    if report.get("outcome") != _outcome(preflight["simulation"]):
        raise NistStructuralSimulationActionError("simulation outcome is not recomputable")
    registry_expected = {
        "registry_id": preflight["registry"]["registry_id"],
        "registry_path": preflight["registry"]["registry_path"],
        "registry_sha256": preflight["registry"]["registry_sha256"],
    }
    if report.get("registry") != registry_expected:
        raise NistStructuralSimulationActionError("report registry binding drifted")
    state = load_research_state(request["research_run"])
    if state.get("status") != "stopped" or not isinstance(state.get("actions"), list):
        raise NistStructuralSimulationActionError("research run was not stopped after bounded simulation")
    matches = [item for item in state["actions"] if isinstance(item, Mapping) and item.get("action_id") == request["action_id"]]
    if len(matches) != 1 or matches[0].get("action_type") != ACTION_TYPE or matches[0].get("cost_units") != 2:
        raise NistStructuralSimulationActionError("ledger action binding mismatch")
    return {
        "verification_status": "verified",
        "action_id": request["action_id"],
        "action_type": ACTION_TYPE,
        "outcome": report["outcome"],
        "physical_evidence_requirement_satisfied": False,
        "scientific_evidence_upgraded": False,
    }


def _preflight_for_verification(request_path: Path, request_value: Mapping[str, Any]) -> dict[str, Any]:
    """Verification variant that accepts the expected stopped post-action research state."""
    request = _validate_request(request_value, base=request_path.parent)
    state = load_research_state(request["research_run"])
    if state.get("research_id") != RESEARCH_ID:
        raise NistStructuralSimulationActionError("research run identity drifted")
    registry = load_action_registry(request["registry"], repository_root=request["repository_root"])
    if registry.get("registry_sha256") != request["expected_registry_sha256"]:
        raise NistStructuralSimulationActionError("registry binding drifted")
    contract = describe_action(registry, ACTION_TYPE)
    if contract.get("version") != ACTION_VERSION or contract.get("cost_units") != 2:
        raise NistStructuralSimulationActionError("action contract drifted")
    simulation = simulate_design_structure_file(request["simulation_config"])
    return {"request": request, "state": state, "registry": registry, "contract": contract, "simulation": simulation}


__all__ = [
    "ACTION_REPORT_FILENAME",
    "ACTION_TYPE",
    "ACTION_VERSION",
    "NistStructuralSimulationActionError",
    "execute_nist_structural_design_simulation_action_preparsed",
    "verify_nist_structural_design_simulation_report",
]
