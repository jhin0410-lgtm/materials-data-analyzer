"""Bounded multi-cycle orchestration over the existing one-step research contract.

This module does not generate execution requests. It consumes at most one exact,
checksum-bound, predeclared typed request per cycle and delegates every execution to
``run_research_cycle``. The existing planner, authorization, registry, budget, and
verifier boundaries therefore remain authoritative on every iteration.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .kernel import ResearchLoopError
from .research_cycle import run_research_cycle

MULTICYCLE_SCHEMA_VERSION = "1.0"
MULTICYCLE_POLICY_VERSION = "1.0"
REQUEST_QUEUE_SCHEMA_VERSION = "1.0"

_DEFAULT_MAX_CYCLES = 8
_HARD_MAX_CYCLES = 32
_TERMINAL_PROBE_STATUSES = {
    "stopped_current_scope",
    "manual_review_required",
    "blocked",
    "authorization_denied",
}


class MultiCycleResearchError(ResearchLoopError):
    """Raised when a predeclared multi-cycle research contract is invalid."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MultiCycleResearchError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise MultiCycleResearchError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MultiCycleResearchError(f"JSON root must be an object: {path}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MultiCycleResearchError(f"{field} must be a non-empty string")
    return value.strip()


def _positive_int(value: object, field: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise MultiCycleResearchError(
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
        raise MultiCycleResearchError(f"{field} must be an object")
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise MultiCycleResearchError(f"{field} is missing required keys: {', '.join(missing)}")
    if unknown:
        raise MultiCycleResearchError(f"{field} has unknown keys: {', '.join(unknown)}")
    return value


def _resolve_under_root(raw_path: object, root: Path, field: str) -> Path:
    text = _nonempty_text(raw_path, field)
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise MultiCycleResearchError(f"{field} escapes request_root: {text}") from exc
    if not resolved.is_file():
        raise MultiCycleResearchError(f"{field} must resolve to a regular file: {resolved}")
    return resolved


def load_request_queue(
    queue_path: str | Path,
    *,
    request_root: str | Path | None = None,
) -> dict[str, Any]:
    """Load and verify a finite queue of explicit typed execution requests."""
    path = Path(queue_path).expanduser().resolve(strict=True)
    payload = _exact_object(
        _load_json(path),
        required={"schema_version", "queue_id", "adapter_id", "requests"},
        allowed={"schema_version", "queue_id", "adapter_id", "requests", "metadata"},
        field="request queue",
    )
    if payload["schema_version"] != REQUEST_QUEUE_SCHEMA_VERSION:
        raise MultiCycleResearchError(
            f"unsupported request queue schema_version: {payload['schema_version']!r}"
        )
    root = (
        Path(request_root).expanduser().resolve(strict=True)
        if request_root is not None
        else path.parent
    )
    if not root.is_dir():
        raise MultiCycleResearchError(f"request_root must be a directory: {root}")
    raw_requests = payload["requests"]
    if not isinstance(raw_requests, list):
        raise MultiCycleResearchError("request queue requests must be a list")
    request_ids: set[str] = set()
    normalized_requests: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_requests):
        item = _exact_object(
            raw,
            required={
                "request_id",
                "path",
                "sha256",
                "expected_action_type",
                "expected_action_version",
            },
            allowed={
                "request_id",
                "path",
                "sha256",
                "expected_action_type",
                "expected_action_version",
            },
            field=f"requests[{index}]",
        )
        request_id = _nonempty_text(item["request_id"], f"requests[{index}].request_id")
        if request_id in request_ids:
            raise MultiCycleResearchError(f"duplicate request_id: {request_id}")
        request_ids.add(request_id)
        request_path = _resolve_under_root(item["path"], root, f"requests[{index}].path")
        expected_sha = _nonempty_text(item["sha256"], f"requests[{index}].sha256")
        actual_sha = _sha256_file(request_path)
        if expected_sha != actual_sha:
            raise MultiCycleResearchError(
                f"requests[{index}] checksum mismatch: expected {expected_sha}, got {actual_sha}"
            )
        normalized_requests.append(
            {
                "request_id": request_id,
                "path": str(request_path),
                "sha256": actual_sha,
                "expected_action_type": _nonempty_text(
                    item["expected_action_type"], f"requests[{index}].expected_action_type"
                ),
                "expected_action_version": _nonempty_text(
                    item["expected_action_version"],
                    f"requests[{index}].expected_action_version",
                ),
            }
        )
    result: dict[str, Any] = {
        "schema_version": REQUEST_QUEUE_SCHEMA_VERSION,
        "queue_id": _nonempty_text(payload["queue_id"], "queue_id"),
        "adapter_id": _nonempty_text(payload["adapter_id"], "adapter_id"),
        "queue_binding": {"path": str(path), "sha256": _sha256_file(path)},
        "request_root": str(root),
        "requests": normalized_requests,
    }
    if "metadata" in payload:
        if not isinstance(payload["metadata"], dict):
            raise MultiCycleResearchError("request queue metadata must be an object")
        result["metadata"] = payload["metadata"]
    return result


def _selected_action(authorization: object) -> dict[str, Any] | None:
    if not isinstance(authorization, Mapping):
        return None
    selected = authorization.get("selected_action")
    return dict(selected) if isinstance(selected, Mapping) else None


def _verify_request_matches_selected_action(
    request: Mapping[str, Any],
    selected_action: Mapping[str, Any],
) -> None:
    expected_type = _nonempty_text(
        request.get("expected_action_type"), "request.expected_action_type"
    )
    expected_version = _nonempty_text(
        request.get("expected_action_version"), "request.expected_action_version"
    )
    actual_type = _nonempty_text(
        selected_action.get("action_type"), "selected_action.action_type"
    )
    actual_version = _nonempty_text(
        selected_action.get("action_version"), "selected_action.action_version"
    )
    if actual_type != expected_type or actual_version != expected_version:
        raise MultiCycleResearchError(
            "predeclared request queue does not match the current planner-selected action: "
            f"request expects {expected_type}@{expected_version}, planner selected "
            f"{actual_type}@{actual_version}"
        )


def _canonical_state_fingerprint(state: object) -> str | None:
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
    return hashlib.sha256(encoded).hexdigest()


def _cycle_record(
    *,
    cycle_index: int,
    probe: Mapping[str, Any],
    request: Mapping[str, Any] | None,
    execution_cycle: Mapping[str, Any] | None,
) -> dict[str, Any]:
    after_state = (
        execution_cycle.get("after_planning_state")
        if isinstance(execution_cycle, Mapping)
        else None
    )
    return {
        "cycle_index": cycle_index,
        "probe_status": probe.get("cycle_status"),
        "probe_before_transition": probe.get("before_transition"),
        "request": dict(request) if isinstance(request, Mapping) else None,
        "execution_cycle_status": (
            execution_cycle.get("cycle_status") if isinstance(execution_cycle, Mapping) else None
        ),
        "execution": (
            execution_cycle.get("execution") if isinstance(execution_cycle, Mapping) else None
        ),
        "before_state_fingerprint": _canonical_state_fingerprint(
            probe.get("before_planning_state")
        ),
        "after_state_fingerprint": _canonical_state_fingerprint(after_state),
        "after_transition": (
            execution_cycle.get("after_transition")
            if isinstance(execution_cycle, Mapping)
            else None
        ),
    }


def run_bounded_multicycle(
    adapter_id: str,
    *,
    repository_root: str | Path,
    research_run: str | Path | None = None,
    action_registry_path: str | Path | None = None,
    request_queue_path: str | Path | None = None,
    request_root: str | Path | None = None,
    max_cycles: int = _DEFAULT_MAX_CYCLES,
) -> dict[str, Any]:
    """Run a finite series of predeclared explicit actions with replanning after each."""
    max_cycles = _positive_int(max_cycles, "max_cycles", maximum=_HARD_MAX_CYCLES)
    root = Path(repository_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise MultiCycleResearchError(f"repository_root must be a directory: {root}")
    queue = (
        load_request_queue(request_queue_path, request_root=request_root)
        if request_queue_path is not None
        else None
    )
    if queue is not None and queue["adapter_id"] != adapter_id:
        raise MultiCycleResearchError(
            "request queue adapter_id does not match the requested research adapter"
        )
    requests = queue["requests"] if queue is not None else []
    request_index = 0
    cycles: list[dict[str, Any]] = []
    actions_executed = 0
    seen_after_fingerprints: set[str] = set()
    stop_reason: str | None = None
    program_status: str | None = None

    for cycle_index in range(1, max_cycles + 1):
        probe = run_research_cycle(
            adapter_id,
            repository_root=root,
            research_run=research_run,
            action_registry_path=action_registry_path,
            request_path=None,
        )
        probe_status = probe.get("cycle_status")
        if probe_status in _TERMINAL_PROBE_STATUSES:
            cycles.append(
                _cycle_record(
                    cycle_index=cycle_index,
                    probe=probe,
                    request=None,
                    execution_cycle=None,
                )
            )
            program_status = {
                "stopped_current_scope": "stopped_current_scope",
                "manual_review_required": "manual_review_required",
                "blocked": "blocked",
                "authorization_denied": "authorization_denied",
            }[str(probe_status)]
            stop_reason = "Current verified planning state does not permit another execution."
            break
        if probe_status != "explicit_request_required":
            raise MultiCycleResearchError(
                f"unexpected probe cycle status: {probe_status!r}"
            )
        selected = _selected_action(probe.get("authorization"))
        if selected is None:
            raise MultiCycleResearchError(
                "explicit-request probe did not retain one planner-selected authorized action"
            )
        if request_index >= len(requests):
            cycles.append(
                _cycle_record(
                    cycle_index=cycle_index,
                    probe=probe,
                    request=None,
                    execution_cycle=None,
                )
            )
            program_status = "predeclared_request_required"
            stop_reason = (
                "The planner selected another authorized typed action, but the finite "
                "predeclared request queue contains no matching unused request."
            )
            break

        request = requests[request_index]
        _verify_request_matches_selected_action(request, selected)
        execution_cycle = run_research_cycle(
            adapter_id,
            repository_root=root,
            research_run=research_run,
            action_registry_path=action_registry_path,
            request_path=request["path"],
        )
        record = _cycle_record(
            cycle_index=cycle_index,
            probe=probe,
            request=request,
            execution_cycle=execution_cycle,
        )
        cycles.append(record)
        if execution_cycle.get("cycle_status") != "one_action_executed":
            program_status = "execution_cycle_not_completed"
            stop_reason = (
                "The queued request did not complete one authorized action under the existing "
                "single-cycle contract."
            )
            break
        request_index += 1
        actions_executed += 1

        before_fp = record["before_state_fingerprint"]
        after_fp = record["after_state_fingerprint"]
        if after_fp is None:
            raise MultiCycleResearchError("completed execution cycle omitted after planning state")
        if after_fp == before_fp or after_fp in seen_after_fingerprints:
            program_status = "stopped_no_verified_state_progress"
            stop_reason = (
                "A completed action did not produce a new bounded planning-state fingerprint; "
                "automatic repetition was stopped."
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
            stop_reason = "Replanning after execution closed the current scientific scope."
            break
        if transition_type == "manual_review_required":
            program_status = "manual_review_required"
            stop_reason = "Replanning requires manual semantic or failed-action review."
            break
        if transition_type == "blocked":
            program_status = "blocked"
            stop_reason = "Replanning reached a verified operational blocker."
            break
        if transition_type not in {
            "action_pending_authorization",
            "evidence_requirement_pending_authorization",
        }:
            raise MultiCycleResearchError(
                f"unsupported after-transition type: {transition_type!r}"
            )
    else:
        program_status = "max_cycles_reached"
        stop_reason = "The hard-bounded invocation reached its configured cycle limit."

    if program_status is None or stop_reason is None:
        raise MultiCycleResearchError("multi-cycle orchestration ended without a stop status")
    return {
        "schema_version": MULTICYCLE_SCHEMA_VERSION,
        "multicycle_policy_version": MULTICYCLE_POLICY_VERSION,
        "adapter_id": adapter_id,
        "program_status": program_status,
        "stop_reason": stop_reason,
        "max_cycles": max_cycles,
        "cycles_started": len(cycles),
        "actions_executed": actions_executed,
        "requests_consumed": request_index,
        "requests_remaining": len(requests) - request_index,
        "request_queue": queue,
        "cycles": cycles,
        "autonomy_boundary": {
            "automatic_request_generation_available": False,
            "only_predeclared_checksum_bound_requests_consumed": True,
            "one_action_per_cycle_enforced_by_delegate": True,
            "planner_rebuilt_after_every_execution": True,
            "authorization_rechecked_for_every_execution": True,
            "generic_command_generation_available": False,
            "network_access_initiated_by_multicycle_orchestrator": False,
            "physical_experiment_execution_initiated_by_multicycle_orchestrator": False,
            "scientific_evidence_upgraded_by_multicycle_orchestrator": False,
        },
    }


__all__ = [
    "MULTICYCLE_POLICY_VERSION",
    "MULTICYCLE_SCHEMA_VERSION",
    "REQUEST_QUEUE_SCHEMA_VERSION",
    "MultiCycleResearchError",
    "load_request_queue",
    "run_bounded_multicycle",
]
