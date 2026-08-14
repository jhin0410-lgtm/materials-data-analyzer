"""Hardening facade for the policy-authorized closed-loop core.

The core module contains the previously reviewed execute/record/regate implementation.
This facade keeps its public and focused-test surface stable while enforcing three
cross-cutting invariants before/around side effects:

* the exact pinned mission must allow explicit typed computational requests;
* record-only transition lineage metadata must be structurally usable before execution;
* the existing re-entrant research-ledger lock remains held from action execution
  through successor-graph ingestion, so a concurrent append cannot orphan a verified
  action from its graph transition.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from . import policy_authorized_closed_loop_core as _core
from .action_output_ledger_transaction import shared_research_ledger_transaction_lock

CLOSED_LOOP_SCHEMA_VERSION = _core.CLOSED_LOOP_SCHEMA_VERSION
CLOSED_LOOP_POLICY_VERSION = "1.3"
RESULT_RECORD_PLAN_SCHEMA_VERSION = _core.RESULT_RECORD_PLAN_SCHEMA_VERSION
PolicyAuthorizedClosedLoopError = _core.PolicyAuthorizedClosedLoopError

# Preserve the focused helper surface used by tests and downstream audits.  Mutable
# dependencies are intentionally module globals so monkeypatch-based contract tests keep
# controlling the exact objects used by the core runner.
evaluate_epistemic_gate = _core.evaluate_epistemic_gate
build_research_program = _core.build_research_program
run_research_cycle = _core.run_research_cycle
run_pinned_research_cycle = _core.run_pinned_research_cycle
load_research_state = _core.load_research_state

_read_json_snapshot = _core._read_json_snapshot
_preflight_output_root = _core._preflight_output_root
_verify_gate_snapshot_bindings = _core._verify_gate_snapshot_bindings
_apply_record_only_action_result = _core._apply_record_only_action_result
load_result_record_plan = _core.load_result_record_plan

_ORIGINAL_SNAPSHOT_STATIC_FILE = _core._snapshot_static_file
_ORIGINAL_PREFLIGHT_GRAPH_AND_RECORDS = _core._preflight_graph_and_records


def _require_explicit_typed_action_policy(mission_value: Mapping[str, Any]) -> None:
    policy = mission_value.get("autonomy_policy")
    if not isinstance(policy, Mapping):
        raise PolicyAuthorizedClosedLoopError(
            "pinned mission is missing autonomy_policy before typed execution"
        )
    mode = policy.get("typed_computational_actions")
    if mode != "explicit_request":
        raise PolicyAuthorizedClosedLoopError(
            "pinned mission does not authorize explicit typed computational actions: "
            f"typed_computational_actions={mode!r}"
        )


def _snapshot_static_file(source: str | Path, *, field: str) -> dict[str, Any]:
    snapshot = _ORIGINAL_SNAPSHOT_STATIC_FILE(source, field=field)
    if field == "mission_path":
        value = snapshot.get("value")
        if not isinstance(value, Mapping):
            raise PolicyAuthorizedClosedLoopError("pinned mission snapshot is malformed")
        _require_explicit_typed_action_policy(value)
    return snapshot


def _preflight_graph_and_records(
    *,
    graph_path: Path,
    records: Sequence[Mapping[str, Any]],
    target_ids: Sequence[str],
) -> dict[str, Any]:
    binding = _ORIGINAL_PREFLIGHT_GRAPH_AND_RECORDS(
        graph_path=graph_path,
        records=records,
        target_ids=target_ids,
    )
    graph, _, digest = _read_json_snapshot(graph_path)
    if digest != binding["sha256"]:
        raise PolicyAuthorizedClosedLoopError(
            "graph changed while closed-loop preflight was validating it"
        )
    metadata = graph.get("metadata")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise PolicyAuthorizedClosedLoopError("base graph metadata must be an object")
    if isinstance(metadata, Mapping):
        lineage = metadata.get("record_only_transition_lineage")
        if lineage is not None and not isinstance(lineage, list):
            raise PolicyAuthorizedClosedLoopError(
                "base graph metadata.record_only_transition_lineage must be a list"
            )
    return binding


def _sync_core_dependencies() -> None:
    """Keep monkeypatchable facade dependencies authoritative for the core invocation."""
    _core.evaluate_epistemic_gate = evaluate_epistemic_gate
    _core.build_research_program = build_research_program
    _core.run_research_cycle = run_research_cycle
    _core.run_pinned_research_cycle = run_pinned_research_cycle
    _core.load_research_state = load_research_state
    _core._snapshot_static_file = _snapshot_static_file
    _core._preflight_graph_and_records = _preflight_graph_and_records
    _core._apply_record_only_action_result = _apply_record_only_action_result
    _core.CLOSED_LOOP_POLICY_VERSION = CLOSED_LOOP_POLICY_VERSION


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
    max_cycles: int = 8,
) -> dict[str, Any]:
    """Run the core loop while preserving mission and ledger authority end-to-end."""
    _sync_core_dependencies()
    # This is deliberately the existing kernel-backed, re-entrant ledger lock.  Nested
    # executor/recovery acquisitions reuse the same lock ownership context.  Holding it
    # for the bounded invocation is stronger than the minimum execute->ingest interval
    # and prevents a concurrent legitimate append from invalidating verifier provenance
    # after this invocation has already committed its action.
    with shared_research_ledger_transaction_lock(research_run):
        result = _core.run_policy_authorized_closed_loop(
            adapter_id,
            repository_root=repository_root,
            mission_path=mission_path,
            initial_graph_path=initial_graph_path,
            epistemic_workstream_id=epistemic_workstream_id,
            epistemic_target_node_ids=epistemic_target_node_ids,
            runtime_context_path=runtime_context_path,
            artifact_root=artifact_root,
            research_run=research_run,
            action_registry_path=action_registry_path,
            request_queue_path=request_queue_path,
            result_record_plan_path=result_record_plan_path,
            output_root=output_root,
            request_root=request_root,
            max_cycles=max_cycles,
        )
    boundary = result.get("autonomy_boundary")
    if isinstance(boundary, dict):
        boundary["mission_typed_action_policy_enforced_from_pinned_snapshot"] = True
        boundary["ledger_lock_held_through_successor_ingestion"] = True
    result["closed_loop_policy_version"] = CLOSED_LOOP_POLICY_VERSION
    return result


__all__ = [
    "CLOSED_LOOP_POLICY_VERSION",
    "CLOSED_LOOP_SCHEMA_VERSION",
    "RESULT_RECORD_PLAN_SCHEMA_VERSION",
    "PolicyAuthorizedClosedLoopError",
    "load_result_record_plan",
    "run_policy_authorized_closed_loop",
]
