"""Validated handoff from discrepancy diagnosis into a future planning cycle.

A discrepancy report may propose useful research directions, but those proposals are not
planner candidates and are never executable actions. This module validates the source
report and projects its ranked proposals into bounded research-objective context for a
*new* planning cycle. It cannot mutate the current planner frontier, select an action,
or authorize execution.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .kernel import ResearchLoopError
from .model_evidence_discrepancy import (
    validate_model_evidence_discrepancy_report,
)

DISCREPANCY_PLANNING_HANDOFF_SCHEMA_VERSION = "1.0"
DISCREPANCY_PLANNING_HANDOFF_POLICY_VERSION = "1.0"
_ALLOWED_EXECUTION_MODES = {"plan_only", "explicit_authorization_required"}
_ALLOWED_PRIORITIES = {"highest", "high", "medium", "low"}


class DiscrepancyPlanningHandoffError(ResearchLoopError):
    """Raised when discrepancy proposals cannot be handed to planning safely."""


def _canonical_sha256(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DiscrepancyPlanningHandoffError(
            "planning handoff state must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DiscrepancyPlanningHandoffError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise DiscrepancyPlanningHandoffError(f"{field} must be a sequence")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise DiscrepancyPlanningHandoffError(f"{field} must be non-empty trimmed text")
    return value


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DiscrepancyPlanningHandoffError(f"{field} must be an integer >= 1")
    return value


def _proposal_objective(raw: object, *, expected_rank: int) -> dict[str, Any]:
    proposal = _mapping(raw, f"ranked_next_actions[{expected_rank - 1}]")
    rank = _positive_integer(
        proposal.get("rank"),
        f"ranked_next_actions[{expected_rank - 1}].rank",
    )
    if rank != expected_rank:
        raise DiscrepancyPlanningHandoffError(
            "ranked discrepancy proposals must use contiguous one-based ranks"
        )
    if proposal.get("availability_asserted") is not False:
        raise DiscrepancyPlanningHandoffError(
            "discrepancy proposal cannot assert action availability"
        )
    if proposal.get("automatic_execution_authorized") is not False:
        raise DiscrepancyPlanningHandoffError(
            "discrepancy proposal cannot authorize execution"
        )
    if proposal.get("information_gain_is_calibrated_probability") is not False:
        raise DiscrepancyPlanningHandoffError(
            "discrepancy proposal cannot invent calibrated information-gain probability"
        )
    execution_mode = _text(
        proposal.get("execution_mode"),
        f"ranked_next_actions[{expected_rank - 1}].execution_mode",
    )
    if execution_mode not in _ALLOWED_EXECUTION_MODES:
        raise DiscrepancyPlanningHandoffError(
            "unsupported discrepancy proposal execution_mode"
        )
    priority = _text(
        proposal.get("information_gain_priority"),
        f"ranked_next_actions[{expected_rank - 1}].information_gain_priority",
    )
    if priority not in _ALLOWED_PRIORITIES:
        raise DiscrepancyPlanningHandoffError(
            "unsupported discrepancy proposal information_gain_priority"
        )
    proposal_id = _text(
        proposal.get("proposal_id"),
        f"ranked_next_actions[{expected_rank - 1}].proposal_id",
    )
    action_class = _text(
        proposal.get("action_class"),
        f"ranked_next_actions[{expected_rank - 1}].action_class",
    )
    return {
        "objective_id": f"planning-objective:{proposal_id}",
        "source_proposal_id": proposal_id,
        "source_rank": rank,
        "research_action_class": action_class,
        "description": _text(
            proposal.get("description"),
            f"ranked_next_actions[{expected_rank - 1}].description",
        ),
        "rationale": _text(
            proposal.get("rationale"),
            f"ranked_next_actions[{expected_rank - 1}].rationale",
        ),
        "information_gain_priority": priority,
        "source_execution_mode": execution_mode,
        "planner_candidate_required": True,
        "candidate_match_status": "not_evaluated_in_current_handoff",
        "action_type": None,
        "action_version": None,
        "action_registry_id": None,
        "availability_asserted": False,
        "automatic_execution_authorized": False,
    }


def build_discrepancy_planning_handoff(
    discrepancy_report: Mapping[str, Any],
    *,
    evaluated_graph: Mapping[str, Any],
    hypothesis_portfolio: Mapping[str, Any] | None = None,
    previous_discrepancy_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project a validated discrepancy report into future-planning context only."""
    report = dict(_mapping(discrepancy_report, "discrepancy_report"))
    verified = validate_model_evidence_discrepancy_report(
        report,
        evaluated_graph=evaluated_graph,
        hypothesis_portfolio=hypothesis_portfolio,
        previous_report=previous_discrepancy_report,
    )
    target = _mapping(report.get("target"), "discrepancy_report.target")
    stop = _mapping(
        report.get("stop_recommendation"),
        "discrepancy_report.stop_recommendation",
    )
    autonomy = _mapping(
        report.get("autonomy_boundary"),
        "discrepancy_report.autonomy_boundary",
    )
    if autonomy.get("scientific_status_changed") is not False:
        raise DiscrepancyPlanningHandoffError(
            "source discrepancy report changed scientific status"
        )
    if autonomy.get("automatic_execution_authorized") is not False:
        raise DiscrepancyPlanningHandoffError(
            "source discrepancy report authorized execution"
        )

    proposals = _sequence(
        report.get("ranked_next_actions"),
        "discrepancy_report.ranked_next_actions",
    )
    objectives = [
        _proposal_objective(raw, expected_rank=index)
        for index, raw in enumerate(proposals, start=1)
    ]
    objective_ids = [str(item["objective_id"]) for item in objectives]
    if len(objective_ids) != len(set(objective_ids)):
        raise DiscrepancyPlanningHandoffError(
            "discrepancy proposals map to duplicate planning objective IDs"
        )

    diagnoses = [
        _text(item, f"validated.diagnosis_types[{index}]")
        for index, item in enumerate(
            _sequence(verified.get("diagnosis_types", []), "validated.diagnosis_types")
        )
    ]
    gates = _mapping(report.get("gates"), "discrepancy_report.gates")
    failed_gates: list[str] = []
    passed_gates: list[str] = []
    for gate_name, raw_gate in gates.items():
        name = _text(gate_name, "discrepancy_report.gates key")
        gate = _mapping(raw_gate, f"discrepancy_report.gates.{name}")
        passed = gate.get("passed")
        if passed is True:
            passed_gates.append(name)
        elif passed is False:
            failed_gates.append(name)
        else:
            raise DiscrepancyPlanningHandoffError(
                f"discrepancy gate {name} has no boolean passed state"
            )

    report_ancestry = _mapping(
        report.get("ancestry"),
        "discrepancy_report.ancestry",
    )
    portfolio_state = report.get("hypothesis_portfolio_state")
    portfolio_directive = None
    if portfolio_state is not None:
        portfolio = _mapping(
            portfolio_state,
            "discrepancy_report.hypothesis_portfolio_state",
        )
        portfolio_directive = portfolio.get("research_directive")
        if portfolio_directive is not None:
            portfolio_directive = _text(
                portfolio_directive,
                "discrepancy_report.hypothesis_portfolio_state.research_directive",
            )

    next_planning_cycle_required = bool(objectives) or bool(failed_gates) or bool(diagnoses)
    if not next_planning_cycle_required:
        # An empty/no-diagnosis report is still not permission to mutate the current plan.
        planning_state = "bounded_no_objective_handoff"
    elif objectives:
        planning_state = "fresh_planner_candidate_generation_required"
    else:
        planning_state = "fresh_planner_review_required_no_proposal_available"

    result: dict[str, Any] = {
        "schema_version": DISCREPANCY_PLANNING_HANDOFF_SCHEMA_VERSION,
        "policy_version": DISCREPANCY_PLANNING_HANDOFF_POLICY_VERSION,
        "handoff_id": (
            f"discrepancy-planning:{target.get('graph_id')}:{target.get('node_id')}:"
            f"{str(verified['report_sha256'])[:12]}"
        ),
        "source_discrepancy_report_sha256": verified["report_sha256"],
        "source_iteration_index": verified["iteration_index"],
        "target": {
            "graph_id": _text(target.get("graph_id"), "discrepancy_report.target.graph_id"),
            "node_id": _text(target.get("node_id"), "discrepancy_report.target.node_id"),
            "node_type": _text(target.get("node_type"), "discrepancy_report.target.node_type"),
            "statement": _text(target.get("statement"), "discrepancy_report.target.statement"),
        },
        "diagnosis_context": {
            "diagnosis_types": diagnoses,
            "passed_gates": sorted(passed_gates),
            "failed_gates": sorted(failed_gates),
            "stop_recommendation": _text(
                stop.get("recommendation"),
                "discrepancy_report.stop_recommendation.recommendation",
            ),
            "stop_rationale": _text(
                stop.get("rationale"),
                "discrepancy_report.stop_recommendation.rationale",
            ),
            "hypothesis_portfolio_directive": portfolio_directive,
        },
        "research_objectives": objectives,
        "planning_handoff_state": planning_state,
        "next_planning_cycle_required": next_planning_cycle_required,
        "source_ancestry": {
            "previous_discrepancy_report_sha256": report_ancestry.get(
                "previous_report_sha256"
            ),
            "prior_diagnosis_types": list(
                report_ancestry.get("prior_diagnosis_types", [])
            ),
            "current_diagnosis_types": list(
                report_ancestry.get("current_diagnosis_types", [])
            ),
        },
        "planner_boundary": {
            "current_planner_frontier_modified": False,
            "current_selected_action_modified": False,
            "executable_candidate_created": False,
            "candidate_availability_verified": False,
            "candidate_registry_binding_created": False,
            "fresh_planner_candidate_matching_required": True,
            "action_authorization_granted": False,
            "automatic_execution_authorized": False,
            "scientific_status_changed": False,
        },
    }
    result["handoff_sha256"] = _canonical_sha256(result)
    return result


def validate_discrepancy_planning_handoff(
    handoff: Mapping[str, Any],
    *,
    discrepancy_report: Mapping[str, Any],
    evaluated_graph: Mapping[str, Any],
    hypothesis_portfolio: Mapping[str, Any] | None = None,
    previous_discrepancy_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Rebuild and compare a handoff; any proposal/report drift fails closed."""
    value = dict(_mapping(handoff, "planning_handoff"))
    embedded = _text(value.pop("handoff_sha256", None), "planning_handoff.handoff_sha256")
    if len(embedded) != 64 or any(char not in "0123456789abcdef" for char in embedded):
        raise DiscrepancyPlanningHandoffError(
            "planning_handoff.handoff_sha256 must be lowercase SHA-256"
        )
    actual = _canonical_sha256(value)
    if actual != embedded:
        raise DiscrepancyPlanningHandoffError(
            "planning handoff canonical SHA-256 does not match its content"
        )
    rebuilt = build_discrepancy_planning_handoff(
        discrepancy_report,
        evaluated_graph=evaluated_graph,
        hypothesis_portfolio=hypothesis_portfolio,
        previous_discrepancy_report=previous_discrepancy_report,
    )
    if rebuilt != handoff:
        raise DiscrepancyPlanningHandoffError(
            "planning handoff differs from current validated discrepancy context"
        )
    return {
        "handoff_sha256": embedded,
        "source_discrepancy_report_sha256": rebuilt["source_discrepancy_report_sha256"],
        "research_objective_count": len(rebuilt["research_objectives"]),
        "fresh_planner_candidate_matching_required": True,
        "current_planner_frontier_modified": False,
        "current_selected_action_modified": False,
        "action_authorization_granted": False,
        "scientific_status_changed": False,
    }


__all__ = [
    "DISCREPANCY_PLANNING_HANDOFF_POLICY_VERSION",
    "DISCREPANCY_PLANNING_HANDOFF_SCHEMA_VERSION",
    "DiscrepancyPlanningHandoffError",
    "build_discrepancy_planning_handoff",
    "validate_discrepancy_planning_handoff",
]
