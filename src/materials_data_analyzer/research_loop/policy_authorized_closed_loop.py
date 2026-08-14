"""Policy-authorized closed-loop research orchestration.

This module closes one deliberately narrow autonomous loop:

    immutable authority snapshot -> epistemic gate -> planner/authorization
    -> one pinned typed local action -> pinned result verification
    -> record-only immutable graph successor -> re-gate/replan.

Execution requests, mission/runtime authority, record semantics, and the gated base
knowledge state are carried as exact snapshots across every side effect.  The loop
never invents execution requests, directional scientific inference, domain
verification, network actions, generic commands, or physical experiment execution.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

from .epistemic_gate import evaluate_epistemic_gate
from .epistemic_graph import evaluate_epistemic_graph, validate_epistemic_graph
from .kernel import ResearchLoopError, load_research_state
from .multicycle import load_request_queue
from .pinned_cycle_execution import run_pinned_research_cycle
from .research_cycle import run_research_cycle
from .research_program import build_research_program

CLOSED_LOOP_SCHEMA_VERSION = "1.0"
CLOSED_LOOP_POLICY_VERSION = "1.2"
RESULT_RECORD_PLAN_SCHEMA_VERSION = "1.1"

_DEFAULT_MAX_CYCLES = 8
_HARD_MAX_CYCLES = 32
_TERMINAL_PROBE_STATUSES = {
    "stopped_current_scope",
    "manual_review_required",
    "blocked",
    "authorization_denied",
}
_LOCAL_RESULT_TYPES = {
    ("analysis", "authorized_local_analysis"),
    ("simulation", "authorized_local_simulation"),
}
_LOCAL_ACTION_CLASSES = {
    "existing_data_reanalysis",
    "computational_experiment",
    "sensitivity_analysis",
    "simulation",
    "replication",
}
_MUTABLE_PROGRAM_EVIDENCE_ROLES = {"research_state", "research_ledger"}
_TARGET_TYPES = {"hypothesis", "claim", "conclusion"}


class PolicyAuthorizedClosedLoopError(ResearchLoopError):
    """Raised when the bounded closed-loop contract cannot be preserved."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PolicyAuthorizedClosedLoopError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_file_snapshot(path: Path) -> tuple[bytes, str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PolicyAuthorizedClosedLoopError(f"could not read snapshot source: {path}") from exc
    return raw, _sha256_bytes(raw)


def _parse_json_snapshot(raw: bytes, path: Path) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PolicyAuthorizedClosedLoopError(f"invalid UTF-8 in {path}: {exc}") from exc
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise PolicyAuthorizedClosedLoopError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PolicyAuthorizedClosedLoopError(f"JSON root must be an object: {path}")
    return value


def _read_json_snapshot(path: Path) -> tuple[dict[str, Any], bytes, str]:
    raw, digest = _read_file_snapshot(path)
    return _parse_json_snapshot(raw, path), raw, digest


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolicyAuthorizedClosedLoopError(f"{field} must be a non-empty string")
    return value.strip()


def _positive_int(value: object, field: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise PolicyAuthorizedClosedLoopError(
            f"{field} must be an integer from 1 to {maximum}"
        )
    return value


def _exact_object(
    value: object,
    *,
    required: set[str],
    allowed: set[str],
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PolicyAuthorizedClosedLoopError(f"{field} must be an object")
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise PolicyAuthorizedClosedLoopError(
            f"{field} is missing required keys: {', '.join(missing)}"
        )
    if unknown:
        raise PolicyAuthorizedClosedLoopError(
            f"{field} has unknown keys: {', '.join(unknown)}"
        )
    return value


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list):
        raise PolicyAuthorizedClosedLoopError(f"{field} must be a list")
    result: list[str] = []
    for index, item in enumerate(value):
        text = _nonempty_text(item, f"{field}[{index}]")
        if text in result:
            raise PolicyAuthorizedClosedLoopError(f"{field} must not contain duplicates")
        result.append(text)
    return result


def _resolved_file(value: str | Path, field: str, *, strict: bool = True) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=strict)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise PolicyAuthorizedClosedLoopError(f"{field} does not resolve: {value}") from exc
    if strict and not path.is_file():
        raise PolicyAuthorizedClosedLoopError(f"{field} must be a regular file: {path}")
    return path


def _resolved_dir(value: str | Path, field: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise PolicyAuthorizedClosedLoopError(f"{field} does not resolve: {value}") from exc
    if not path.is_dir():
        raise PolicyAuthorizedClosedLoopError(f"{field} must be a directory: {path}")
    return path


def _binding(path: Path, sha256: str) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256}


def _write_exact_snapshot(path: Path, raw: bytes, *, expected_sha256: str) -> dict[str, str]:
    if _sha256_bytes(raw) != expected_sha256:
        raise PolicyAuthorizedClosedLoopError("snapshot bytes differ from expected SHA-256")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(raw)
    except FileExistsError as exc:
        raise PolicyAuthorizedClosedLoopError(f"authority snapshot already exists: {path}") from exc
    written, written_sha = _read_file_snapshot(path)
    if written != raw or written_sha != expected_sha256:
        raise PolicyAuthorizedClosedLoopError(
            f"authority snapshot did not preserve exact bytes: {path}"
        )
    return _binding(path.resolve(), written_sha)


def _verify_binding_file(
    binding: object,
    *,
    expected_path: str | Path,
    field: str,
) -> dict[str, str]:
    """Compatibility helper for non-side-effecting callers and focused regressions."""
    if not isinstance(binding, Mapping):
        raise PolicyAuthorizedClosedLoopError(f"{field} is missing or malformed")
    actual_path = _resolved_file(expected_path, f"{field} expected path")
    bound_path = _resolved_file(
        _nonempty_text(binding.get("path"), f"{field}.path"), f"{field}.path"
    )
    if bound_path != actual_path:
        raise PolicyAuthorizedClosedLoopError(
            f"{field} path differs from the exact gated/predeclared path"
        )
    expected_sha = _nonempty_text(binding.get("sha256"), f"{field}.sha256")
    _, actual_sha = _read_file_snapshot(actual_path)
    if actual_sha != expected_sha:
        raise PolicyAuthorizedClosedLoopError(
            f"{field} bytes changed after validation: expected {expected_sha}, got {actual_sha}"
        )
    return _binding(actual_path, actual_sha)


def load_result_record_plan(
    path: str | Path,
    *,
    request_queue: Mapping[str, Any],
) -> dict[str, Any]:
    """Load a finite record-only plan bound to exact queued request bytes."""
    plan_path = _resolved_file(path, "result_record_plan")
    raw, _, plan_sha = _read_json_snapshot(plan_path)
    root = _exact_object(
        raw,
        required={"schema_version", "plan_id", "adapter_id", "records"},
        allowed={"schema_version", "plan_id", "adapter_id", "records", "metadata"},
        field="result record plan",
    )
    if root["schema_version"] != RESULT_RECORD_PLAN_SCHEMA_VERSION:
        raise PolicyAuthorizedClosedLoopError("unsupported result record plan schema_version")
    adapter_id = _nonempty_text(root["adapter_id"], "result record plan adapter_id")
    if adapter_id != request_queue.get("adapter_id"):
        raise PolicyAuthorizedClosedLoopError(
            "result record plan adapter_id does not match request queue"
        )
    requests = request_queue.get("requests")
    if not isinstance(requests, list):
        raise PolicyAuthorizedClosedLoopError("request queue requests are malformed")
    requests_by_id = {
        str(item["request_id"]): item
        for item in requests
        if isinstance(item, Mapping) and isinstance(item.get("request_id"), str)
    }
    raw_records = root["records"]
    if not isinstance(raw_records, list):
        raise PolicyAuthorizedClosedLoopError("result record plan records must be a list")

    records: list[dict[str, Any]] = []
    record_ids: set[str] = set()
    request_ids: set[str] = set()
    result_node_ids: set[str] = set()
    for index, raw_record in enumerate(raw_records):
        record = _exact_object(
            raw_record,
            required={
                "record_id",
                "request_id",
                "request_sha256",
                "expected_action_type",
                "expected_action_version",
                "target_node_id",
                "result_node_id",
                "result_node_type",
                "result_origin",
                "action_class",
                "statement",
                "limitations",
            },
            allowed={
                "record_id",
                "request_id",
                "request_sha256",
                "expected_action_type",
                "expected_action_version",
                "target_node_id",
                "result_node_id",
                "result_node_type",
                "result_origin",
                "action_class",
                "statement",
                "limitations",
            },
            field=f"records[{index}]",
        )
        record_id = _nonempty_text(record["record_id"], f"records[{index}].record_id")
        request_id = _nonempty_text(record["request_id"], f"records[{index}].request_id")
        result_node_id = _nonempty_text(
            record["result_node_id"], f"records[{index}].result_node_id"
        )
        if record_id in record_ids:
            raise PolicyAuthorizedClosedLoopError(f"duplicate record_id: {record_id}")
        if request_id in request_ids:
            raise PolicyAuthorizedClosedLoopError(f"duplicate record request_id: {request_id}")
        if result_node_id in result_node_ids:
            raise PolicyAuthorizedClosedLoopError(f"duplicate result_node_id: {result_node_id}")
        record_ids.add(record_id)
        request_ids.add(request_id)
        result_node_ids.add(result_node_id)

        request = requests_by_id.get(request_id)
        if not isinstance(request, Mapping):
            raise PolicyAuthorizedClosedLoopError(
                f"record references unknown request_id: {request_id}"
            )
        request_sha = _nonempty_text(
            record["request_sha256"], f"records[{index}].request_sha256"
        )
        if request_sha != request.get("sha256"):
            raise PolicyAuthorizedClosedLoopError(
                f"record {record_id} is not bound to the exact queued request checksum"
            )
        action_type = _nonempty_text(
            record["expected_action_type"], f"records[{index}].expected_action_type"
        )
        action_version = _nonempty_text(
            record["expected_action_version"],
            f"records[{index}].expected_action_version",
        )
        if (
            request.get("expected_action_type") != action_type
            or request.get("expected_action_version") != action_version
        ):
            raise PolicyAuthorizedClosedLoopError(
                f"record {record_id} action type/version does not match request {request_id}"
            )
        node_type = _nonempty_text(
            record["result_node_type"], f"records[{index}].result_node_type"
        )
        result_origin = _nonempty_text(
            record["result_origin"], f"records[{index}].result_origin"
        )
        if (node_type, result_origin) not in _LOCAL_RESULT_TYPES:
            raise PolicyAuthorizedClosedLoopError(
                "record-only automatic transitions support only authorized local analysis or simulation results"
            )
        action_class = _nonempty_text(
            record["action_class"], f"records[{index}].action_class"
        )
        if action_class not in _LOCAL_ACTION_CLASSES:
            raise PolicyAuthorizedClosedLoopError(
                f"records[{index}].action_class is not an allowed local class"
            )
        records.append(
            {
                "record_id": record_id,
                "request_id": request_id,
                "request_sha256": request_sha,
                "expected_action_type": action_type,
                "expected_action_version": action_version,
                "target_node_id": _nonempty_text(
                    record["target_node_id"], f"records[{index}].target_node_id"
                ),
                "result_node_id": result_node_id,
                "result_node_type": node_type,
                "result_origin": result_origin,
                "action_class": action_class,
                "statement": _nonempty_text(
                    record["statement"], f"records[{index}].statement"
                ),
                "limitations": _string_list(
                    record["limitations"], f"records[{index}].limitations"
                ),
            }
        )
    if request_ids != set(requests_by_id):
        missing = sorted(set(requests_by_id) - request_ids)
        extra = sorted(request_ids - set(requests_by_id))
        raise PolicyAuthorizedClosedLoopError(
            "result record plan must bind every queued request exactly once; "
            f"missing={missing}, extra={extra}"
        )
    result: dict[str, Any] = {
        "schema_version": RESULT_RECORD_PLAN_SCHEMA_VERSION,
        "plan_id": _nonempty_text(root["plan_id"], "plan_id"),
        "adapter_id": adapter_id,
        "plan_binding": _binding(plan_path, plan_sha),
        "records": records,
    }
    if "metadata" in root:
        if not isinstance(root["metadata"], dict):
            raise PolicyAuthorizedClosedLoopError("result record plan metadata must be an object")
        result["metadata"] = root["metadata"]
    return result


def _preflight_output_root(output_root: Path) -> None:
    if output_root.exists():
        if not output_root.is_dir():
            raise PolicyAuthorizedClosedLoopError(
                f"output_root must be a directory when it exists: {output_root}"
            )
        if any(output_root.iterdir()):
            raise PolicyAuthorizedClosedLoopError(
                "output_root must be absent or empty before any closed-loop action executes"
            )


def _preflight_graph_and_records(
    *,
    graph_path: Path,
    records: Sequence[Mapping[str, Any]],
    target_ids: Sequence[str],
) -> dict[str, Any]:
    """Fail before side effects on graph/record incompatibility and mutable provenance."""
    graph, _, graph_sha = _read_json_snapshot(graph_path)
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise PolicyAuthorizedClosedLoopError("initial epistemic graph nodes/edges are malformed")
    nodes_by_id: dict[str, Mapping[str, Any]] = {}
    for item in nodes:
        if not isinstance(item, Mapping):
            continue
        raw_id = item.get("node_id")
        if isinstance(raw_id, str) and raw_id.strip():
            nodes_by_id[raw_id.strip()] = item
    edge_ids = {
        str(item.get("edge_id")).strip()
        for item in edges
        if isinstance(item, Mapping)
        and isinstance(item.get("edge_id"), str)
        and str(item.get("edge_id")).strip()
    }
    selected = set(target_ids)
    for target_id in selected:
        target = nodes_by_id.get(target_id)
        raw_type = target.get("node_type") if isinstance(target, Mapping) else None
        target_type = raw_type.strip() if isinstance(raw_type, str) else None
        if target_type not in _TARGET_TYPES:
            raise PolicyAuthorizedClosedLoopError(
                f"selected target is not an existing hypothesis/claim/conclusion: {target_id}"
            )

    mutable_bindings: list[str] = []
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        raw_type = node.get("node_type")
        node_type = raw_type.strip() if isinstance(raw_type, str) else None
        if node_type != "evidence":
            continue
        binding = node.get("evidence_binding")
        if not isinstance(binding, Mapping):
            continue
        raw_role = binding.get("role")
        role = raw_role.strip() if isinstance(raw_role, str) else None
        if role in _MUTABLE_PROGRAM_EVIDENCE_ROLES:
            mutable_bindings.append(str(node.get("node_id")).strip())
    if mutable_bindings:
        raise PolicyAuthorizedClosedLoopError(
            "closed-loop graphs must not use mutable research_state/research_ledger "
            "program evidence bindings; use an immutable evidence binding or frozen "
            f"snapshot before execution: nodes={sorted(mutable_bindings)}"
        )

    for record in records:
        target_id = _nonempty_text(record.get("target_node_id"), "record.target_node_id")
        if target_id not in selected:
            raise PolicyAuthorizedClosedLoopError(
                "every result-record target must be one of the exact gate-selected targets"
            )
        result_node_id = _nonempty_text(record.get("result_node_id"), "record.result_node_id")
        if result_node_id in nodes_by_id:
            raise PolicyAuthorizedClosedLoopError(
                f"predeclared result node collides with initial graph: {result_node_id}"
            )
        edge_id = f"{_nonempty_text(record.get('record_id'), 'record.record_id')}::tests"
        if edge_id in edge_ids:
            raise PolicyAuthorizedClosedLoopError(
                f"predeclared tests edge collides with initial graph: {edge_id}"
            )
    return _binding(graph_path.resolve(), graph_sha)


def _snapshot_requests(queue: Mapping[str, Any]) -> list[dict[str, Any]]:
    requests = queue.get("requests")
    if not isinstance(requests, list):
        raise PolicyAuthorizedClosedLoopError("request queue requests are malformed")
    snapshots: list[dict[str, Any]] = []
    for index, request in enumerate(requests):
        if not isinstance(request, Mapping):
            raise PolicyAuthorizedClosedLoopError(f"request queue item {index} is malformed")
        path = _resolved_file(
            _nonempty_text(request.get("path"), f"requests[{index}].path"),
            f"requests[{index}].path",
        )
        raw, digest = _read_file_snapshot(path)
        expected = _nonempty_text(request.get("sha256"), f"requests[{index}].sha256")
        if digest != expected:
            raise PolicyAuthorizedClosedLoopError(
                "queued request changed before closed-loop authority was pinned"
            )
        value = _parse_json_snapshot(raw, path)
        snapshots.append({**dict(request), "path": str(path), "raw": raw, "value": value})
    return snapshots


def _snapshot_static_file(
    source: str | Path,
    *,
    field: str,
) -> dict[str, Any]:
    path = _resolved_file(source, field)
    value, raw, digest = _read_json_snapshot(path)
    return {"source_path": str(path), "value": value, "raw": raw, "sha256": digest}


def _prepare_authority_root(
    output_base: Path,
    *,
    mission: Mapping[str, Any],
    context: Mapping[str, Any],
    queue: Mapping[str, Any],
    queue_raw: bytes,
    plan: Mapping[str, Any],
    plan_raw: bytes,
    request_snapshots: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    control = output_base / "_authority"
    control.mkdir(parents=True, exist_ok=False)
    mission_binding = _write_exact_snapshot(
        control / "mission.json",
        mission["raw"],
        expected_sha256=str(mission["sha256"]),
    )
    context_binding = _write_exact_snapshot(
        control / "runtime_context.json",
        context["raw"],
        expected_sha256=str(context["sha256"]),
    )
    queue_binding = _write_exact_snapshot(
        control / "request_queue.json",
        queue_raw,
        expected_sha256=str(queue["queue_binding"]["sha256"]),
    )
    plan_binding = _write_exact_snapshot(
        control / "result_record_plan.json",
        plan_raw,
        expected_sha256=str(plan["plan_binding"]["sha256"]),
    )
    pinned_requests: list[dict[str, Any]] = []
    for request in request_snapshots:
        request_id = _nonempty_text(request.get("request_id"), "request.request_id")
        binding = _write_exact_snapshot(
            control / "requests" / f"{request_id}.json",
            request["raw"],
            expected_sha256=str(request["sha256"]),
        )
        pinned_requests.append({**dict(request), "snapshot_binding": binding})
    return {
        "root": str(control.resolve()),
        "mission_binding": mission_binding,
        "runtime_context_binding": context_binding,
        "queue_binding": queue_binding,
        "plan_binding": plan_binding,
        "requests": pinned_requests,
    }


def _cycle_input_snapshot(
    *,
    authority_root: Path,
    cycle_index: int,
    mission_raw: bytes,
    mission_sha: str,
    context_raw: bytes,
    context_sha: str,
    graph_raw: bytes,
    graph_sha: str,
) -> dict[str, dict[str, str]]:
    root = authority_root / f"cycle_{cycle_index:03d}"
    root.mkdir(parents=True, exist_ok=False)
    return {
        "mission": _write_exact_snapshot(root / "mission.json", mission_raw, expected_sha256=mission_sha),
        "runtime_context": _write_exact_snapshot(
            root / "runtime_context.json", context_raw, expected_sha256=context_sha
        ),
        "graph": _write_exact_snapshot(root / "base_graph.json", graph_raw, expected_sha256=graph_sha),
    }


def _verify_gate_snapshot_bindings(
    gate: Mapping[str, Any],
    *,
    snapshots: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    expected = {
        "mission_binding": snapshots["mission"],
        "runtime_context_binding": snapshots["runtime_context"],
        "graph_binding": snapshots["graph"],
    }
    for field, binding in expected.items():
        observed = gate.get(field)
        if not isinstance(observed, Mapping):
            raise PolicyAuthorizedClosedLoopError(f"epistemic gate omitted {field}")
        if observed.get("path") != binding["path"] or observed.get("sha256") != binding["sha256"]:
            raise PolicyAuthorizedClosedLoopError(
                f"epistemic gate {field} does not match the exact authority snapshot"
            )
    return expected


def _verify_runtime_context_value(
    context: Mapping[str, Any],
    *,
    workstream_id: str,
    research_run: str | Path,
    action_registry_path: str | Path,
) -> dict[str, str]:
    workstreams = context.get("workstreams")
    if not isinstance(workstreams, Mapping):
        raise PolicyAuthorizedClosedLoopError("runtime context workstreams must be an object")
    selected = workstreams.get(workstream_id)
    if not isinstance(selected, Mapping):
        raise PolicyAuthorizedClosedLoopError(
            f"runtime context omits workstream: {workstream_id}"
        )
    expected_run = _resolved_dir(
        _nonempty_text(selected.get("research_run"), "runtime research_run"),
        "runtime research_run",
    )
    expected_registry = _resolved_file(
        _nonempty_text(selected.get("action_registry_path"), "runtime action_registry_path"),
        "runtime action_registry_path",
    )
    actual_run = _resolved_dir(research_run, "research_run")
    actual_registry = _resolved_file(action_registry_path, "action_registry_path")
    if expected_run != actual_run or expected_registry != actual_registry:
        raise PolicyAuthorizedClosedLoopError(
            "execution paths differ from the pinned epistemic runtime context"
        )
    return {"research_run": str(actual_run), "action_registry_path": str(actual_registry)}


def _verify_action_report_still_ledger_bound(
    *,
    research_run: str | Path,
    report_path: Path,
    report_bytes: bytes,
    report_sha256: str,
    action_id: str,
    execution: Mapping[str, Any],
) -> dict[str, Any]:
    run = _resolved_dir(research_run, "research_run")
    verified_report = execution.get("verified_report")
    if not isinstance(verified_report, Mapping):
        raise PolicyAuthorizedClosedLoopError("execution result omitted the pinned verifier result")
    execution_status = _nonempty_text(
        execution.get("execution_status"), "execution.execution_status"
    )
    verified_status = _nonempty_text(
        verified_report.get("execution_status"), "execution.verified_report.execution_status"
    )
    if execution_status not in {"completed", "failed"} or verified_status != execution_status:
        raise PolicyAuthorizedClosedLoopError(
            "execution status does not match the pinned verifier result"
        )
    state = load_research_state(run)
    verified_ledger_sha = _nonempty_text(
        verified_report.get("ledger_sha256"), "execution.verified_report.ledger_sha256"
    )
    current_ledger_sha = _nonempty_text(
        state.get("ledger_sha256"), "research_state.ledger_sha256"
    )
    if current_ledger_sha != verified_ledger_sha:
        raise PolicyAuthorizedClosedLoopError(
            "research ledger changed after typed result verification"
        )
    actions = state.get("actions")
    if not isinstance(actions, list):
        raise PolicyAuthorizedClosedLoopError("research action ledger is malformed")
    matches = [
        item
        for item in actions
        if isinstance(item, Mapping) and item.get("action_id") == action_id
    ]
    if len(matches) != 1:
        raise PolicyAuthorizedClosedLoopError(
            "research ledger must contain exactly one recorded action for the result"
        )
    if matches[0].get("status") != execution_status:
        raise PolicyAuthorizedClosedLoopError(
            "research ledger action status differs from the verified execution status"
        )
    artifacts = matches[0].get("artifacts")
    if not isinstance(artifacts, list):
        raise PolicyAuthorizedClosedLoopError("ledger action artifact binding is malformed")
    report_size = len(report_bytes)
    report_matches = [
        item
        for item in artifacts
        if isinstance(item, Mapping)
        and item.get("path") == str(report_path)
        and item.get("sha256") == report_sha256
        and item.get("bytes") == report_size
    ]
    if len(report_matches) != 1:
        raise PolicyAuthorizedClosedLoopError(
            "current action report bytes are no longer checksum-bound by the verified ledger"
        )
    return {
        "research_run": str(run),
        "ledger_sha256": current_ledger_sha,
        "action_id": action_id,
        "execution_status": execution_status,
        "action_report_sha256": report_sha256,
        "action_report_bytes": report_size,
    }


def _assessment_for(evaluation: Mapping[str, Any], node_id: str) -> dict[str, Any]:
    assessments = evaluation.get("assessments")
    if not isinstance(assessments, list):
        raise PolicyAuthorizedClosedLoopError("epistemic evaluation assessments are malformed")
    matches = [
        item
        for item in assessments
        if isinstance(item, Mapping) and item.get("node_id") == node_id
    ]
    if len(matches) != 1:
        raise PolicyAuthorizedClosedLoopError(f"target assessment is not unique: {node_id}")
    return dict(matches[0])


def _apply_record_only_action_result(
    *,
    base_graph_path: str | Path,
    pre_execution_program_state: Mapping[str, Any],
    artifact_root: str | Path,
    output_dir: str | Path,
    research_run: str | Path,
    record_plan_binding: Mapping[str, Any],
    record: Mapping[str, Any],
    request: Mapping[str, Any],
    execution: Mapping[str, Any],
    base_graph_value: Mapping[str, Any] | None = None,
    base_graph_sha256: str | None = None,
    record_plan_snapshot_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one verified outcome without reopening pinned scientific authority inputs."""
    base_path = _resolved_file(base_graph_path, "base_graph_path")
    artifacts = _resolved_dir(artifact_root, "artifact_root")
    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise PolicyAuthorizedClosedLoopError(
            f"cycle output already exists before graph recording: {output}"
        )

    if base_graph_value is None:
        base_raw, _, observed_base_sha = _read_json_snapshot(base_path)
        if base_graph_sha256 is not None and observed_base_sha != base_graph_sha256:
            raise PolicyAuthorizedClosedLoopError(
                "base graph changed after the epistemic gate authorized execution"
            )
        base_sha = observed_base_sha
    else:
        base_raw = dict(base_graph_value)
        canonical_source = _canonical_json_bytes(base_raw)
        # When a raw source SHA is provided it is authoritative even if formatting was
        # noncanonical.  The value is already the exact parse of those bytes.
        base_sha = base_graph_sha256 or _sha256_bytes(canonical_source)

    base_validated = validate_epistemic_graph(
        base_raw, program_state=pre_execution_program_state, artifact_root=artifacts
    )
    before_eval = evaluate_epistemic_graph(
        base_raw, program_state=pre_execution_program_state, artifact_root=artifacts
    )

    request_id = _nonempty_text(request.get("request_id"), "request.request_id")
    if request_id != record.get("request_id"):
        raise PolicyAuthorizedClosedLoopError("record does not match the consumed execution request")
    if record.get("request_sha256") != request.get("sha256"):
        raise PolicyAuthorizedClosedLoopError(
            "record request checksum differs from the consumed request"
        )
    for record_field, execution_field in (
        ("expected_action_type", "action_type"),
        ("expected_action_version", "action_version"),
    ):
        if record.get(record_field) != execution.get(execution_field):
            raise PolicyAuthorizedClosedLoopError(
                f"execution {execution_field} does not match predeclared result record"
            )

    action_id = _nonempty_text(execution.get("ledger_action_id"), "execution.ledger_action_id")
    report_path = _resolved_file(
        _nonempty_text(execution.get("action_report"), "execution.action_report"),
        "execution.action_report",
    )
    report_bytes, report_sha = _read_file_snapshot(report_path)
    ledger_binding = _verify_action_report_still_ledger_bound(
        research_run=research_run,
        report_path=report_path,
        report_bytes=report_bytes,
        report_sha256=report_sha,
        action_id=action_id,
        execution=execution,
    )
    execution_status = str(ledger_binding["execution_status"])

    if record_plan_snapshot_binding is not None:
        plan_binding = {
            "path": _nonempty_text(
                record_plan_snapshot_binding.get("path"), "record_plan_snapshot_binding.path"
            ),
            "sha256": _nonempty_text(
                record_plan_snapshot_binding.get("sha256"), "record_plan_snapshot_binding.sha256"
            ),
        }
    else:
        plan_binding = _verify_binding_file(
            record_plan_binding,
            expected_path=_nonempty_text(record_plan_binding.get("path"), "record_plan_binding.path"),
            field="result_record_plan_binding",
        )

    request_binding = execution.get("request_binding")
    if not isinstance(request_binding, Mapping):
        raise PolicyAuthorizedClosedLoopError("execution result omitted exact request binding")
    if request_binding.get("sha256") != request.get("sha256"):
        raise PolicyAuthorizedClosedLoopError(
            "execution request binding does not match pinned queued request bytes"
        )
    if execution.get("request_bytes_source") not in {None, "pinned_in_memory_snapshot"}:
        raise PolicyAuthorizedClosedLoopError("execution used an unknown request byte source")
    if execution.get("scientific_evidence_upgraded_by_orchestrator") is not False:
        raise PolicyAuthorizedClosedLoopError(
            "execution result does not preserve the no-evidence-upgrade boundary"
        )
    if execution.get("network_access_initiated_by_orchestrator") is not False:
        raise PolicyAuthorizedClosedLoopError(
            "closed loop refuses execution results that initiated network access"
        )

    nodes = base_validated["nodes"]
    target_id = _nonempty_text(record.get("target_node_id"), "record.target_node_id")
    target = next(
        (
            item
            for item in nodes
            if item["node_id"] == target_id and item["node_type"] in _TARGET_TYPES
        ),
        None,
    )
    if target is None:
        raise PolicyAuthorizedClosedLoopError(
            "record target must be an existing hypothesis, claim, or conclusion"
        )
    result_node_id = _nonempty_text(record.get("result_node_id"), "record.result_node_id")
    if any(item["node_id"] == result_node_id for item in nodes):
        raise PolicyAuthorizedClosedLoopError(f"result node already exists: {result_node_id}")
    tests_edge_id = f"{_nonempty_text(record.get('record_id'), 'record.record_id')}::tests"
    if any(item["edge_id"] == tests_edge_id for item in base_validated["edges"]):
        raise PolicyAuthorizedClosedLoopError(
            f"result record tests edge already exists: {tests_edge_id}"
        )

    node_type = _nonempty_text(record.get("result_node_type"), "record.result_node_type")
    result_origin = _nonempty_text(record.get("result_origin"), "record.result_origin")
    if (node_type, result_origin) not in _LOCAL_RESULT_TYPES:
        raise PolicyAuthorizedClosedLoopError(
            "automatic record transition attempted a non-local result origin"
        )

    output.mkdir(parents=True, exist_ok=False)
    frozen_report = output / "verified_action_report.json"
    try:
        frozen_report.write_bytes(report_bytes)
        frozen_bytes, frozen_sha = _read_file_snapshot(frozen_report)
        if frozen_bytes != report_bytes or frozen_sha != report_sha:
            raise PolicyAuthorizedClosedLoopError(
                "frozen action-report snapshot does not match verified report bytes"
            )

        result_node: dict[str, Any] = {
            "node_id": result_node_id,
            "node_type": node_type,
            "statement": _nonempty_text(record.get("statement"), "record.statement"),
            "execution_status": execution_status,
            "metadata": {
                "result_origin": result_origin,
                "record_only_transition": True,
                "record_id": record["record_id"],
                "record_plan_binding": plan_binding,
                "verified_ledger_binding": ledger_binding,
                "source_action": {
                    "action_id": action_id,
                    "action_type": execution["action_type"],
                    "action_version": execution["action_version"],
                    "action_class": record["action_class"],
                    "execution_mode": "typed_local_action",
                },
                "request_binding": {
                    "request_id": request_id,
                    "path": request_binding.get("path"),
                    "sha256": request_binding.get("sha256"),
                    "size_bytes": request_binding.get("size_bytes"),
                },
                "limitations": list(record.get("limitations", [])),
            },
        }
        appended_edges: list[dict[str, Any]] = []
        if execution_status == "completed":
            result_node["artifact_bindings"] = [
                {
                    "role": "authorized_action_report_snapshot",
                    "path": str(frozen_report),
                    "sha256": report_sha,
                }
            ]
            appended_edges.append(
                {
                    "edge_id": tests_edge_id,
                    "source_node_id": result_node_id,
                    "target_node_id": target_id,
                    "relation": "tests",
                    "assessment_level": "proposal",
                    "rationale": (
                        "The completed checksum-bound local result is recorded as testing "
                        "this target. No directional inference is generated."
                    ),
                    "active": True,
                }
            )
        else:
            encoded = base64.b64encode(report_bytes).decode("ascii")
            result_node["metadata"]["failed_action_report_snapshot"] = {
                "encoding": "base64",
                "sha256": report_sha,
                "size_bytes": len(report_bytes),
                "data": encoded,
            }
            # Backward-compatible audit locator; the embedded snapshot above is the
            # self-contained tamper-evident failure provenance.
            result_node["metadata"]["failed_action_report_binding"] = {
                "path": str(frozen_report),
                "sha256": report_sha,
                "bytes": len(report_bytes),
            }

        metadata = dict(base_raw.get("metadata", {}))
        lineage = metadata.get("record_only_transition_lineage", [])
        if not isinstance(lineage, list):
            raise PolicyAuthorizedClosedLoopError(
                "base graph metadata.record_only_transition_lineage must be a list"
            )
        record_id = str(record["record_id"])
        metadata["record_only_transition_lineage"] = [
            *lineage,
            {
                "record_id": record_id,
                "parent_graph_id": base_validated["graph_id"],
                "parent_graph_sha256": base_sha,
                "request_id": request_id,
                "request_sha256": request["sha256"],
                "record_plan_sha256": plan_binding["sha256"],
                "verified_ledger_sha256": ledger_binding["ledger_sha256"],
                "action_id": action_id,
                "action_execution_status": execution_status,
                "action_report_sha256": report_sha,
                "result_node_id": result_node_id,
            },
        ]
        successor = {
            "schema_version": base_raw["schema_version"],
            "graph_id": f"{base_validated['graph_id']}::record::{record_id}",
            "research_scope": base_raw["research_scope"],
            "nodes": [*base_raw["nodes"], result_node],
            "edges": [*base_raw["edges"], *appended_edges],
            "metadata": metadata,
        }
        validate_epistemic_graph(
            successor,
            program_state=pre_execution_program_state,
            artifact_root=artifacts,
        )
        after_eval = evaluate_epistemic_graph(
            successor,
            program_state=pre_execution_program_state,
            artifact_root=artifacts,
        )
        before_target = _assessment_for(before_eval, target_id)
        after_target = _assessment_for(after_eval, target_id)
        protected_fields = (
            "status",
            "verified_support_edges",
            "verified_contradiction_edges",
            "verified_falsification_edges",
            "final_positive_support_granted",
            "domain_closeout_required_for_positive_conclusion",
            "confidence_score",
        )
        if any(before_target.get(key) != after_target.get(key) for key in protected_fields):
            raise PolicyAuthorizedClosedLoopError(
                "record-only transition changed verified epistemic target status"
            )

        graph_bytes = _canonical_json_bytes(successor)
        graph_sha = _sha256_bytes(graph_bytes)
        graph_path = output / "epistemic_graph.json"
        graph_path.write_bytes(graph_bytes)
        manifest = {
            "schema_version": CLOSED_LOOP_SCHEMA_VERSION,
            "closed_loop_policy_version": CLOSED_LOOP_POLICY_VERSION,
            "transition_kind": "record_only_action_result",
            "record_id": record_id,
            "execution_status": execution_status,
            "base_graph_binding": {"path": str(base_path), "sha256": base_sha},
            "request_binding": {
                "request_id": request_id,
                "path": request.get("path"),
                "sha256": request.get("sha256"),
            },
            "result_record_plan_binding": plan_binding,
            "verified_ledger_binding": ledger_binding,
            "action_binding": {
                "action_id": action_id,
                "action_type": execution["action_type"],
                "action_version": execution["action_version"],
                "source_action_report": str(report_path),
                "frozen_action_report": str(frozen_report),
                "action_report_sha256": report_sha,
                "action_report_bytes": len(report_bytes),
            },
            "target_node_id": target_id,
            "target_before": before_target,
            "target_after": after_target,
            "tests_edge_generated": execution_status == "completed",
            "directional_inference_generated": False,
            "domain_verification_generated": False,
            "successor_graph": {
                "graph_id": successor["graph_id"],
                "path": str(graph_path),
                "sha256": graph_sha,
            },
            "autonomy_boundary": {
                "supports_relation_generated": False,
                "contradicts_relation_generated": False,
                "falsifies_relation_generated": False,
                "scientific_status_upgraded": False,
                "failed_action_misrepresented_as_completed": False,
                "network_access_performed_by_transition": False,
                "physical_experiment_executed_by_transition": False,
                "base_graph_mutated": False,
                "verified_report_frozen_before_graph_binding": True,
                "failed_report_provenance_embedded_in_graph": execution_status == "failed",
            },
        }
        (output / "record_only_transition_manifest.json").write_bytes(
            _canonical_json_bytes(manifest)
        )
        return {**manifest, "successor_graph_evaluation": after_eval}
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def _selected_action(authorization: object) -> dict[str, Any] | None:
    if not isinstance(authorization, Mapping):
        return None
    selected = authorization.get("selected_action")
    return dict(selected) if isinstance(selected, Mapping) else None


def _verify_request_matches_selected_action(
    request: Mapping[str, Any], selected_action: Mapping[str, Any]
) -> None:
    if (
        request.get("expected_action_type") != selected_action.get("action_type")
        or request.get("expected_action_version") != selected_action.get("action_version")
    ):
        raise PolicyAuthorizedClosedLoopError(
            "predeclared request does not match the current planner-selected action"
        )


def _state_fingerprint(state: object) -> str | None:
    if not isinstance(state, Mapping):
        return None
    bounded = {
        "adapter_id": state.get("adapter_id"),
        "current_blocker": state.get("current_blocker"),
        "evidence_gap": state.get("evidence_gap"),
        "selected_action": state.get("selected_action"),
        "stop_state": state.get("stop_state"),
        "budget": state.get("budget"),
        "evidence_bindings": state.get("evidence_bindings"),
    }
    encoded = json.dumps(
        bounded,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _gate_stop_status(directive: str) -> tuple[str, str]:
    mapping = {
        "stop_falsified_target": (
            "epistemic_falsification_stop",
            "Verified falsification stopped the selected line of inquiry.",
        ),
        "manual_discrimination_required": (
            "epistemic_discrimination_required",
            "Verified contradiction/conflict requires a stronger discriminating step.",
        ),
        "domain_closeout_required": (
            "epistemic_domain_closeout_required",
            "Provisional positive support requires domain closeout.",
        ),
    }
    if directive not in mapping:
        raise PolicyAuthorizedClosedLoopError(
            f"unsupported non-executable epistemic directive: {directive!r}"
        )
    return mapping[directive]


def run_policy_authorized_closed_loop(
    adapter_id: str,
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    initial_graph_path: str | Path,
    epistemic_workstream_id: str,
    epistemic_target_node_ids: Sequence[object],
    runtime_context_path: str | Path,
    artifact_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_queue_path: str | Path,
    result_record_plan_path: str | Path,
    output_root: str | Path,
    request_root: str | Path | None = None,
    max_cycles: int = _DEFAULT_MAX_CYCLES,
) -> dict[str, Any]:
    """Execute-record-regate-replan using immutable authority snapshots."""
    adapter = _nonempty_text(adapter_id, "adapter_id")
    max_cycles = _positive_int(max_cycles, "max_cycles", maximum=_HARD_MAX_CYCLES)
    root = _resolved_dir(repository_root, "repository_root")
    artifacts = _resolved_dir(artifact_root, "artifact_root")
    run = _resolved_dir(research_run, "research_run")
    registry = _resolved_file(action_registry_path, "action_registry_path")

    mission = _snapshot_static_file(mission_path, field="mission_path")
    context = _snapshot_static_file(runtime_context_path, field="runtime_context_path")
    current_graph_source = _resolved_file(initial_graph_path, "initial_graph_path")
    current_graph_value, current_graph_raw, current_graph_sha = _read_json_snapshot(
        current_graph_source
    )
    initial_graph_sha = current_graph_sha

    queue = load_request_queue(request_queue_path, request_root=request_root)
    if queue.get("adapter_id") != adapter:
        raise PolicyAuthorizedClosedLoopError(
            "request queue adapter_id does not match closed-loop adapter"
        )
    queue_path = _resolved_file(queue["queue_binding"]["path"], "request_queue")
    queue_raw, queue_sha = _read_file_snapshot(queue_path)
    if queue_sha != queue["queue_binding"]["sha256"]:
        raise PolicyAuthorizedClosedLoopError("request queue changed before authority pinning")

    record_plan = load_result_record_plan(result_record_plan_path, request_queue=queue)
    plan_path = _resolved_file(record_plan["plan_binding"]["path"], "result_record_plan")
    plan_raw, plan_sha = _read_file_snapshot(plan_path)
    if plan_sha != record_plan["plan_binding"]["sha256"]:
        raise PolicyAuthorizedClosedLoopError("result record plan changed before authority pinning")
    request_snapshots = _snapshot_requests(queue)

    target_ids = [
        _nonempty_text(value, f"epistemic_target_node_ids[{index}]")
        for index, value in enumerate(epistemic_target_node_ids)
    ]
    if not target_ids or len(set(target_ids)) != len(target_ids):
        raise PolicyAuthorizedClosedLoopError(
            "epistemic_target_node_ids must be unique and non-empty"
        )

    output_base = Path(output_root).expanduser().resolve()
    _preflight_output_root(output_base)
    # Preflight against an exact temporary snapshot before creating any executable
    # authority surface.  The file is deleted immediately afterward.
    preflight_dir = output_base.parent / f".{output_base.name}.preflight"
    if preflight_dir.exists():
        raise PolicyAuthorizedClosedLoopError(
            f"closed-loop preflight path already exists: {preflight_dir}"
        )
    preflight_dir.mkdir(parents=True)
    try:
        preflight_graph = preflight_dir / "graph.json"
        preflight_graph.write_bytes(current_graph_raw)
        _preflight_graph_and_records(
            graph_path=preflight_graph,
            records=record_plan["records"],
            target_ids=target_ids,
        )
    finally:
        shutil.rmtree(preflight_dir, ignore_errors=True)

    _verify_runtime_context_value(
        context["value"],
        workstream_id=epistemic_workstream_id,
        research_run=run,
        action_registry_path=registry,
    )
    output_base.mkdir(parents=True, exist_ok=True)
    authority = _prepare_authority_root(
        output_base,
        mission=mission,
        context=context,
        queue=queue,
        queue_raw=queue_raw,
        plan=record_plan,
        plan_raw=plan_raw,
        request_snapshots=request_snapshots,
    )
    requests = authority["requests"]
    records_by_request = {
        str(item["request_id"]): item for item in record_plan["records"]
    }

    request_index = 0
    cycles: list[dict[str, Any]] = []
    seen_after_fingerprints: set[str] = set()
    program_status: str | None = None
    stop_reason: str | None = None
    final_graph_path = current_graph_source

    for cycle_index in range(1, max_cycles + 1):
        cycle_snapshots = _cycle_input_snapshot(
            authority_root=Path(authority["root"]),
            cycle_index=cycle_index,
            mission_raw=mission["raw"],
            mission_sha=str(mission["sha256"]),
            context_raw=context["raw"],
            context_sha=str(context["sha256"]),
            graph_raw=current_graph_raw,
            graph_sha=current_graph_sha,
        )
        cycle_graph_path = Path(cycle_snapshots["graph"]["path"])
        # Every cycle is checked again because prior record-only successors contain new
        # nodes/edges even though the predeclared plan is finite.
        remaining_records = record_plan["records"][request_index:]
        _preflight_graph_and_records(
            graph_path=cycle_graph_path,
            records=remaining_records,
            target_ids=target_ids,
        )

        gate = evaluate_epistemic_gate(
            adapter_id=adapter,
            workstream_id=epistemic_workstream_id,
            target_node_ids=target_ids,
            mission_path=cycle_snapshots["mission"]["path"],
            graph_path=cycle_snapshots["graph"]["path"],
            repository_root=root,
            runtime_context_path=cycle_snapshots["runtime_context"]["path"],
            artifact_root=artifacts,
        )
        gate_bindings = _verify_gate_snapshot_bindings(gate, snapshots=cycle_snapshots)
        directive = gate.get("directive")
        if not isinstance(directive, Mapping):
            raise PolicyAuthorizedClosedLoopError("epistemic gate directive is malformed")
        if directive.get("automatic_execution_permitted") is not True:
            program_status, stop_reason = _gate_stop_status(str(directive.get("directive")))
            cycles.append(
                {
                    "cycle_index": cycle_index,
                    "graph_before": cycle_snapshots["graph"]["path"],
                    "epistemic_gate": gate,
                    "execution_input_bindings": gate_bindings,
                    "probe": None,
                    "request": None,
                    "execution": None,
                    "record_transition": None,
                }
            )
            break
        if directive.get("directive") != "continue_discriminating_research":
            raise PolicyAuthorizedClosedLoopError(
                "epistemic gate permitted execution with an unsupported directive"
            )

        pre_execution_program = build_research_program(
            cycle_snapshots["mission"]["path"],
            repository_root=root,
            runtime_context_path=cycle_snapshots["runtime_context"]["path"],
        )
        if pre_execution_program.get("mission_binding") != gate_bindings["mission_binding"]:
            raise PolicyAuthorizedClosedLoopError(
                "mission snapshot used by program differs from gated mission bytes"
            )
        if pre_execution_program.get("runtime_context_binding") != gate_bindings[
            "runtime_context_binding"
        ]:
            raise PolicyAuthorizedClosedLoopError(
                "runtime snapshot used by program differs from gated runtime bytes"
            )

        probe = run_research_cycle(
            adapter,
            repository_root=root,
            research_run=run,
            action_registry_path=registry,
            request_path=None,
        )
        probe_status = probe.get("cycle_status")
        if probe_status in _TERMINAL_PROBE_STATUSES:
            program_status = str(probe_status)
            stop_reason = "Current verified planning state does not permit another execution."
            cycles.append(
                {
                    "cycle_index": cycle_index,
                    "graph_before": cycle_snapshots["graph"]["path"],
                    "epistemic_gate": gate,
                    "execution_input_bindings": gate_bindings,
                    "probe": probe,
                    "request": None,
                    "execution": None,
                    "record_transition": None,
                }
            )
            break
        if probe_status != "explicit_request_required":
            raise PolicyAuthorizedClosedLoopError(
                f"unexpected probe cycle status: {probe_status!r}"
            )
        selected = _selected_action(probe.get("authorization"))
        if selected is None:
            raise PolicyAuthorizedClosedLoopError(
                "explicit-request probe omitted planner-selected authorized action"
            )
        if request_index >= len(requests):
            program_status = "predeclared_request_required"
            stop_reason = (
                "The planner selected another action, but the finite predeclared request queue is exhausted."
            )
            cycles.append(
                {
                    "cycle_index": cycle_index,
                    "graph_before": cycle_snapshots["graph"]["path"],
                    "epistemic_gate": gate,
                    "execution_input_bindings": gate_bindings,
                    "probe": probe,
                    "request": None,
                    "execution": None,
                    "record_transition": None,
                }
            )
            break

        request = requests[request_index]
        _verify_request_matches_selected_action(request, selected)
        record = records_by_request.get(str(request["request_id"]))
        if not isinstance(record, Mapping):
            raise PolicyAuthorizedClosedLoopError(
                "queued request has no checksum-bound result-record directive"
            )
        if record.get("target_node_id") not in target_ids:
            raise PolicyAuthorizedClosedLoopError(
                "result-record target is outside the exact gate-selected target set"
            )
        cycle_output = output_base / f"cycle_{cycle_index:03d}"
        if cycle_output.exists():
            raise PolicyAuthorizedClosedLoopError(
                "cycle output collision detected before action execution"
            )

        # This is the only side-effecting delegation.  It receives the exact request
        # bytes retained in memory at invocation preflight and never reopens the live
        # request pathname for request content.
        execution_cycle = run_pinned_research_cycle(
            adapter,
            repository_root=root,
            research_run=run,
            action_registry_path=registry,
            request_path=request["path"],
            request_bytes=request["raw"],
            expected_request_sha256=request["sha256"],
        )
        if execution_cycle.get("cycle_status") != "one_action_executed":
            program_status = "execution_cycle_not_completed"
            stop_reason = "The pinned request did not complete one authorized local action."
            cycles.append(
                {
                    "cycle_index": cycle_index,
                    "graph_before": cycle_snapshots["graph"]["path"],
                    "epistemic_gate": gate,
                    "execution_input_bindings": gate_bindings,
                    "probe": probe,
                    "request": {k: v for k, v in request.items() if k not in {"raw", "value"}},
                    "execution": execution_cycle,
                    "record_transition": None,
                }
            )
            break
        execution = execution_cycle.get("execution")
        if not isinstance(execution, Mapping):
            raise PolicyAuthorizedClosedLoopError(
                "completed pinned research cycle omitted execution result"
            )

        transition = _apply_record_only_action_result(
            base_graph_path=cycle_snapshots["graph"]["path"],
            base_graph_value=current_graph_value,
            base_graph_sha256=current_graph_sha,
            pre_execution_program_state=pre_execution_program,
            artifact_root=artifacts,
            output_dir=cycle_output,
            research_run=run,
            record_plan_binding=record_plan["plan_binding"],
            record_plan_snapshot_binding=authority["plan_binding"],
            record=record,
            request=request,
            execution=execution,
        )
        next_graph = _resolved_file(
            transition["successor_graph"]["path"], "record transition successor graph"
        )
        next_value, next_raw, next_sha = _read_json_snapshot(next_graph)
        if next_sha != transition["successor_graph"]["sha256"]:
            raise PolicyAuthorizedClosedLoopError(
                "successor graph changed immediately after record-only commit"
            )
        before_fp = _state_fingerprint(probe.get("before_planning_state"))
        after_fp = _state_fingerprint(execution_cycle.get("after_planning_state"))
        cycles.append(
            {
                "cycle_index": cycle_index,
                "graph_before": cycle_snapshots["graph"]["path"],
                "graph_after": str(next_graph),
                "epistemic_gate": gate,
                "execution_input_bindings": gate_bindings,
                "probe": probe,
                "request": {k: v for k, v in request.items() if k not in {"raw", "value"}},
                "execution": execution_cycle,
                "record_transition": transition,
                "before_state_fingerprint": before_fp,
                "after_state_fingerprint": after_fp,
            }
        )
        request_index += 1
        current_graph_value = next_value
        current_graph_raw = next_raw
        current_graph_sha = next_sha
        final_graph_path = next_graph

        if after_fp is None:
            raise PolicyAuthorizedClosedLoopError("completed action omitted after planning state")
        if after_fp == before_fp or after_fp in seen_after_fingerprints:
            program_status = "stopped_no_verified_planning_progress"
            stop_reason = (
                "The action outcome was recorded, but the bounded planning state did not progress; automatic execution stopped."
            )
            break
        seen_after_fingerprints.add(after_fp)

        after_transition = execution_cycle.get("after_transition")
        transition_type = (
            after_transition.get("transition_type")
            if isinstance(after_transition, Mapping)
            else None
        )
        if transition_type == "stop_current_scope":
            program_status = "stopped_current_scope"
            stop_reason = "Replanning after execution closed the current scope."
            break
        if transition_type in {"manual_review_required", "blocked"}:
            program_status = str(transition_type)
            stop_reason = "Replanning after execution reached a non-automatic boundary."
            break
    else:
        program_status = "cycle_limit_reached"
        stop_reason = "The hard-bounded invocation reached max_cycles."

    if program_status is None:
        program_status = "cycle_limit_reached"
        stop_reason = "The hard-bounded invocation reached max_cycles."
    return {
        "schema_version": CLOSED_LOOP_SCHEMA_VERSION,
        "closed_loop_policy_version": CLOSED_LOOP_POLICY_VERSION,
        "adapter_id": adapter,
        "program_status": program_status,
        "stop_reason": stop_reason,
        "max_cycles": max_cycles,
        "cycles_completed": len(cycles),
        "actions_executed": request_index,
        "requests_consumed": request_index,
        "request_queue_binding": authority["queue_binding"],
        "result_record_plan_binding": authority["plan_binding"],
        "initial_graph_binding": {
            "path": str(current_graph_source),
            "sha256": initial_graph_sha,
        },
        "final_graph_binding": {"path": str(final_graph_path), "sha256": current_graph_sha},
        "cycles": cycles,
        "autonomy_boundary": {
            "request_queue_is_finite": True,
            "request_bytes_pinned_in_memory_before_side_effects": True,
            "request_path_reopened_for_content_during_execution": False,
            "mission_runtime_graph_authority_snapshotted_per_cycle": True,
            "successor_ingestion_uses_exact_gated_base_value": True,
            "record_plan_semantics_pinned_before_execution": True,
            "verified_action_report_frozen_before_graph_binding": True,
            "failed_report_provenance_is_self_contained": True,
            "new_requests_generated": False,
            "directional_scientific_inference_generated": False,
            "domain_verification_generated": False,
            "network_evidence_acquisition_performed": False,
            "physical_experiment_execution_performed": False,
            "generic_command_execution_available": False,
        },
    }


__all__ = [
    "CLOSED_LOOP_POLICY_VERSION",
    "CLOSED_LOOP_SCHEMA_VERSION",
    "RESULT_RECORD_PLAN_SCHEMA_VERSION",
    "PolicyAuthorizedClosedLoopError",
    "load_result_record_plan",
    "run_policy_authorized_closed_loop",
]
