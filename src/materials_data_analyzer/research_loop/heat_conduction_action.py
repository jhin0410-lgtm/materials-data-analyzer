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
    "registry",
    "repository_root",
    "expected_registry_sha256",
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
    for field in ("expected_solver_request_sha256", "expected_registry_sha256"):
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
    state = load_research_state(run)
    if state.get("status") != "active":
        raise HeatConductionActionError("research run is not active")
    if any(item.get("action_type") == ACTION_TYPE for item in state.get("actions", [])):
        raise HeatConductionActionError("audited heat action may execute only once per research run")
    budget = state.get("budget")
    if not isinstance(budget, Mapping) or budget.get("actions_remaining", 0) <= 0 or budget.get("cost_units_remaining", 0) < COST_UNITS:
        raise HeatConductionActionError("research budget cannot fund heat simulation")
    result = run_reference_heat_conduction_request(solver_request)
    return {
        "request": request,
        "solver_request": solver_request,
        "solver_record": solver_record,
        "registry": registry,
        "contract": contract,
        "result": result,
    }


def execute_heat_conduction_action_preparsed(
    request_value: Mapping[str, Any],
    *,
    request_path: str | Path,
    request_record: Mapping[str, Any],
) -> dict[str, Any]:
    pinned_path = Path(request_path).expanduser().resolve(strict=True)
    if set(request_record) != {"path", "bytes", "sha256"} or request_record.get("path") != str(pinned_path):
        raise HeatConductionActionError("pinned typed execution request record is malformed")
    if not isinstance(request_record.get("sha256"), str) or _SHA256.fullmatch(str(request_record["sha256"])) is None:
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
    result_status = str(result.get("run_status"))
    ledger_status = "rejected" if result_status == "rejected_numerically_unstable" else "completed"
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
            "action_id": action_id,
            "action_type": ACTION_TYPE,
            "action_version": ACTION_VERSION,
            "cost_units": COST_UNITS,
            "started_at_utc": started,
            "completed_at_utc": _utc_now(),
            "request": dict(request_record),
            "solver_request": dict(preflight["solver_record"]),
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
            },
            "physics_solver": True,
            "empirical_validation_performed": False,
            "scientific_status_upgrade_authorized": False,
        }
        _write_json(staging / ACTION_REPORT_FILENAME, report)
    report_path = action_directory / ACTION_REPORT_FILENAME
    result_path = action_directory / OUTPUT_RELATIVE_PATH
    state = append_action(
        run,
        action_id=action_id,
        action_type=ACTION_TYPE,
        status=ledger_status,
        summary=(
            "Audited 1D heat-conduction reference simulation completed without empirical scientific promotion."
            if ledger_status == "completed"
            else "Audited 1D heat-conduction request was rejected by the FTCS stability gate."
        ),
        cost_units=COST_UNITS,
        artifact_paths=(report_path, result_path),
    )
    return {
        "action_report": str(report_path),
        "solver_result": str(result_path),
        "ledger_sha256": state["ledger_sha256"],
        "execution_status": ledger_status,
        "run_status": result_status,
    }


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
    request_file = Path(request_path).expanduser().resolve(strict=True)
    if report.get("request") != dict(request_record):
        raise HeatConductionActionError("action report request binding differs from pinned request")
    request = _validate_request(request_value, request_path=request_file)
    result_path = Path(str(report.get("solver_result", {}).get("path"))).expanduser().resolve(strict=True)
    expected_directory = request["research_run"] / "actions" / request["action_id"]
    _within(result_path, expected_directory, field="solver_result")
    result_bytes, result_record = _snapshot(result_path)
    result = _load_json_bytes(result_bytes, field="heat_solver_result")
    if report.get("solver_result", {}).get("sha256") != result_record["sha256"]:
        raise HeatConductionActionError("solver result artifact checksum drifted")
    solver_bytes, solver_record = _snapshot(request["solver_request"])
    if solver_record["sha256"] != request["expected_solver_request_sha256"]:
        raise HeatConductionActionError("solver input changed after execution")
    expected = run_reference_heat_conduction_request(_load_json_bytes(solver_bytes, field="solver_request"))
    if result != expected:
        raise HeatConductionActionError("persisted solver result differs from deterministic recomputation")
    if result.get("result_sha256") != report.get("solver_result", {}).get("result_sha256"):
        raise HeatConductionActionError("solver result canonical SHA binding drifted")
    return {
        "report_sha256": report_record["sha256"],
        "solver_result_sha256": result_record["sha256"],
        "solver_request_sha256": solver_record["sha256"],
        "result_sha256": result["result_sha256"],
        "run_status": result["run_status"],
        "validation_state": result["validation"]["state"],
        "deterministic_recomputation_verified": True,
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
