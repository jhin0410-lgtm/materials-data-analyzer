"""Typed response-free structural design simulation for NIST AM-Bench Stage 1."""
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
from .kernel import ResearchLoopError, append_action, load_research_state

ACTION_TYPE = "nist_structural_design_simulation"
ACTION_VERSION = "1.0"
ACTION_REPORT_FILENAME = "action_result.json"
REQUEST_SCHEMA_VERSION = "1.0"
REPORT_SCHEMA_VERSION = "1.0"
OUTPUT_RELATIVE_PATH = "reports/structural_design_simulation.json"
EXPECTED_SPEC_RELATIVE_PATH = (
    "configs/research/nist_ambench_stage1_structural_design_simulation.v1.json"
)
EXPECTED_BINDING_PATH = "scripts/run_nist_structural_design_action.py"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_REQUEST_KEYS = {
    "schema_version",
    "action_id",
    "action_type",
    "research_run",
    "simulation_spec",
    "expected_simulation_spec_sha256",
    "registry",
    "repository_root",
    "expected_registry_sha256",
}
_REQUIRED_BOUNDARY_FALSE = (
    "response_values_used",
    "synthetic_response_generated",
    "coefficients_estimated",
    "effect_sizes_estimated",
    "predictions_generated",
    "causal_effects_inferred",
    "optimization_performed",
    "engineering_decision_made",
)


class NistStructuralDesignActionError(ResearchLoopError):
    """Raised when the fixed NIST structural-simulation action contract drifts."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_record(path: Path) -> dict[str, Any]:
    """Bind one file from one byte snapshot rather than separate stat/hash reads."""
    resolved = path.resolve(strict=True)
    data = resolved.read_bytes()
    return {
        "path": str(resolved),
        "bytes": len(data),
        "sha256": _sha256_bytes(data),
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _validate_request_record(
    record: Mapping[str, Any], *, request_path: Path
) -> dict[str, Any]:
    expected = {"path", "bytes", "sha256"}
    if set(record) != expected or record.get("path") != str(request_path):
        raise NistStructuralDesignActionError("pinned request record is malformed")
    size = record.get("bytes")
    digest = record.get("sha256")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise NistStructuralDesignActionError("pinned request byte count is invalid")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise NistStructuralDesignActionError("pinned request SHA-256 is invalid")
    return dict(record)


def _resolve_path(raw: object, *, field: str, base: Path) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise NistStructuralDesignActionError(f"{field} must be a path string")
    value = Path(raw).expanduser()
    if not value.is_absolute():
        value = base / value
    return value.resolve(strict=True)


def _ensure_within(path: Path, parent: Path, *, field: str) -> None:
    try:
        path.relative_to(parent)
    except ValueError as exc:
        raise NistStructuralDesignActionError(f"{field} escapes required root") from exc


def _validate_request(value: Mapping[str, Any], *, base: Path) -> dict[str, Any]:
    if set(value) != _REQUEST_KEYS:
        missing = sorted(_REQUEST_KEYS - set(value))
        extra = sorted(set(value) - _REQUEST_KEYS)
        raise NistStructuralDesignActionError(
            f"execution request field set drifted; missing={missing}, extra={extra}"
        )
    if value.get("schema_version") != REQUEST_SCHEMA_VERSION:
        raise NistStructuralDesignActionError("unsupported execution request schema")
    action_id = value.get("action_id")
    if not isinstance(action_id, str) or not _SAFE_ID.fullmatch(action_id):
        raise NistStructuralDesignActionError("action_id is not executor-safe")
    if value.get("action_type") != ACTION_TYPE:
        raise NistStructuralDesignActionError(
            f"this action accepts only {ACTION_TYPE!r}"
        )
    for key in ("expected_registry_sha256", "expected_simulation_spec_sha256"):
        digest = value.get(key)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise NistStructuralDesignActionError(f"{key} must be lowercase SHA-256 hex")
    return {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "action_id": action_id,
        "action_type": ACTION_TYPE,
        "research_run": _resolve_path(
            value["research_run"], field="research_run", base=base
        ),
        "simulation_spec": _resolve_path(
            value["simulation_spec"], field="simulation_spec", base=base
        ),
        "expected_simulation_spec_sha256": value[
            "expected_simulation_spec_sha256"
        ],
        "registry": _resolve_path(value["registry"], field="registry", base=base),
        "repository_root": _resolve_path(
            value["repository_root"], field="repository_root", base=base
        ),
        "expected_registry_sha256": value["expected_registry_sha256"],
    }


def _verify_result_boundary(result: Mapping[str, Any]) -> None:
    boundary = result.get("scientific_boundary")
    if not isinstance(boundary, Mapping):
        raise NistStructuralDesignActionError("simulation scientific boundary is missing")
    for field in _REQUIRED_BOUNDARY_FALSE:
        if boundary.get(field) is not False:
            raise NistStructuralDesignActionError(
                f"response-free simulation widened scientific authority: {field}"
            )
    comparison = result.get("comparison")
    if not isinstance(comparison, Mapping):
        raise NistStructuralDesignActionError("simulation comparison is missing")
    if (
        comparison.get("new_unique_cell_count") != 3
        or comparison.get("new_replicate_count") != 9
    ):
        raise NistStructuralDesignActionError("Stage 1 proposal dimensions drifted")
    before = result.get("before")
    after = result.get("after_proposal")
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        raise NistStructuralDesignActionError(
            "simulation before/after summaries are missing"
        )
    before_grid = before.get("grid")
    after_grid = after.get("grid")
    if not isinstance(before_grid, Mapping) or not isinstance(after_grid, Mapping):
        raise NistStructuralDesignActionError("simulation grid summaries are missing")
    if (
        before_grid.get("total_replicates") != 10
        or after_grid.get("total_replicates") != 19
    ):
        raise NistStructuralDesignActionError("NIST structural replicate counts drifted")
    changes = comparison.get("model_changes")
    if not isinstance(changes, list):
        raise NistStructuralDesignActionError("simulation model changes are missing")
    by_model = {
        item.get("model"): item for item in changes if isinstance(item, Mapping)
    }
    interaction = by_model.get("interaction")
    quadratic = by_model.get("quadratic")
    if not isinstance(interaction, Mapping) or not isinstance(quadratic, Mapping):
        raise NistStructuralDesignActionError("required structural models are missing")
    if (
        interaction.get("rank_before") != 3
        or interaction.get("rank_after") != 4
        or interaction.get("full_column_rank_before") is not False
        or interaction.get("full_column_rank_after") is not True
        or interaction.get("residual_df_before") != 7
        or interaction.get("residual_df_after") != 15
    ):
        raise NistStructuralDesignActionError("interaction structural result drifted")
    if (
        quadratic.get("rank_after") != 5
        or quadratic.get("full_column_rank_after") is not False
    ):
        raise NistStructuralDesignActionError("quadratic structural limitation drifted")
    gain = result.get("expected_information_gain")
    if (
        not isinstance(gain, Mapping)
        or gain.get("status") != "not_quantified"
        or gain.get("value") is not None
    ):
        raise NistStructuralDesignActionError(
            "structural simulation must not claim quantified information gain"
        )


def _preflight(request_path: Path, request_value: Mapping[str, Any]) -> dict[str, Any]:
    request = _validate_request(request_value, base=request_path.parent)
    run = request["research_run"]
    root = request["repository_root"]
    if not run.is_dir() or not root.is_dir():
        raise NistStructuralDesignActionError(
            "research_run/repository_root must be directories"
        )
    _ensure_within(request["simulation_spec"], root, field="simulation_spec")
    expected_spec = (root / EXPECTED_SPEC_RELATIVE_PATH).resolve(strict=True)
    if request["simulation_spec"] != expected_spec:
        raise NistStructuralDesignActionError(
            "request is not bound to the frozen NIST Stage 1 spec"
        )
    state = load_research_state(run)
    if state.get("status") != "active":
        raise NistStructuralDesignActionError("research run is not active")
    if any(item.get("action_type") == ACTION_TYPE for item in state.get("actions", [])):
        raise NistStructuralDesignActionError(
            "structural simulation may execute only once per run"
        )
    registry = load_action_registry(request["registry"], repository_root=root)
    if registry["registry_sha256"] != request["expected_registry_sha256"]:
        raise NistStructuralDesignActionError("execution registry binding drifted")
    contract = describe_action(registry, ACTION_TYPE)
    if (
        contract.get("version") != ACTION_VERSION
        or contract.get("availability") != "available"
        or contract.get("cost_units") != 1
    ):
        raise NistStructuralDesignActionError("registered action contract drifted")
    binding = contract.get("binding")
    if (
        not isinstance(binding, Mapping)
        or binding.get("kind") != "source_script"
        or binding.get("path") != EXPECTED_BINDING_PATH
    ):
        raise NistStructuralDesignActionError("NIST typed-action binding drifted")
    if (
        state["budget"]["actions_remaining"] <= 0
        or state["budget"]["cost_units_remaining"] < 1
    ):
        raise NistStructuralDesignActionError(
            "research budget cannot fund structural simulation"
        )

    result = simulate_design_structure_file(expected_spec)
    expected_spec_binding = {
        "path": str(expected_spec),
        "sha256": request["expected_simulation_spec_sha256"],
    }
    if result.get("simulation_spec_binding") != expected_spec_binding:
        raise NistStructuralDesignActionError(
            "simulation did not consume the exact request-pinned NIST spec bytes"
        )
    spec_record = _file_record(expected_spec)
    if spec_record["sha256"] != request["expected_simulation_spec_sha256"]:
        raise NistStructuralDesignActionError(
            "NIST simulation spec changed after the simulation snapshot"
        )
    _verify_result_boundary(result)
    return {
        "request": request,
        "state": state,
        "registry": registry,
        "contract": contract,
        "result": result,
        "spec_record": spec_record,
    }


def execute_nist_structural_design_action_preparsed(
    request_value: Mapping[str, Any],
    *,
    request_path: str | Path,
    request_record: Mapping[str, Any],
) -> dict[str, Any]:
    pinned_path = Path(request_path)
    if not pinned_path.is_absolute():
        raise NistStructuralDesignActionError("pinned request_path must be absolute")
    pinned_record = _validate_request_record(request_record, request_path=pinned_path)
    preflight = _preflight(pinned_path, request_value)
    request = preflight["request"]
    run = request["research_run"]
    action_id = request["action_id"]
    action_directory = run / "actions" / action_id
    if action_directory.exists():
        raise FileExistsError(f"action output already exists: {action_directory}")
    result_path = action_directory / OUTPUT_RELATIVE_PATH
    report_path = action_directory / ACTION_REPORT_FILENAME
    started = _utc_now()
    with transactional_output_directory(
        action_directory,
        protected_paths=(pinned_path, request["simulation_spec"], request["registry"]),
        recognized_markers=(ACTION_REPORT_FILENAME,),
    ) as staging:
        staged_result = staging / OUTPUT_RELATIVE_PATH
        _write_json(staged_result, preflight["result"])
        staged_result_record = _file_record(staged_result)
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "execution_status": "completed",
            "action_id": action_id,
            "action_type": ACTION_TYPE,
            "action_version": ACTION_VERSION,
            "cost_units": 1,
            "started_at_utc": started,
            "completed_at_utc": _utc_now(),
            "request": dict(pinned_record),
            "registry": {
                "registry_id": preflight["registry"]["registry_id"],
                "registry_path": preflight["registry"]["registry_path"],
                "registry_sha256": preflight["registry"]["registry_sha256"],
            },
            "research_run": str(run),
            "immutable_inputs": [preflight["spec_record"]],
            "simulation_result": preflight["result"],
            "output": {
                "relative_path": OUTPUT_RELATIVE_PATH,
                "path": str(result_path),
                "bytes": staged_result_record["bytes"],
                "sha256": staged_result_record["sha256"],
            },
            "physical_evidence_requirement": {
                "satisfied": False,
                "required_real_trace_count": 9,
                "required_new_conditions": [
                    {
                        "actual_laser_power_w": 137.9,
                        "scan_speed_mm_s": 800.0,
                        "minimum_traces": 3,
                    },
                    {
                        "actual_laser_power_w": 137.9,
                        "scan_speed_mm_s": 1200.0,
                        "minimum_traces": 3,
                    },
                    {
                        "actual_laser_power_w": 179.2,
                        "scan_speed_mm_s": 400.0,
                        "minimum_traces": 3,
                    },
                ],
                "synthetic_or_simulated_trace_substitution_allowed": False,
            },
            "scientific_evidence_upgraded": False,
            "maximum_allowed_use_after_action": (
                "descriptive_and_structural_design_diagnostic"
            ),
        }
        _write_json(staging / ACTION_REPORT_FILENAME, report)
    final_state = append_action(
        run,
        action_id=action_id,
        action_type=ACTION_TYPE,
        status="completed",
        summary=(
            "Response-free Stage 1 structural estimability was audited. "
            "Nine real physical traces remain required."
        ),
        cost_units=1,
        artifact_paths=[report_path, result_path],
    )
    return {
        "execution_status": "completed",
        "action_id": action_id,
        "action_report": str(report_path),
        "simulation_result": str(result_path),
        "research_state": final_state,
    }


__all__ = [
    "ACTION_TYPE",
    "ACTION_VERSION",
    "NistStructuralDesignActionError",
    "execute_nist_structural_design_action_preparsed",
]
