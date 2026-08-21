"""Bounded recursive research-cycle checkpoints over discrepancy planning handoffs.

This module intentionally does not execute actions. It verifies that a validated
model/evidence discrepancy handoff has entered a *fresh* autonomous inquiry plan and
that an explicit typed match record points to the planner's independently selected
candidate. Only then may the checkpoint advance to ``explicit_authorization_required``.

A discrepancy proposal is never an action. The action remains planner-owned and must
still pass the repository's existing independent authorization / typed-executor chain.
Planner stop decisions and recursive ancestry are authoritative fail-closed boundaries.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .autonomous_inquiry import AUTONOMOUS_INQUIRY_POLICY_VERSION
from .kernel import ResearchLoopError

RECURSIVE_CYCLE_SCHEMA_VERSION = "1.0"
RECURSIVE_CYCLE_POLICY_VERSION = "1.0"
CANDIDATE_MATCH_SCHEMA_VERSION = "1.0"
CANDIDATE_MATCH_POLICY_VERSION = "1.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RecursiveResearchCycleError(ResearchLoopError):
    """Raised when recursive planning ancestry or candidate ownership drifts."""


def _canonical_sha256(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RecursiveResearchCycleError(
            "recursive cycle state must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RecursiveResearchCycleError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise RecursiveResearchCycleError(f"{field} must be a sequence")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise RecursiveResearchCycleError(f"{field} must be non-empty trimmed text")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if _SHA256.fullmatch(text) is None:
        raise RecursiveResearchCycleError(f"{field} must be lowercase SHA-256")
    return text


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RecursiveResearchCycleError(f"{field} must be an integer >= 1")
    return value


def _verified_embedded_sha(
    value: Mapping[str, Any], *, field: str, sha_field: str
) -> str:
    snapshot = dict(value)
    embedded = _sha(snapshot.pop(sha_field, None), f"{field}.{sha_field}")
    actual = _canonical_sha256(snapshot)
    if actual != embedded:
        raise RecursiveResearchCycleError(
            f"{field}.{sha_field} does not match canonical content"
        )
    return embedded


def _verify_handoff(
    handoff: Mapping[str, Any],
) -> tuple[str, dict[str, Any], list[dict[str, Any]], str | None]:
    if handoff.get("schema_version") != "1.0":
        raise RecursiveResearchCycleError(
            "unsupported discrepancy planning handoff schema_version"
        )
    if handoff.get("policy_version") != "1.0":
        raise RecursiveResearchCycleError(
            "unsupported discrepancy planning handoff policy_version"
        )
    handoff_sha = _verified_embedded_sha(
        handoff,
        field="planning_handoff",
        sha_field="handoff_sha256",
    )
    boundary = _mapping(
        handoff.get("planner_boundary"), "planning_handoff.planner_boundary"
    )
    required_false = {
        "current_planner_frontier_modified",
        "current_selected_action_modified",
        "executable_candidate_created",
        "candidate_availability_verified",
        "candidate_registry_binding_created",
        "action_authorization_granted",
        "automatic_execution_authorized",
        "scientific_status_changed",
    }
    for field in required_false:
        if boundary.get(field) is not False:
            raise RecursiveResearchCycleError(
                f"planning handoff weakened non-authoritative boundary: {field}"
            )
    if boundary.get("fresh_planner_candidate_matching_required") is not True:
        raise RecursiveResearchCycleError(
            "planning handoff must require fresh planner candidate matching"
        )

    target = dict(_mapping(handoff.get("target"), "planning_handoff.target"))
    for field in ("graph_id", "node_id", "node_type", "statement"):
        _text(target.get(field), f"planning_handoff.target.{field}")

    objectives: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(
        _sequence(
            handoff.get("research_objectives"),
            "planning_handoff.research_objectives",
        )
    ):
        item = dict(
            _mapping(raw, f"planning_handoff.research_objectives[{index}]")
        )
        objective_id = _text(
            item.get("objective_id"), f"objective[{index}].objective_id"
        )
        if objective_id in seen_ids:
            raise RecursiveResearchCycleError(
                "planning handoff contains duplicate objective_id"
            )
        seen_ids.add(objective_id)
        _text(item.get("source_proposal_id"), f"objective[{index}].source_proposal_id")
        _positive_int(item.get("source_rank"), f"objective[{index}].source_rank")
        _text(
            item.get("research_action_class"),
            f"objective[{index}].research_action_class",
        )
        if item.get("planner_candidate_required") is not True:
            raise RecursiveResearchCycleError(
                "every discrepancy objective requires a planner candidate"
            )
        if item.get("availability_asserted") is not False:
            raise RecursiveResearchCycleError(
                "discrepancy objective cannot assert availability"
            )
        if item.get("automatic_execution_authorized") is not False:
            raise RecursiveResearchCycleError(
                "discrepancy objective cannot authorize execution"
            )
        objectives.append(item)

    source_ancestry = _mapping(
        handoff.get("source_ancestry"), "planning_handoff.source_ancestry"
    )
    previous_report_sha = source_ancestry.get("previous_discrepancy_report_sha256")
    if previous_report_sha is not None:
        previous_report_sha = _sha(
            previous_report_sha,
            "planning_handoff.source_ancestry.previous_discrepancy_report_sha256",
        )
    return handoff_sha, target, objectives, previous_report_sha


def _verify_plan(
    plan: Mapping[str, Any],
) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None, dict[str, Any]]:
    if plan.get("schema_version") != "1.0":
        raise RecursiveResearchCycleError(
            "unsupported autonomous inquiry plan schema_version"
        )
    if plan.get("policy_version") != AUTONOMOUS_INQUIRY_POLICY_VERSION:
        raise RecursiveResearchCycleError(
            "unsupported autonomous inquiry plan policy_version"
        )
    plan_sha = _verified_embedded_sha(
        plan, field="fresh_plan", sha_field="plan_sha256"
    )
    boundary = _mapping(plan.get("autonomy_boundary"), "fresh_plan.autonomy_boundary")
    for field in (
        "empirical_evidence_created",
        "network_access_performed",
        "physical_experiment_execution_performed",
        "automatic_execution_authorized",
        "scientific_status_changed",
        "mission_mutated",
    ):
        if boundary.get(field) is not False:
            raise RecursiveResearchCycleError(
                f"fresh autonomous plan weakened planning-only boundary: {field}"
            )
    handoff = _mapping(plan.get("handoff"), "fresh_plan.handoff")
    if (
        handoff.get("request_compiled") is not False
        or handoff.get("execution_performed") is not False
    ):
        raise RecursiveResearchCycleError(
            "fresh planner already crossed request/execution boundary"
        )

    ranked: list[dict[str, Any]] = []
    action_ids: set[str] = set()
    for index, raw in enumerate(
        _sequence(plan.get("ranked_actions"), "fresh_plan.ranked_actions")
    ):
        action = dict(_mapping(raw, f"fresh_plan.ranked_actions[{index}]"))
        action_id = _text(
            action.get("action_id"), f"ranked_actions[{index}].action_id"
        )
        if action_id in action_ids:
            raise RecursiveResearchCycleError(
                "fresh planner contains duplicate action_id"
            )
        action_ids.add(action_id)
        _text(action.get("action_class"), f"ranked_actions[{index}].action_class")
        if action.get("automatic_execution_authorized") is not False:
            raise RecursiveResearchCycleError(
                "planner candidate cannot authorize execution"
            )
        ranked.append(action)

    selected_raw = plan.get("selected_next_action")
    selected = (
        None
        if selected_raw is None
        else dict(_mapping(selected_raw, "fresh_plan.selected_next_action"))
    )
    if selected is not None:
        selected_id = _text(
            selected.get("action_id"), "selected_next_action.action_id"
        )
        matches = [item for item in ranked if item.get("action_id") == selected_id]
        if len(matches) != 1 or matches[0] != selected:
            raise RecursiveResearchCycleError(
                "selected_next_action must be exactly one independently ranked planner candidate"
            )

    stop = dict(_mapping(plan.get("stop_decision"), "fresh_plan.stop_decision"))
    if not isinstance(stop.get("stop"), bool):
        raise RecursiveResearchCycleError("fresh planner stop_decision.stop must be boolean")
    _text(stop.get("reason"), "fresh_plan.stop_decision.reason")
    _text(stop.get("next_mode"), "fresh_plan.stop_decision.next_mode")
    if stop["stop"] is True and selected is not None:
        raise RecursiveResearchCycleError(
            "fresh planner stop decision cannot retain a selected_next_action"
        )
    if stop["stop"] is False and selected is None:
        raise RecursiveResearchCycleError(
            "fresh planner cannot continue without a selected_next_action"
        )
    if handoff.get("required_for_selected_action") is not (selected is not None):
        raise RecursiveResearchCycleError(
            "fresh planner handoff requirement disagrees with selected_next_action"
        )
    return plan_sha, ranked, selected, stop


def _previous_checkpoint(
    previous: Mapping[str, Any] | None,
    *,
    target: Mapping[str, Any],
    current_plan_sha: str,
    previous_discrepancy_report_sha256: str | None,
) -> tuple[str | None, int]:
    if previous is None:
        if previous_discrepancy_report_sha256 is not None:
            raise RecursiveResearchCycleError(
                "successor discrepancy handoff requires previous recursive checkpoint ancestry"
            )
        return None, 1
    if previous.get("schema_version") != RECURSIVE_CYCLE_SCHEMA_VERSION:
        raise RecursiveResearchCycleError("previous checkpoint schema_version drifted")
    if previous.get("policy_version") != RECURSIVE_CYCLE_POLICY_VERSION:
        raise RecursiveResearchCycleError("previous checkpoint policy_version drifted")
    previous_sha = _verified_embedded_sha(
        previous,
        field="previous_checkpoint",
        sha_field="checkpoint_sha256",
    )
    previous_target = _mapping(
        previous.get("target"), "previous_checkpoint.target"
    )
    # A verified epistemic transition is allowed to advance graph_id, but it may not
    # silently change the stable hypothesis/claim identity under the recursive cycle.
    for field in ("node_id", "node_type", "statement"):
        if previous_target.get(field) != target.get(field):
            raise RecursiveResearchCycleError(
                f"recursive cycle target identity changed across checkpoints: {field}"
            )
    if (
        previous_discrepancy_report_sha256 is None
        and previous_target.get("graph_id") != target.get("graph_id")
    ):
        raise RecursiveResearchCycleError(
            "recursive cycle graph identity changed without successor discrepancy ancestry"
        )
    ancestry = _mapping(
        previous.get("ancestry"), "previous_checkpoint.ancestry"
    )
    if previous_discrepancy_report_sha256 is not None:
        previous_source_report_sha = _sha(
            ancestry.get("source_discrepancy_report_sha256"),
            "previous_checkpoint.ancestry.source_discrepancy_report_sha256",
        )
        if previous_source_report_sha != previous_discrepancy_report_sha256:
            raise RecursiveResearchCycleError(
                "successor discrepancy ancestry does not descend from the previous checkpoint report"
            )
    previous_plan_sha = _sha(
        ancestry.get("fresh_plan_sha256"),
        "previous_checkpoint.ancestry.fresh_plan_sha256",
    )
    if previous_plan_sha == current_plan_sha:
        raise RecursiveResearchCycleError(
            "fresh planning cycle required but previous plan SHA was reused"
        )
    cycle_index = (
        _positive_int(previous.get("cycle_index"), "previous_checkpoint.cycle_index")
        + 1
    )
    return previous_sha, cycle_index


def _validate_match_record(
    record: Mapping[str, Any],
    *,
    handoff_sha: str,
    plan_sha: str,
    objectives: Sequence[Mapping[str, Any]],
    selected: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if record.get("schema_version") != CANDIDATE_MATCH_SCHEMA_VERSION:
        raise RecursiveResearchCycleError(
            "unsupported candidate match schema_version"
        )
    if record.get("policy_version") != CANDIDATE_MATCH_POLICY_VERSION:
        raise RecursiveResearchCycleError(
            "unsupported candidate match policy_version"
        )
    if record.get("handoff_sha256") != handoff_sha:
        raise RecursiveResearchCycleError(
            "candidate match handoff SHA substitution detected"
        )
    if record.get("fresh_plan_sha256") != plan_sha:
        raise RecursiveResearchCycleError(
            "candidate match fresh-plan SHA substitution detected"
        )
    if selected is None:
        raise RecursiveResearchCycleError(
            "candidate match supplied even though the fresh planner selected no action"
        )
    objective_id = _text(
        record.get("objective_id"), "candidate_match.objective_id"
    )
    objective_matches = [
        item for item in objectives if item.get("objective_id") == objective_id
    ]
    if len(objective_matches) != 1:
        raise RecursiveResearchCycleError(
            "candidate match objective is not in discrepancy handoff"
        )
    objective = dict(objective_matches[0])
    for field in ("source_proposal_id", "source_rank"):
        if record.get(field) != objective.get(field):
            raise RecursiveResearchCycleError(
                f"candidate match {field} substitution detected"
            )
    candidate_id = _text(
        record.get("candidate_action_id"), "candidate_match.candidate_action_id"
    )
    if candidate_id != selected.get("action_id"):
        raise RecursiveResearchCycleError(
            "candidate match must point to the fresh planner's selected_next_action"
        )
    candidate_class = _text(
        record.get("candidate_action_class"),
        "candidate_match.candidate_action_class",
    )
    if candidate_class != selected.get("action_class"):
        raise RecursiveResearchCycleError(
            "candidate action_class substitution detected"
        )
    if candidate_class != objective.get("research_action_class"):
        raise RecursiveResearchCycleError(
            "planner-selected action class does not match discrepancy objective class"
        )
    execution_mode = _text(
        record.get("candidate_execution_mode"),
        "candidate_match.candidate_execution_mode",
    )
    if execution_mode != selected.get("execution_mode"):
        raise RecursiveResearchCycleError(
            "candidate execution_mode substitution detected"
        )
    rationale = _text(
        record.get("match_rationale"), "candidate_match.match_rationale"
    )
    normalized = {
        "schema_version": CANDIDATE_MATCH_SCHEMA_VERSION,
        "policy_version": CANDIDATE_MATCH_POLICY_VERSION,
        "handoff_sha256": handoff_sha,
        "fresh_plan_sha256": plan_sha,
        "objective_id": objective_id,
        "source_proposal_id": objective["source_proposal_id"],
        "source_rank": objective["source_rank"],
        "candidate_action_id": candidate_id,
        "candidate_action_class": candidate_class,
        "candidate_execution_mode": execution_mode,
        "match_rationale": rationale,
        "match_semantics": "explicit_typed_record_not_heuristic_action_injection",
        "availability_promoted": False,
        "authorization_granted": False,
    }
    return normalized, objective


def build_recursive_research_cycle_checkpoint(
    *,
    planning_handoff: Mapping[str, Any],
    fresh_plan: Mapping[str, Any],
    candidate_match: Mapping[str, Any] | None = None,
    previous_checkpoint: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Advance discrepancy planning only to a verified fresh-plan checkpoint."""
    handoff = _mapping(planning_handoff, "planning_handoff")
    plan = _mapping(fresh_plan, "fresh_plan")
    handoff_sha, target, objectives, previous_report_sha = _verify_handoff(handoff)
    plan_sha, ranked, selected, stop_decision = _verify_plan(plan)
    previous_sha, cycle_index = _previous_checkpoint(
        previous_checkpoint,
        target=target,
        current_plan_sha=plan_sha,
        previous_discrepancy_report_sha256=previous_report_sha,
    )

    match_record: dict[str, Any] | None = None
    matched_objective: dict[str, Any] | None = None
    if candidate_match is not None:
        match_record, matched_objective = _validate_match_record(
            _mapping(candidate_match, "candidate_match"),
            handoff_sha=handoff_sha,
            plan_sha=plan_sha,
            objectives=objectives,
            selected=selected,
        )

    if stop_decision["stop"] is True:
        checkpoint_status = "bounded_stop_fresh_planner_decision"
        stop_reason = (
            "Fresh planner explicitly stopped: " + str(stop_decision["reason"])
        )
    elif not objectives:
        checkpoint_status = "bounded_stop_no_research_objective"
        stop_reason = (
            "Validated discrepancy handoff contains no future research objective."
        )
    elif match_record is None:
        checkpoint_status = "bounded_stop_no_matching_candidate"
        stop_reason = (
            "No explicit typed record matches a discrepancy objective to the fresh "
            "planner's independently selected candidate."
        )
    else:
        checkpoint_status = "explicit_authorization_required"
        stop_reason = None

    checkpoint: dict[str, Any] = {
        "schema_version": RECURSIVE_CYCLE_SCHEMA_VERSION,
        "policy_version": RECURSIVE_CYCLE_POLICY_VERSION,
        "cycle_id": f"recursive:{target['graph_id']}:{target['node_id']}",
        "cycle_index": cycle_index,
        "checkpoint_status": checkpoint_status,
        "target": dict(target),
        "ancestry": {
            "previous_checkpoint_sha256": previous_sha,
            "source_discrepancy_report_sha256": _sha(
                handoff.get("source_discrepancy_report_sha256"),
                "planning_handoff.source_discrepancy_report_sha256",
            ),
            "planning_handoff_sha256": handoff_sha,
            "fresh_plan_sha256": plan_sha,
        },
        "fresh_planner_state": {
            "ranked_candidate_count": len(ranked),
            "selected_candidate_id": selected.get("action_id") if selected else None,
            "stop_decision": stop_decision,
        },
        "matched_objective": matched_objective,
        "candidate_match": match_record,
        "authorization_handoff": {
            "required": checkpoint_status == "explicit_authorization_required",
            "destination": "existing_independent_action_authorization_and_typed_executor_chain",
            "authorization_granted": False,
            "request_compiled": False,
            "execution_performed": False,
        },
        "epistemic_handoff": {
            "execution_result_verified": False,
            "epistemic_interpretation_performed": False,
            "epistemic_transition_verified": False,
            "hypothesis_portfolio_refreshed": False,
            "re_diagnosis_performed": False,
        },
        "bounded_stop": {
            "stopped": checkpoint_status.startswith("bounded_stop_"),
            "reason": stop_reason,
            "reopen_condition": (
                "Generate a fresh planner result after the bound budget/scope/evidence state changes."
                if checkpoint_status == "bounded_stop_fresh_planner_decision"
                else (
                    "Generate a new autonomous inquiry plan and supply an explicit typed objective/candidate match record."
                    if checkpoint_status == "bounded_stop_no_matching_candidate"
                    else None
                )
            ),
        },
        "autonomy_boundary": {
            "critic_proposal_executed_directly": False,
            "planner_candidate_injected": False,
            "action_type_synthesized": False,
            "registry_synthesized": False,
            "availability_promoted": False,
            "authorization_granted": False,
            "automatic_execution_authorized": False,
            "execution_performed": False,
            "network_access_performed": False,
            "physical_experiment_executed": False,
            "empirical_evidence_created": False,
            "epistemic_edge_created": False,
            "scientific_status_changed": False,
        },
    }
    checkpoint["checkpoint_sha256"] = _canonical_sha256(checkpoint)
    return checkpoint


def validate_recursive_research_cycle_checkpoint(
    checkpoint: Mapping[str, Any],
    *,
    planning_handoff: Mapping[str, Any],
    fresh_plan: Mapping[str, Any],
    candidate_match: Mapping[str, Any] | None = None,
    previous_checkpoint: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Rebuild a checkpoint from bound inputs; mutation or substitution fails closed."""
    value = dict(_mapping(checkpoint, "checkpoint"))
    embedded = _verified_embedded_sha(
        value,
        field="checkpoint",
        sha_field="checkpoint_sha256",
    )
    rebuilt = build_recursive_research_cycle_checkpoint(
        planning_handoff=planning_handoff,
        fresh_plan=fresh_plan,
        candidate_match=candidate_match,
        previous_checkpoint=previous_checkpoint,
    )
    if rebuilt != checkpoint:
        raise RecursiveResearchCycleError(
            "recursive checkpoint differs from deterministic reconstruction"
        )
    return {
        "checkpoint_sha256": embedded,
        "checkpoint_status": rebuilt["checkpoint_status"],
        "cycle_index": rebuilt["cycle_index"],
        "authorization_granted": False,
        "execution_performed": False,
        "scientific_status_changed": False,
    }


__all__ = [
    "CANDIDATE_MATCH_POLICY_VERSION",
    "CANDIDATE_MATCH_SCHEMA_VERSION",
    "RECURSIVE_CYCLE_POLICY_VERSION",
    "RECURSIVE_CYCLE_SCHEMA_VERSION",
    "RecursiveResearchCycleError",
    "build_recursive_research_cycle_checkpoint",
    "validate_recursive_research_cycle_checkpoint",
]
