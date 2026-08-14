"""Epistemic-graph-gated bounded multi-cycle research orchestration.

This is a strict composition layer over the existing one-action research cycle and
request-queue contract. Before every possible execution it rebuilds the current mission
state, revalidates the selected epistemic graph and verifier artifacts, and refuses to
consume another request when the targeted hypothesis/claim is falsified, contradicted,
contested, or awaiting positive domain closeout.

It does not generate requests, mutate the graph, invent hypotheses, perform network
searches, or execute physical experiments.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .epistemic_gate import evaluate_epistemic_gate
from .kernel import ResearchLoopError
from .multicycle import load_request_queue
from .research_cycle import run_research_cycle

EPISTEMIC_MULTICYCLE_SCHEMA_VERSION = "1.0"
EPISTEMIC_MULTICYCLE_POLICY_VERSION = "1.0"

_DEFAULT_MAX_CYCLES = 8
_HARD_MAX_CYCLES = 32
_TERMINAL_PROBE_STATUSES = {
    "stopped_current_scope",
    "manual_review_required",
    "blocked",
    "authorization_denied",
}


class EpistemicMultiCycleError(ResearchLoopError):
    """Raised when graph-gated repeated execution cannot proceed safely."""


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EpistemicMultiCycleError(f"{field} must be a non-empty string")
    return value.strip()


def _positive_int(value: object, field: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise EpistemicMultiCycleError(
            f"{field} must be an integer from 1 to {maximum}"
        )
    return value


def _selected_action(authorization: object) -> dict[str, Any] | None:
    if not isinstance(authorization, Mapping):
        return None
    selected = authorization.get("selected_action")
    return dict(selected) if isinstance(selected, Mapping) else None


def _verify_request_matches_selected_action(
    request: Mapping[str, Any], selected_action: Mapping[str, Any]
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
        raise EpistemicMultiCycleError(
            "predeclared request queue does not match the current planner-selected action: "
            f"request expects {expected_type}@{expected_version}, planner selected "
            f"{actual_type}@{actual_version}"
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
    return hashlib.sha256(encoded).hexdigest()


def _execution_record(
    *,
    cycle_index: int,
    gate: Mapping[str, Any],
    probe: Mapping[str, Any] | None,
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
        "epistemic_gate": dict(gate),
        "probe_status": probe.get("cycle_status") if isinstance(probe, Mapping) else None,
        "probe_before_transition": (
            probe.get("before_transition") if isinstance(probe, Mapping) else None
        ),
        "request": dict(request) if isinstance(request, Mapping) else None,
        "execution_cycle_status": (
            execution_cycle.get("cycle_status")
            if isinstance(execution_cycle, Mapping)
            else None
        ),
        "execution": (
            execution_cycle.get("execution")
            if isinstance(execution_cycle, Mapping)
            else None
        ),
        "before_state_fingerprint": _state_fingerprint(
            probe.get("before_planning_state") if isinstance(probe, Mapping) else None
        ),
        "after_state_fingerprint": _state_fingerprint(after_state),
        "after_transition": (
            execution_cycle.get("after_transition")
            if isinstance(execution_cycle, Mapping)
            else None
        ),
    }


def _gate_stop_status(directive: str) -> tuple[str, str]:
    mapping = {
        "stop_falsified_target": (
            "epistemic_falsification_stop",
            "Verified falsification stopped the selected line of inquiry before another request was consumed.",
        ),
        "manual_discrimination_required": (
            "epistemic_discrimination_required",
            "Verified contradiction or conflict requires a stronger discriminating step before automatic repetition.",
        ),
        "domain_closeout_required": (
            "epistemic_domain_closeout_required",
            "Provisionally supported status requires domain closeout before further confirmatory repetition.",
        ),
    }
    if directive not in mapping:
        raise EpistemicMultiCycleError(
            f"unsupported non-executable epistemic directive: {directive!r}"
        )
    return mapping[directive]


def run_epistemically_bounded_multicycle(
    adapter_id: str,
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    graph_path: str | Path,
    epistemic_workstream_id: str,
    epistemic_target_node_ids: Sequence[object],
    runtime_context_path: str | Path | None = None,
    artifact_root: str | Path | None = None,
    research_run: str | Path | None = None,
    action_registry_path: str | Path | None = None,
    request_queue_path: str | Path | None = None,
    request_root: str | Path | None = None,
    max_cycles: int = _DEFAULT_MAX_CYCLES,
) -> dict[str, Any]:
    """Run repeated typed actions only while selected verified epistemic state permits it."""
    max_cycles = _positive_int(max_cycles, "max_cycles", maximum=_HARD_MAX_CYCLES)
    adapter = _nonempty_text(adapter_id, "adapter_id")
    root = Path(repository_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise EpistemicMultiCycleError(f"repository_root must be a directory: {root}")
    queue = (
        load_request_queue(request_queue_path, request_root=request_root)
        if request_queue_path is not None
        else None
    )
    if queue is not None and queue["adapter_id"] != adapter:
        raise EpistemicMultiCycleError(
            "request queue adapter_id does not match the requested research adapter"
        )
    requests = queue["requests"] if queue is not None else []
    request_index = 0
    cycles: list[dict[str, Any]] = []
    actions_executed = 0
    seen_after_fingerprints: set[str] = set()
    program_status: str | None = None
    stop_reason: str | None = None

    for cycle_index in range(1, max_cycles + 1):
        gate = evaluate_epistemic_gate(
            adapter_id=adapter,
            workstream_id=epistemic_workstream_id,
            target_node_ids=epistemic_target_node_ids,
            mission_path=mission_path,
            graph_path=graph_path,
            repository_root=root,
            runtime_context_path=runtime_context_path,
            artifact_root=artifact_root,
        )
        directive = gate["directive"]
        if directive.get("automatic_execution_permitted") is not True:
            cycles.append(
                _execution_record(
                    cycle_index=cycle_index,
                    gate=gate,
                    probe=None,
                    request=None,
                    execution_cycle=None,
                )
            )
            program_status, stop_reason = _gate_stop_status(str(directive.get("directive")))
            break
        if directive.get("directive") != "continue_discriminating_research":
            raise EpistemicMultiCycleError(
                "epistemic gate permitted execution with an unsupported directive"
            )

        probe = run_research_cycle(
            adapter,
            repository_root=root,
            research_run=research_run,
            action_registry_path=action_registry_path,
            request_path=None,
        )
        probe_status = probe.get("cycle_status")
        if probe_status in _TERMINAL_PROBE_STATUSES:
            cycles.append(
                _execution_record(
                    cycle_index=cycle_index,
                    gate=gate,
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
            raise EpistemicMultiCycleError(
                f"unexpected probe cycle status: {probe_status!r}"
            )
        selected = _selected_action(probe.get("authorization"))
        if selected is None:
            raise EpistemicMultiCycleError(
                "explicit-request probe did not retain one planner-selected authorized action"
            )
        if request_index >= len(requests):
            cycles.append(
                _execution_record(
                    cycle_index=cycle_index,
                    gate=gate,
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
            adapter,
            repository_root=root,
            research_run=research_run,
            action_registry_path=action_registry_path,
            request_path=request["path"],
        )
        record = _execution_record(
            cycle_index=cycle_index,
            gate=gate,
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
            raise EpistemicMultiCycleError(
                "completed execution cycle omitted after planning state"
            )
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
            raise EpistemicMultiCycleError(
                f"unsupported after-transition type: {transition_type!r}"
            )
    else:
        program_status = "max_cycles_reached"
        stop_reason = "The hard-bounded invocation reached its configured cycle limit."

    if program_status is None or stop_reason is None:
        raise EpistemicMultiCycleError(
            "epistemic multi-cycle orchestration ended without a stop status"
        )
    return {
        "schema_version": EPISTEMIC_MULTICYCLE_SCHEMA_VERSION,
        "epistemic_multicycle_policy_version": EPISTEMIC_MULTICYCLE_POLICY_VERSION,
        "adapter_id": adapter,
        "epistemic_workstream_id": epistemic_workstream_id,
        "epistemic_target_node_ids": list(epistemic_target_node_ids),
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
            "epistemic_gate_revalidated_before_every_possible_execution": True,
            "automatic_request_generation_available": False,
            "only_predeclared_checksum_bound_requests_consumed": True,
            "one_action_per_cycle_enforced_by_delegate": True,
            "planner_rebuilt_after_every_execution": True,
            "authorization_rechecked_for_every_execution": True,
            "graph_mutation_available": False,
            "generic_command_generation_available": False,
            "network_access_initiated_by_orchestrator": False,
            "physical_experiment_execution_initiated_by_orchestrator": False,
            "scientific_evidence_upgraded_by_orchestrator": False,
        },
    }


__all__ = [
    "EPISTEMIC_MULTICYCLE_POLICY_VERSION",
    "EPISTEMIC_MULTICYCLE_SCHEMA_VERSION",
    "EpistemicMultiCycleError",
    "run_epistemically_bounded_multicycle",
]
