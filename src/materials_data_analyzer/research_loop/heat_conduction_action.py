"""Typed, checksum-bound execution wrapper for the audited 1D heat solver."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from platform_core.output_safety import transactional_output_directory

from .action_registry import describe_action, load_action_registry
from .heat_conduction_solver import (
    HEAT_SOLVER_ACTION_TYPE as ACTION_TYPE,
    HEAT_SOLVER_ACTION_VERSION as ACTION_VERSION,
    run_reference_heat_conduction_request,
)
from .kernel import ResearchLoopError, append_action, load_research_state

REQUEST_SCHEMA_VERSION = "1.0"
REPORT_SCHEMA_VERSION = "1.0"
ACTION_REPORT_FILENAME = "action_result.json"
OUTPUT_RELATIVE_PATH = "reports/heat_conduction_result.json"
EXPECTED_BINDING_PATH = "scripts/run_reference_heat_conduction_action.py"
COST_UNITS = 1
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_KEYS = {
    "schema_version",
    "action_id",
    "action_type",
    "action_version",
    "research_run",
    "solver_request",
    "expected_solver_request_sha256",
    "expected_solver_implementation_sha256",
    "registry",
    "repository_root",
    "expected_registry_sha256",
}
_REPORT_KEYS = {
    "schema_version",
    "execution_status",
    "registered_outcome",
    "action_id",
    "action_type",
    "action_version",
    "cost_units",
    "started_at_utc",
    "completed_at_utc",
    "request",
    "solver_request",
    "solver_implementation",
    "registry",
    "solver_result",
    "physics_solver",
    "empirical_validation_performed",
    "scientific_status_upgrade_authorized",
}


class HeatConductionActionError(ResearchLoopError):
    """Raised when a typed heat-solver action or its byte bindings drift."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _snapshot(path: Path) -> tuple[bytes, dict[str, Any]]:
    resolved = path.resolve(strict=True)
    data = resolved.read_bytes()
    return data, {"path": str(resolved), "bytes": len(data), "sha256": _sha256_bytes(data)}


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _resolve(raw: object, *, field: str, base: Path) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise HeatConductionActionError(f"{field} must be a path string")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve(strict=True)


def _within(path: Path, parent: Path, *, field: str) -> None:
    try:
        path.relative_to(parent)
    except ValueError as exc:
        raise HeatConductionActionError(f"{field} escapes required root") from exc


def _load_json_bytes(data: bytes, *, field: str) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HeatConductionActionError(f"{field} must be UTF-8 JSON") from exc

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise HeatConductionActionError(f"duplicate JSON key in {field}: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(text, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as exc:
        raise HeatConductionActionError(f"invalid {field} JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise HeatConductionActionError(f"{field} root must be an object")
    return value


def _solver_implementation_contract() -> dict[str, str]:
    from .scientific_simulation_registry import repository_heat_conduction_contract

    contract = repository_heat_conduction_contract()
    return {
        "solver_id": contract.solver_id,
        "solver_version": contract.version,
        "implementation_qualname": contract.implementation_qualname,
        "implementation_module_sha256": contract.implementation_module_sha256,
    }


def _registered_outcome(result: Mapping[str, Any]) -> str:
    run_status = result.get("run_status")
    validation = result.get("validation")
    if not isinstance(validation, Mapping):
        raise HeatConductionActionError("heat result validation block is malformed")
    validation_state = validation.get("state")
    if run_status == "rejected_numerically_unstable":
        if validation_state != "not_run_due_to_stability_rejection":
            raise HeatConductionActionError("unstable heat result validation state drifted")
        return "rejected_numerically_unstable"
    if run_status != "completed":
        raise HeatConductionActionError("heat result run_status is not registered")
    if validation_state == "passed":
        return "numerically_validated_reference_solution"
    if validation_state == "failed":
        return "numerical_validation_failed"
    raise HeatConductionActionError(
        "audited heat action requires an explicit passed or failed numerical validation outcome"
    )


def _validate_request(value: Mapping[str, Any], *, request_path: Path) -> dict[str, Any]:
    if set(value) != _REQUEST_KEYS:
        raise HeatConductionActionError("typed heat execution request field set drifted")
    if value.get("schema_version") != REQUEST_SCHEMA_VERSION:
        raise HeatConductionActionError("unsupported typed heat execution request schema")
    action_id = value.get("action_id")
    if not isinstance(action_id, str) or _SAFE_ID.fullmatch(action_id) is None:
        raise HeatConductionActionError("action_id is not executor-safe")
    if value.get("action_type") != ACTION_TYPE or value.get("action_version") != ACTION_VERSION:
        raise HeatConductionActionError("heat action type/version binding drifted")
    for field in (
        "expected_solver_request_sha256",
        "expected_solver_implementation_sha256",
        "expected_registry_sha256",
    ):
        digest = value.get(field)
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise HeatConductionActionError(f"{field} must be lowercase SHA-256")
    base = request_path.parent
    return {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "action_id": action_id,
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "research_run": _resolve(value["research_run"], field="research_run", base=base),
        "solver_request": _resolve(value["solver_request"], field="solver_request", base=base),
        "expected_solver_request_sha256": value["expected_solver_request_sha256"],
        "expected_solver_implementation_sha256": value["expected_solver_implementation_sha256"],
        "registry": _resolve(value["registry"], field="registry", base=base),
        "repository_root": _resolve(value["repository_root"], field="repository_root", base=base),
        "expected_registry_sha256": value["expected_registry_sha256"],
    }


def _preflight(request_value: Mapping[str, Any], *, request_path: Path) -> dict[str, Any]:
    request = _validate_request(request_value, request_path=request_path)
    run = request["research_run"]
    root = request["repository_root"]
    if not run.is_dir() or not root.is_dir():
        raise HeatConductionActionError("research_run and repository_root must be directories")
    _within(request["solver_request"], root, field="solver_request")
    _within(request["registry"], root, field="registry")
    solver_bytes, solver_record = _snapshot(request["solver_request"])
    if solver_record["sha256"] != request["expected_solver_request_sha256"]:
        raise HeatConductionActionError("solver request bytes differ from the pinned SHA-256")
    solver_request = _load_json_bytes(solver_bytes, field="solver_request")

    implementation = _solver_implementation_contract()
    if (
        implementation["implementation_module_sha256"]
        != request["expected_solver_implementation_sha256"]
    ):
        raise HeatConductionActionError(
            "solver implementation bytes differ from the pinned SHA-256"
        )

    registry = load_action_registry(request["registry"], repository_root=root)
    if registry["registry_sha256"] != request["expected_registry_sha256"]:
        raise HeatConductionActionError("execution registry binding drifted")
    if registry.get("domain") != "reference_heat_conduction_physics":
        raise HeatConductionActionError("heat execution registry domain drifted")
    contract = describe_action(registry, ACTION_TYPE)
    binding = contract.get("binding")
    if (
        contract.get("version") != ACTION_VERSION
        or contract.get("availability") != "available"
        or contract.get("cost_units") != COST_UNITS
        or not isinstance(binding, Mapping)
        or binding.get("kind") != "source_script"
        or binding.get("path") != EXPECTED_BINDING_PATH
    ):
        raise HeatConductionActionError("registered heat action contract drifted")
    allowed_outcomes = contract.get("allowed_outcomes")
    if not isinstance(allowed_outcomes, list) or any(
        not isinstance(item, str) for item in allowed_outcomes
    ):
        raise HeatConductionActionError("registered heat allowed_outcomes contract is malformed")

    state = load_research_state(run)
    if state.get("status") != "active":
        raise HeatConductionActionError("research run is not active")
    actions = state.get("actions")
    if not isinstance(actions, list):
        raise HeatConductionActionError("research action ledger is malformed")
    if any(
        isinstance(item, Mapping) and item.get("action_type") == ACTION_TYPE
        for item in actions
    ):
        raise HeatConductionActionError("audited heat action may execute only once per research run")
    budget = state.get("budget")
    if (
        not isinstance(budget, Mapping)
        or budget.get("actions_remaining", 0) <= 0
        or budget.get("cost_units_remaining", 0) < COST_UNITS
    ):
        raise HeatConductionActionError("research budget cannot fund heat simulation")

    result = run_reference_heat_conduction_request(solver_request)
    outcome = _registered_outcome(result)
    if outcome not in allowed_outcomes:
        raise HeatConductionActionError(
            "heat solver outcome is not permitted by the pinned action registry"
        )
    return {
        "request": request,
        "solver_request": solver_request,
        "solver_record": solver_record,
        "solver_implementation": implementation,
        "registry": registry,
        "contract": contract,
        "result": result,
        "registered_outcome": outcome,
    }


def execute_heat_conduction_action_preparsed(
    request_value: Mapping[str, Any],
    *,
    request_path: str | Path,
    request_record: Mapping[str, Any],
) -> dict[str, Any]:
    pinned_path = Path(request_path).expanduser().resolve(strict=True)
    if (
        set(request_record) != {"path", "bytes", "sha256"}
        or request_record.get("path") != str(pinned_path)
    ):
        raise HeatConductionActionError("pinned typed execution request record is malformed")
    if (
        not isinstance(request_record.get("sha256"), str)
        or _SHA256.fullmatch(str(request_record["sha256"])) is None
    ):
        raise HeatConductionActionError("pinned typed execution request SHA-256 is malformed")
    preflight = _preflight(request_value, request_path=pinned_path)
    request = preflight["request"]
    run = request["research_run"]
    action_id = request["action_id"]
    action_directory = run / "actions" / action_id
    if action_directory.exists():
        raise FileExistsError(f"action output already exists: {action_directory}")
    started = _utc_now()
    result = preflight["result"]
    outcome = str(preflight["registered_outcome"])
    result_status = str(result.get("run_status"))
    ledger_status = (
        "completed"
        if outcome == "numerically_validated_reference_solution"
        else "rejected"
    )
    with transactional_output_directory(
        action_directory,
        protected_paths=(pinned_path, request["solver_request"], request["registry"]),
        recognized_markers=(ACTION_REPORT_FILENAME,),
    ) as staging:
        staged_result = staging / OUTPUT_RELATIVE_PATH
        _write_json(staged_result, result)
        _, staged_result_record = _snapshot(staged_result)
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "execution_status": ledger_status,
            "registered_outcome": outcome,
            "action_id": action_id,
            "action_type": ACTION_TYPE,
            "action_version": ACTION_VERSION,
            "cost_units": COST_UNITS,
            "started_at_utc": started,
            "completed_at_utc": _utc_now(),
            "request": dict(request_record),
            "solver_request": dict(preflight["solver_record"]),
            "solver_implementation": dict(preflight["solver_implementation"]),
            "registry": {
                "registry_id": preflight["registry"]["registry_id"],
                "registry_sha256": preflight["registry"]["registry_sha256"],
                "registry_path": preflight["registry"]["registry_path"],
            },
            "solver_result": {
                "path": str(action_directory / OUTPUT_RELATIVE_PATH),
                "sha256": staged_result_record["sha256"],
                "bytes": staged_result_record["bytes"],
                "result_sha256": result["result_sha256"],
                "run_status": result_status,
                "validation_state": result["validation"]["state"],
                "registered_outcome": outcome,
            },
            "physics_solver": True,
            "empirical_validation_performed": False,
            "scientific_status_upgrade_authorized": False,
        }
        _write_json(staging / ACTION_REPORT_FILENAME, report)
    report_path = action_directory / ACTION_REPORT_FILENAME
    result_path = action_directory / OUTPUT_RELATIVE_PATH
    summary_by_outcome = {
        "numerically_validated_reference_solution": (
            "Audited 1D heat-conduction reference simulation passed its declared numerical validation; no empirical scientific promotion occurred."
        ),
        "numerical_validation_failed": (
            "Audited 1D heat-conduction reference simulation completed but failed its declared numerical validation and was retained as rejected numerical evidence."
        ),
        "rejected_numerically_unstable": (
            "Audited 1D heat-conduction request was rejected by the FTCS stability gate before spatial allocation or time marching."
        ),
    }
    state = append_action(
        run,
        action_id=action_id,
        action_type=ACTION_TYPE,
        status=ledger_status,
        summary=summary_by_outcome[outcome],
        cost_units=COST_UNITS,
        artifact_paths=(report_path, result_path),
    )
    return {
        "action_report": str(report_path),
        "solver_result": str(result_path),
        "ledger_sha256": state["ledger_sha256"],
        "execution_status": ledger_status,
        "registered_outcome": outcome,
        "run_status": result_status,
    }


def _ledger_artifact_record(
    *,
    state: Mapping[str, Any],
    action_id: str,
    action_type: str,
    expected_status: str,
    path: Path,
) -> dict[str, Any]:
    actions = state.get("actions")
    if not isinstance(actions, list):
        raise HeatConductionActionError("research action ledger is malformed")
    matches = [
        item
        for item in actions
        if isinstance(item, Mapping) and item.get("action_id") == action_id
    ]
    if len(matches) != 1:
        raise HeatConductionActionError("exactly one ledger action binding is required")
    action = matches[0]
    if action.get("action_type") != action_type or action.get("status") != expected_status:
        raise HeatConductionActionError("ledger action identity/status differs from action report")
    artifacts = action.get("artifacts")
    if not isinstance(artifacts, list):
        raise HeatConductionActionError("ledger action artifact bindings are malformed")
    records = [
        dict(item)
        for item in artifacts
        if isinstance(item, Mapping) and item.get("path") == str(path)
    ]
    if len(records) != 1:
        raise HeatConductionActionError("action artifact is not uniquely bound in the research ledger")
    return records[0]


def verify_heat_conduction_action_report_pinned(
    report_path: str | Path,
    *,
    request_value: Mapping[str, Any],
    request_path: str | Path,
    request_record: Mapping[str, Any],
) -> dict[str, Any]:
    path = Path(report_path).expanduser().resolve(strict=True)
    data, report_record = _snapshot(path)
    report = _load_json_bytes(data, field="heat_action_report")
    if set(report) != _REPORT_KEYS:
        raise HeatConductionActionError("heat action report field set drifted")
    request_file = Path(request_path).expanduser().resolve(strict=True)
    request = _validate_request(request_value, request_path=request_file)
    expected_directory = request["research_run"] / "actions" / request["action_id"]
    expected_report_path = (expected_directory / ACTION_REPORT_FILENAME).resolve(strict=True)
    if path != expected_report_path:
        raise HeatConductionActionError("heat action report path differs from typed request")
    if report.get("request") != dict(request_record):
        raise HeatConductionActionError("action report request binding differs from pinned request")
    if (
        report.get("schema_version") != REPORT_SCHEMA_VERSION
        or report.get("action_id") != request["action_id"]
        or report.get("action_type") != ACTION_TYPE
        or report.get("action_version") != ACTION_VERSION
        or report.get("cost_units") != COST_UNITS
        or report.get("physics_solver") is not True
        or report.get("empirical_validation_performed") is not False
        or report.get("scientific_status_upgrade_authorized") is not False
    ):
        raise HeatConductionActionError("heat action report identity or scientific boundary drifted")
    for field in ("started_at_utc", "completed_at_utc"):
        if not isinstance(report.get(field), str) or not str(report[field]).strip():
            raise HeatConductionActionError(f"heat action report {field} is malformed")

    solver_bytes, solver_record = _snapshot(request["solver_request"])
    if solver_record["sha256"] != request["expected_solver_request_sha256"]:
        raise HeatConductionActionError("solver input changed after execution")
    if report.get("solver_request") != solver_record:
        raise HeatConductionActionError("action report solver-request binding drifted")

    implementation = _solver_implementation_contract()
    if (
        implementation["implementation_module_sha256"]
        != request["expected_solver_implementation_sha256"]
        or report.get("solver_implementation") != implementation
    ):
        raise HeatConductionActionError("solver implementation binding drifted after execution")

    registry = load_action_registry(request["registry"], repository_root=request["repository_root"])
    expected_registry = {
        "registry_id": registry["registry_id"],
        "registry_sha256": registry["registry_sha256"],
        "registry_path": registry["registry_path"],
    }
    if (
        registry["registry_sha256"] != request["expected_registry_sha256"]
        or report.get("registry") != expected_registry
    ):
        raise HeatConductionActionError("action report execution-registry binding drifted")
    contract = describe_action(registry, ACTION_TYPE)

    solver_result = report.get("solver_result")
    if not isinstance(solver_result, Mapping):
        raise HeatConductionActionError("heat action report solver_result is malformed")
    if set(solver_result) != {
        "path",
        "sha256",
        "bytes",
        "result_sha256",
        "run_status",
        "validation_state",
        "registered_outcome",
    }:
        raise HeatConductionActionError("heat action report solver_result field set drifted")
    result_path = Path(str(solver_result["path"])).expanduser().resolve(strict=True)
    expected_result_path = (expected_directory / OUTPUT_RELATIVE_PATH).resolve(strict=True)
    if result_path != expected_result_path:
        raise HeatConductionActionError("solver result path differs from typed action contract")
    result_bytes, result_record = _snapshot(result_path)
    if (
        solver_result.get("sha256") != result_record["sha256"]
        or solver_result.get("bytes") != result_record["bytes"]
    ):
        raise HeatConductionActionError("solver result artifact checksum/size drifted")
    result = _load_json_bytes(result_bytes, field="heat_solver_result")
    expected = run_reference_heat_conduction_request(
        _load_json_bytes(solver_bytes, field="solver_request")
    )
    if result != expected:
        raise HeatConductionActionError(
            "persisted solver result differs from deterministic recomputation"
        )
    outcome = _registered_outcome(result)
    allowed_outcomes = contract.get("allowed_outcomes")
    if not isinstance(allowed_outcomes, list) or outcome not in allowed_outcomes:
        raise HeatConductionActionError("recomputed heat outcome is not registry-authorized")
    expected_status = (
        "completed"
        if outcome == "numerically_validated_reference_solution"
        else "rejected"
    )
    if (
        report.get("execution_status") != expected_status
        or report.get("registered_outcome") != outcome
        or solver_result.get("result_sha256") != result.get("result_sha256")
        or solver_result.get("run_status") != result.get("run_status")
        or solver_result.get("validation_state") != result.get("validation", {}).get("state")
        or solver_result.get("registered_outcome") != outcome
    ):
        raise HeatConductionActionError("heat action report registered outcome/result binding drifted")

    state = load_research_state(request["research_run"])
    report_ledger_record = _ledger_artifact_record(
        state=state,
        action_id=request["action_id"],
        action_type=ACTION_TYPE,
        expected_status=expected_status,
        path=path,
    )
    result_ledger_record = _ledger_artifact_record(
        state=state,
        action_id=request["action_id"],
        action_type=ACTION_TYPE,
        expected_status=expected_status,
        path=result_path,
    )
    if report_ledger_record != report_record or result_ledger_record != result_record:
        raise HeatConductionActionError(
            "current heat action artifacts differ from immutable research-ledger bindings"
        )

    return {
        "report_sha256": report_record["sha256"],
        "solver_result_sha256": result_record["sha256"],
        "solver_request_sha256": solver_record["sha256"],
        "solver_implementation_sha256": implementation["implementation_module_sha256"],
        "result_sha256": result["result_sha256"],
        "run_status": result["run_status"],
        "validation_state": result["validation"]["state"],
        "registered_outcome": outcome,
        "deterministic_recomputation_verified": True,
        "ledger_artifact_binding_verified": True,
        "physics_solver": True,
        "empirical_validation_performed": False,
        "scientific_status_upgrade_authorized": False,
    }


__all__ = [
    "ACTION_TYPE",
    "ACTION_VERSION",
    "COST_UNITS",
    "HeatConductionActionError",
    "execute_heat_conduction_action_preparsed",
    "verify_heat_conduction_action_report_pinned",
]
