"""Public recursive planning composition over validated discrepancy evidence.

This facade reconstructs discrepancy-to-planning semantics, deterministic planner state,
predecessor planning ancestry, candidate/objective/source-report bindings, and immutable
recursive resource limits.  It grants no execution or scientific authority.  The existing
private structural checkpoint builder is used only as an implementation detail behind this
public validation boundary; callers and acceptance drivers never import it directly.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .action_registry import describe_action, load_action_registry
from .autonomous_inquiry_plan_verifier import validate_autonomous_inquiry_plan
from .heat_conduction_action import ACTION_TYPE as HEAT_ACTION_TYPE
from .heat_conduction_action import ACTION_VERSION as HEAT_ACTION_VERSION
from .heat_execution_verifier import verify_heat_execution_handoff
from .kernel import ResearchLoopError
from .planning_adapter import plan_research_next_action
from .public_recursive_discrepancy import validate_public_recursive_discrepancy_report
from .recursive_research_cycle_controller import _build_recursive_research_cycle_checkpoint
from .recursive_resource_budget import apply_recursive_resource_budget, normalize_recursive_limits

PUBLIC_RECURSIVE_HANDOFF_SCHEMA_VERSION = "1.0"
PUBLIC_RECURSIVE_HANDOFF_POLICY_VERSION = "1.0"
PUBLIC_RECURSIVE_PLANNING_SCHEMA_VERSION = "1.0"
PUBLIC_RECURSIVE_PLANNING_POLICY_VERSION = "1.0"
PUBLIC_RECURSIVE_PLANNING_CONTEXT_SCHEMA_VERSION = "1.0"
PUBLIC_RECURSIVE_PLANNING_CONTEXT_POLICY_VERSION = "1.0"
CANDIDATE_MATCH_SCHEMA_VERSION = "1.0"
CANDIDATE_MATCH_POLICY_VERSION = "1.0"
_HEAT_ADAPTER = "reference-heat-conduction"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_PRIORITIES = {"highest", "high", "medium", "low"}
_ALLOWED_EXECUTION_MODES = {"plan_only", "explicit_authorization_required"}


class PublicRecursivePlanningError(ResearchLoopError):
    """Raised when public recursive planning provenance cannot be reconstructed."""


def _canonical_sha256(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PublicRecursivePlanningError(
            "public recursive planning state must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PublicRecursivePlanningError(f"{field} must be an object")
    return value


def _optional_mapping(value: object, field: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    return _mapping(value, field)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise PublicRecursivePlanningError(f"{field} must be a sequence")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise PublicRecursivePlanningError(f"{field} must be non-empty trimmed text")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if _SHA256.fullmatch(text) is None:
        raise PublicRecursivePlanningError(f"{field} must be lowercase SHA-256")
    return text


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PublicRecursivePlanningError(f"{field} must be integer >= 1")
    return value


def _json_file(path: str | Path, *, field: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        resolved = Path(path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise PublicRecursivePlanningError(f"{field} does not resolve") from exc
    raw = resolved.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicRecursivePlanningError(f"{field} must be UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PublicRecursivePlanningError(f"{field} root must be object")
    return value, {
        "path": str(resolved),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _validate_report(
    report: Mapping[str, Any],
    *,
    evaluated_graph: Mapping[str, Any],
    previous_discrepancy_report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    try:
        return validate_public_recursive_discrepancy_report(
            report,
            evaluated_graph=evaluated_graph,
            previous_report=previous_discrepancy_report,
        )
    except ResearchLoopError as exc:
        raise PublicRecursivePlanningError(
            "source discrepancy failed public physics/provenance reconstruction"
        ) from exc


def _objective(raw: object, *, rank: int) -> dict[str, Any]:
    proposal = _mapping(raw, f"ranked_next_actions[{rank - 1}]")
    if _positive_int(proposal.get("rank"), f"proposal[{rank}].rank") != rank:
        raise PublicRecursivePlanningError("discrepancy proposal ranks must be contiguous")
    if proposal.get("availability_asserted") is not False:
        raise PublicRecursivePlanningError("discrepancy proposal cannot assert availability")
    if proposal.get("automatic_execution_authorized") is not False:
        raise PublicRecursivePlanningError("discrepancy proposal cannot authorize execution")
    if proposal.get("information_gain_is_calibrated_probability") is not False:
        raise PublicRecursivePlanningError("discrepancy proposal cannot invent calibrated probability")
    execution_mode = _text(proposal.get("execution_mode"), "proposal.execution_mode")
    if execution_mode not in _ALLOWED_EXECUTION_MODES:
        raise PublicRecursivePlanningError("unsupported discrepancy execution mode")
    priority = _text(proposal.get("information_gain_priority"), "proposal.information_gain_priority")
    if priority not in _ALLOWED_PRIORITIES:
        raise PublicRecursivePlanningError("unsupported discrepancy information priority")
    proposal_id = _text(proposal.get("proposal_id"), "proposal.proposal_id")
    action_class = _text(proposal.get("action_class"), "proposal.action_class")
    return {
        "objective_id": f"planning-objective:{proposal_id}",
        "source_proposal_id": proposal_id,
        "source_rank": rank,
        "research_action_class": action_class,
        "source_research_action_class": action_class,
        "description": _text(proposal.get("description"), "proposal.description"),
        "rationale": _text(proposal.get("rationale"), "proposal.rationale"),
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


def build_public_recursive_discrepancy_planning_handoff(
    discrepancy_report: Mapping[str, Any],
    *,
    evaluated_graph: Mapping[str, Any],
    previous_discrepancy_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project validated diagnostic semantics into fresh-planner objectives only."""
    verified = _validate_report(
        discrepancy_report,
        evaluated_graph=evaluated_graph,
        previous_discrepancy_report=previous_discrepancy_report,
    )
    report = _mapping(discrepancy_report, "discrepancy_report")
    target = _mapping(report.get("target"), "discrepancy_report.target")
    objectives = [
        _objective(item, rank=index)
        for index, item in enumerate(
            _sequence(report.get("ranked_next_actions", []), "ranked_next_actions"),
            start=1,
        )
    ]
    gates = _mapping(report.get("gates"), "discrepancy_report.gates")
    passed: list[str] = []
    failed: list[str] = []
    for name, raw in gates.items():
        gate = _mapping(raw, f"gates.{name}")
        if gate.get("passed") is True:
            passed.append(str(name))
        elif gate.get("passed") is False:
            failed.append(str(name))
        else:
            raise PublicRecursivePlanningError(f"discrepancy gate {name} lacks boolean state")
    diagnosis_types = {
        str(item) for item in verified.get("diagnosis_types", []) if isinstance(item, str)
    }
    translated: list[str] = []
    for item in objectives:
        if item["research_action_class"] != "numerical_validation":
            item.pop("source_research_action_class", None)
            continue
        if "numerical_invalidity" not in diagnosis_types or "numerical_validity" not in failed:
            raise PublicRecursivePlanningError(
                "numerical-validation semantic bridge lacks the exact numerical-invalidity gate"
            )
        item["research_action_class"] = "simulation"
        item["semantic_action_class_translation"] = {
            "schema_version": "1.0",
            "policy_version": "1.0",
            "translation_id": "numerical-validation-via-audited-simulation-v1",
            "source_diagnostic_action_class": "numerical_validation",
            "planner_action_class": "simulation",
            "required_diagnosis": "numerical_invalidity",
            "required_failed_gate": "numerical_validity",
            "diagnostic_semantics_preserved": True,
            "candidate_availability_asserted": False,
            "registry_binding_created": False,
            "action_authorization_granted": False,
            "automatic_execution_authorized": False,
            "scientific_status_changed": False,
        }
        translated.append(str(item["objective_id"]))
    stop = _mapping(report.get("stop_recommendation"), "stop_recommendation")
    ancestry = _mapping(report.get("ancestry"), "discrepancy_report.ancestry")
    result: dict[str, Any] = {
        "schema_version": PUBLIC_RECURSIVE_HANDOFF_SCHEMA_VERSION,
        "policy_version": PUBLIC_RECURSIVE_HANDOFF_POLICY_VERSION,
        "handoff_id": (
            f"public-recursive:{target.get('graph_id')}:{target.get('node_id')}:"
            f"{str(verified['report_sha256'])[:12]}"
        ),
        "source_discrepancy_report_sha256": verified["report_sha256"],
        "source_iteration_index": verified.get("iteration_index"),
        "target": {
            "graph_id": _text(target.get("graph_id"), "target.graph_id"),
            "node_id": _text(target.get("node_id"), "target.node_id"),
            "node_type": _text(target.get("node_type"), "target.node_type"),
            "statement": _text(target.get("statement"), "target.statement"),
        },
        "diagnosis_context": {
            "diagnosis_types": sorted(diagnosis_types),
            "passed_gates": sorted(passed),
            "failed_gates": sorted(failed),
            "stop_recommendation": _text(stop.get("recommendation"), "stop_recommendation.recommendation"),
            "stop_rationale": _text(stop.get("rationale"), "stop_recommendation.rationale"),
            "hypothesis_portfolio_directive": None,
        },
        "research_objectives": objectives,
        "planning_handoff_state": (
            "fresh_planner_candidate_generation_required"
            if objectives
            else "fresh_planner_review_required_no_proposal_available"
        ),
        "next_planning_cycle_required": bool(objectives or failed or diagnosis_types),
        "source_ancestry": {
            "previous_discrepancy_report_sha256": ancestry.get("previous_report_sha256"),
            "prior_diagnosis_types": list(ancestry.get("prior_diagnosis_types", [])),
            "current_diagnosis_types": list(ancestry.get("current_diagnosis_types", [])),
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
    if translated:
        result["planner_semantic_bridge"] = {
            "schema_version": "1.0",
            "policy_version": "1.0",
            "translated_objective_ids": translated,
            "translation_count": len(translated),
            "candidate_availability_asserted": False,
            "registry_binding_created": False,
            "action_authorization_granted": False,
            "automatic_execution_authorized": False,
            "scientific_status_changed": False,
        }
    result["handoff_sha256"] = _canonical_sha256(result)
    return result


def validate_public_recursive_discrepancy_planning_handoff(
    handoff: Mapping[str, Any],
    *,
    discrepancy_report: Mapping[str, Any],
    evaluated_graph: Mapping[str, Any],
    previous_discrepancy_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    value = dict(_mapping(handoff, "planning_handoff"))
    embedded = _sha(value.pop("handoff_sha256", None), "planning_handoff.handoff_sha256")
    if _canonical_sha256(value) != embedded:
        raise PublicRecursivePlanningError("planning handoff SHA-256 does not match canonical content")
    rebuilt = build_public_recursive_discrepancy_planning_handoff(
        discrepancy_report,
        evaluated_graph=evaluated_graph,
        previous_discrepancy_report=previous_discrepancy_report,
    )
    if rebuilt != handoff:
        raise PublicRecursivePlanningError("planning handoff differs from deterministic reconstruction")
    verification = _validate_report(
        discrepancy_report,
        evaluated_graph=evaluated_graph,
        previous_discrepancy_report=previous_discrepancy_report,
    )
    return {
        "handoff_sha256": embedded,
        "source_discrepancy_report_sha256": verification["report_sha256"],
        "research_objective_count": len(rebuilt["research_objectives"]),
        "fresh_planner_candidate_matching_required": True,
        "source_discrepancy_hardening_verified": True,
        "source_discrepancy_physics_hardening_verified": True,
        "semantic_action_class_translation_count": int(
            rebuilt.get("planner_semantic_bridge", {}).get("translation_count", 0)
        ),
        "authorization_granted": False,
        "scientific_status_changed": False,
    }


def _autonomy_policy() -> dict[str, str]:
    return {
        "goal_generation": "bounded_autonomous",
        "reasoning_proposals": "schema_validated",
        "typed_computational_actions": "explicit_request",
        "network_evidence_search": "explicit_authorization",
        "physical_experiment_execution": "external_only",
    }


def build_heat_recursive_planner_program_state(
    *,
    planning_handoff: Mapping[str, Any],
    discrepancy_report: Mapping[str, Any],
    evaluated_graph: Mapping[str, Any],
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
    previous_discrepancy_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose the live heat registry/request as the only cycle candidate."""
    check = validate_public_recursive_discrepancy_planning_handoff(
        planning_handoff,
        discrepancy_report=discrepancy_report,
        evaluated_graph=evaluated_graph,
        previous_discrepancy_report=previous_discrepancy_report,
    )
    objectives = [
        dict(_mapping(item, "research_objective"))
        for item in _sequence(planning_handoff.get("research_objectives", []), "research_objectives")
    ]
    matches = [item for item in objectives if item.get("research_action_class") == "simulation"]
    if len(matches) != 1:
        raise PublicRecursivePlanningError("heat planner requires exactly one simulation objective")
    try:
        execution_pin = verify_heat_execution_handoff(
            repository_root=repository_root,
            research_run=research_run,
            action_registry_path=action_registry_path,
            request_path=request_path,
        )
        live_plan = plan_research_next_action(
            _HEAT_ADAPTER,
            repository_root=repository_root,
            research_run=research_run,
            action_registry_path=action_registry_path,
        )
    except ResearchLoopError as exc:
        raise PublicRecursivePlanningError(
            "live heat planning/authorization pins are unavailable"
        ) from exc
    if live_plan.get("selection_status") != "ready_to_execute":
        raise PublicRecursivePlanningError("heat planning adapter did not expose an executable candidate")
    selected = _mapping(live_plan.get("selected_action"), "live_heat_plan.selected_action")
    request, request_record = _json_file(request_path, field="heat_execution_request")
    if (
        request.get("action_type") != HEAT_ACTION_TYPE
        or request.get("action_version") != HEAT_ACTION_VERSION
        or selected.get("action_type") != HEAT_ACTION_TYPE
        or selected.get("action_version") != HEAT_ACTION_VERSION
    ):
        raise PublicRecursivePlanningError("heat request and live selected action type/version differ")
    registry = load_action_registry(action_registry_path, repository_root=repository_root)
    contract = describe_action(registry, HEAT_ACTION_TYPE)
    if contract.get("category") != "simulation":
        raise PublicRecursivePlanningError("live heat registry category is not simulation")
    if selected.get("execution_registry_sha256") != registry.get("registry_sha256"):
        raise PublicRecursivePlanningError("live heat selected action registry binding drifted")
    action_id = _text(request.get("action_id"), "heat_execution_request.action_id")
    action = {
        "action_id": action_id,
        "action_class": "simulation",
        "description": "Run the exact checksum-bound reference heat request selected by the live repository planning chain.",
        "rationale": str(matches[0].get("rationale") or "Resolve numerical validity."),
        "required_evidence": [],
        "expected_outcome": "A pinned deterministic heat-solver result for subsequent independent verification.",
        "execution_mode": "typed_local_action",
        "expected_information_score": 0.90,
        "hypothesis_discrimination_score": 0.90,
        "feasibility_score": 0.95,
        "cost_units": float(selected.get("cost_units", 1.0)),
        "risk_penalty": 0.0,
    }
    return {
        "mission": {"autonomy_policy": _autonomy_policy()},
        "generated_goals": [{
            "goal_id": "public-recursive:resolve-numerical-validity",
            "workstream_id": "reference-heat-conduction",
            "research_question": "Can the audited reference heat solver pass its declared numerical benchmark?",
            "goal_statement": "Resolve the verified numerical-validity blocker without claiming empirical validity.",
            "status": "active",
            "priority": 100,
            "evidence_requirements": [
                "Pinned deterministic solver result",
                "Immutable-ledger execution binding",
                "No empirical scientific promotion",
            ],
            "claim_boundary": {"empirical_validation_claimed": False},
            "action_frontier": [action],
        }],
        "public_recursive_planner_binding": {
            "handoff_sha256": check["handoff_sha256"],
            "source_discrepancy_report_sha256": check["source_discrepancy_report_sha256"],
            "execution_request": request_record,
            "execution_request_action_id": action_id,
            "execution_handoff": dict(execution_pin),
            "planning_adapter_selection_status": live_plan.get("selection_status"),
            "planning_adapter_selected_action": dict(selected),
            "registry_sha256": registry["registry_sha256"],
            "candidate_created_from_live_planning_adapter_and_typed_request": True,
            "caller_injected_candidate": False,
            "authorization_granted": False,
            "execution_performed": False,
        },
    }


def build_external_evidence_waiting_program_state(
    *,
    planning_handoff: Mapping[str, Any],
    discrepancy_report: Mapping[str, Any],
    evaluated_graph: Mapping[str, Any],
    previous_discrepancy_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Represent a real evidence-acquisition need without inventing a candidate."""
    check = validate_public_recursive_discrepancy_planning_handoff(
        planning_handoff,
        discrepancy_report=discrepancy_report,
        evaluated_graph=evaluated_graph,
        previous_discrepancy_report=previous_discrepancy_report,
    )
    objectives = [
        dict(_mapping(item, "research_objective"))
        for item in _sequence(planning_handoff.get("research_objectives", []), "research_objectives")
    ]
    external = [item for item in objectives if item.get("research_action_class") == "external_evidence_search"]
    if len(external) != 1:
        raise PublicRecursivePlanningError("evidence waiting requires exactly one external-evidence objective")
    return {
        "mission": {"autonomy_policy": _autonomy_policy()},
        "generated_goals": [{
            "goal_id": "public-recursive:acquire-real-empirical-evidence",
            "workstream_id": "external-empirical-evidence",
            "research_question": "Is provenance-bound empirical evidence available for the target comparison?",
            "goal_statement": "Acquire real independent empirical evidence without synthesizing an observation.",
            "status": "active",
            "priority": 100,
            "evidence_requirements": [
                "A real empirical artifact",
                "Provenance and protocol identity",
                "Explicit authorization before network/external acquisition",
            ],
            "claim_boundary": {"synthetic_measurement_allowed": False},
            "action_frontier": [],
        }],
        "public_recursive_planner_binding": {
            "handoff_sha256": check["handoff_sha256"],
            "source_discrepancy_report_sha256": check["source_discrepancy_report_sha256"],
            "blocking_objective_id": external[0]["objective_id"],
            "blocking_action_class": "external_evidence_search",
            "repository_authorized_external_candidate_available": False,
            "synthetic_candidate_created": False,
            "authorization_granted": False,
            "network_access_performed": False,
        },
    }


def build_public_candidate_match_record(
    *,
    planning_handoff: Mapping[str, Any],
    fresh_plan: Mapping[str, Any],
) -> dict[str, Any]:
    selected = _mapping(fresh_plan.get("selected_next_action"), "selected_next_action")
    selected_class = _text(selected.get("action_class"), "selected_next_action.action_class")
    objectives = [
        dict(_mapping(item, "research_objective"))
        for item in _sequence(planning_handoff.get("research_objectives", []), "research_objectives")
    ]
    matches = [item for item in objectives if item.get("research_action_class") == selected_class]
    if len(matches) != 1:
        raise PublicRecursivePlanningError("fresh selected action does not uniquely match a discrepancy objective")
    objective = matches[0]
    return {
        "schema_version": CANDIDATE_MATCH_SCHEMA_VERSION,
        "policy_version": CANDIDATE_MATCH_POLICY_VERSION,
        "handoff_sha256": _sha(planning_handoff.get("handoff_sha256"), "handoff_sha256"),
        "fresh_plan_sha256": _sha(fresh_plan.get("plan_sha256"), "fresh_plan.plan_sha256"),
        "source_discrepancy_report_sha256": _sha(
            planning_handoff.get("source_discrepancy_report_sha256"),
            "source_discrepancy_report_sha256",
        ),
        "objective_id": objective["objective_id"],
        "source_proposal_id": objective["source_proposal_id"],
        "source_rank": objective["source_rank"],
        "candidate_action_id": _text(selected.get("action_id"), "selected_next_action.action_id"),
        "candidate_action_class": selected_class,
        "candidate_execution_mode": _text(selected.get("execution_mode"), "selected_next_action.execution_mode"),
        "match_rationale": "The reconstructed planner selected the typed action class required by the validated discrepancy objective.",
        "selected_candidate_canonical_sha256": _canonical_sha256(selected),
        "matched_objective_canonical_sha256": _canonical_sha256(objective),
        "availability_promoted": False,
        "authorization_granted": False,
    }


def _verify_candidate_match(
    candidate_match: Mapping[str, Any] | None,
    *,
    planning_handoff: Mapping[str, Any],
    fresh_plan: Mapping[str, Any],
) -> None:
    if candidate_match is None:
        if fresh_plan.get("selected_next_action") is not None:
            raise PublicRecursivePlanningError("selected planner candidate requires an explicit candidate match")
        return
    expected = build_public_candidate_match_record(
        planning_handoff=planning_handoff,
        fresh_plan=fresh_plan,
    )
    if dict(candidate_match) != expected:
        raise PublicRecursivePlanningError("candidate match differs from exact source-report/objective/candidate semantics")


def _persistent_state(
    *,
    planning_handoff: Mapping[str, Any],
    fresh_plan: Mapping[str, Any],
) -> dict[str, Any]:
    diagnosis = _mapping(planning_handoff.get("diagnosis_context"), "diagnosis_context")
    objectives = [dict(_mapping(item, "research_objective")) for item in _sequence(planning_handoff.get("research_objectives", []), "research_objectives")]
    gaps = [dict(_mapping(item, "evidence_gap")) for item in _sequence(fresh_plan.get("evidence_gaps", []), "fresh_plan.evidence_gaps")]
    external = sorted(
        str(item.get("objective_id"))
        for item in objectives
        if item.get("research_action_class") == "external_evidence_search"
        or item.get("source_execution_mode") == "explicit_authorization_required"
    )
    stop = _mapping(fresh_plan.get("stop_decision"), "fresh_plan.stop_decision")
    return {
        "source_discrepancy_report_sha256": planning_handoff["source_discrepancy_report_sha256"],
        "fresh_plan_sha256": fresh_plan["plan_sha256"],
        "unresolved_evidence_gaps": gaps,
        "blockers": {
            "failed_discrepancy_gates": sorted(diagnosis.get("failed_gates", [])),
            "diagnosis_types": sorted(diagnosis.get("diagnosis_types", [])),
            "external_or_authorization_required_objective_ids": external,
            "planner_stop": (
                {"reason": stop.get("reason"), "next_mode": stop.get("next_mode")}
                if stop.get("stop") is True else None
            ),
        },
        "state_semantics": "verified_planning_context_snapshot_not_scientific_truth",
    }


def build_public_recursive_planning_checkpoint(
    *,
    planning_handoff: Mapping[str, Any],
    source_discrepancy_report: Mapping[str, Any],
    source_evaluated_graph: Mapping[str, Any],
    fresh_plan: Mapping[str, Any],
    planner_program_state: Mapping[str, Any],
    previous_discrepancy_report: Mapping[str, Any] | None = None,
    candidate_match: Mapping[str, Any] | None = None,
    budget_units: float = 8.0,
    minimum_utility: float = 0.01,
    previous_validated_planning_context: Mapping[str, Any] | None = None,
    recursive_limits: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish one checkpoint only from reconstructable public source inputs."""
    handoff_check = validate_public_recursive_discrepancy_planning_handoff(
        planning_handoff,
        discrepancy_report=source_discrepancy_report,
        evaluated_graph=source_evaluated_graph,
        previous_discrepancy_report=previous_discrepancy_report,
    )
    try:
        planner_check = validate_autonomous_inquiry_plan(
            fresh_plan,
            program_state=planner_program_state,
            budget_units=budget_units,
            minimum_utility=minimum_utility,
        )
    except ResearchLoopError as exc:
        raise PublicRecursivePlanningError("fresh autonomous plan failed deterministic reconstruction") from exc
    binding = _mapping(planner_program_state.get("public_recursive_planner_binding"), "public_recursive_planner_binding")
    if (
        binding.get("handoff_sha256") != handoff_check["handoff_sha256"]
        or binding.get("source_discrepancy_report_sha256") != handoff_check["source_discrepancy_report_sha256"]
    ):
        raise PublicRecursivePlanningError("planner program is not bound to the exact handoff/source report")
    _verify_candidate_match(candidate_match, planning_handoff=planning_handoff, fresh_plan=fresh_plan)

    previous_checkpoint: dict[str, Any] | None = None
    previous_budget: dict[str, Any] | None = None
    previous_context_sha: str | None = None
    if previous_validated_planning_context is not None:
        previous_verified = validate_public_recursive_planning_context(previous_validated_planning_context)
        previous_checkpoint = dict(previous_verified["recursive_checkpoint"])
        previous_budget = dict(previous_verified["recursive_resource_budget"])
        previous_context_sha = str(previous_verified["context_sha256"])
    effective_limits: Mapping[str, Any] | None = recursive_limits
    if effective_limits is None and previous_budget is not None:
        effective_limits = _mapping(previous_budget.get("limits"), "previous recursive limits")
    normalized_limits = normalize_recursive_limits(effective_limits)

    try:
        checkpoint = _build_recursive_research_cycle_checkpoint(
            planning_handoff=planning_handoff,
            fresh_plan=fresh_plan,
            candidate_match=candidate_match,
            previous_checkpoint=previous_checkpoint,
        )
    except ResearchLoopError as exc:
        raise PublicRecursivePlanningError(
            "recursive structural checkpoint rejected source/plan/predecessor ancestry"
        ) from exc
    checkpoint = dict(checkpoint)
    if candidate_match is not None:
        match = dict(_mapping(checkpoint.get("candidate_match"), "checkpoint.candidate_match"))
        match.update({
            "source_discrepancy_report_sha256": handoff_check["source_discrepancy_report_sha256"],
            "selected_candidate_canonical_sha256": candidate_match["selected_candidate_canonical_sha256"],
            "matched_objective_canonical_sha256": candidate_match["matched_objective_canonical_sha256"],
        })
        checkpoint["candidate_match"] = match
    checkpoint["persistent_research_state"] = _persistent_state(
        planning_handoff=planning_handoff,
        fresh_plan=fresh_plan,
    )
    checkpoint.pop("checkpoint_sha256", None)
    checkpoint["checkpoint_sha256"] = _canonical_sha256(checkpoint)
    checkpoint, resource_budget = apply_recursive_resource_budget(
        checkpoint=checkpoint,
        fresh_plan=fresh_plan,
        previous_checkpoint=previous_checkpoint,
        previous_budget=previous_budget,
        recursive_limits=normalized_limits,
    )
    if (
        checkpoint["ancestry"]["planning_handoff_sha256"] != handoff_check["handoff_sha256"]
        or checkpoint["ancestry"]["fresh_plan_sha256"] != planner_check["plan_sha256"]
    ):
        raise PublicRecursivePlanningError("verified handoff/plan identity diverged before checkpoint publication")
    result: dict[str, Any] = {
        "schema_version": PUBLIC_RECURSIVE_PLANNING_SCHEMA_VERSION,
        "policy_version": PUBLIC_RECURSIVE_PLANNING_POLICY_VERSION,
        "handoff_verification": handoff_check,
        "planner_verification": planner_check,
        "recursive_checkpoint": checkpoint,
        "recursive_resource_budget": resource_budget,
        "predecessor_validation": (
            None if previous_checkpoint is None else {
                "planning_context_sha256": previous_context_sha,
                "recursive_checkpoint_sha256": previous_checkpoint["checkpoint_sha256"],
                "recursive_resource_budget_sha256": previous_budget["budget_sha256"],
                "deterministically_reconstructed": True,
            }
        ),
        "autonomy_boundary": {
            "source_discrepancy_hardening_verified": True,
            "planner_reconstruction_verified": True,
            "predecessor_reconstruction_verified": previous_checkpoint is not None,
            "recursive_resource_limits_enforced": True,
            "candidate_match_source_report_directly_bound": candidate_match is not None,
            "candidate_and_objective_full_semantics_hash_bound": candidate_match is not None,
            "raw_predecessor_checkpoint_trusted": False,
            "caller_authored_execution_record_accepted": False,
            "authorization_granted": False,
            "request_compiled": False,
            "execution_performed": False,
            "scientific_status_changed": False,
        },
    }
    result["validated_checkpoint_sha256"] = _canonical_sha256(result)
    return result


def validate_public_recursive_planning_checkpoint(
    artifact: Mapping[str, Any],
    *,
    planning_handoff: Mapping[str, Any],
    source_discrepancy_report: Mapping[str, Any],
    source_evaluated_graph: Mapping[str, Any],
    fresh_plan: Mapping[str, Any],
    planner_program_state: Mapping[str, Any],
    previous_discrepancy_report: Mapping[str, Any] | None = None,
    candidate_match: Mapping[str, Any] | None = None,
    budget_units: float = 8.0,
    minimum_utility: float = 0.01,
    previous_validated_planning_context: Mapping[str, Any] | None = None,
    recursive_limits: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    supplied = dict(_mapping(artifact, "validated_planning_artifact"))
    embedded = _sha(supplied.get("validated_checkpoint_sha256"), "validated_checkpoint_sha256")
    unsigned = dict(supplied)
    unsigned.pop("validated_checkpoint_sha256", None)
    if _canonical_sha256(unsigned) != embedded:
        raise PublicRecursivePlanningError("validated planning SHA does not match canonical content")
    rebuilt = build_public_recursive_planning_checkpoint(
        planning_handoff=planning_handoff,
        source_discrepancy_report=source_discrepancy_report,
        source_evaluated_graph=source_evaluated_graph,
        fresh_plan=fresh_plan,
        planner_program_state=planner_program_state,
        previous_discrepancy_report=previous_discrepancy_report,
        candidate_match=candidate_match,
        budget_units=budget_units,
        minimum_utility=minimum_utility,
        previous_validated_planning_context=previous_validated_planning_context,
        recursive_limits=recursive_limits,
    )
    if rebuilt != supplied:
        raise PublicRecursivePlanningError("validated planning artifact differs from deterministic reconstruction")
    return {
        "validated_checkpoint_sha256": embedded,
        "recursive_checkpoint": dict(rebuilt["recursive_checkpoint"]),
        "recursive_resource_budget": dict(rebuilt["recursive_resource_budget"]),
        "handoff_verification": dict(rebuilt["handoff_verification"]),
        "planner_verification": dict(rebuilt["planner_verification"]),
        "predecessor_validation": rebuilt.get("predecessor_validation"),
        "authorization_granted": False,
        "execution_performed": False,
        "scientific_status_changed": False,
    }


def build_public_recursive_planning_context(
    *,
    validated_planning_artifact: Mapping[str, Any],
    planning_handoff: Mapping[str, Any],
    source_discrepancy_report: Mapping[str, Any],
    source_evaluated_graph: Mapping[str, Any],
    fresh_plan: Mapping[str, Any],
    planner_program_state: Mapping[str, Any],
    previous_discrepancy_report: Mapping[str, Any] | None = None,
    candidate_match: Mapping[str, Any] | None = None,
    budget_units: float = 8.0,
    minimum_utility: float = 0.01,
    previous_validated_planning_context: Mapping[str, Any] | None = None,
    recursive_limits: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    limits = normalize_recursive_limits(recursive_limits)
    verification = validate_public_recursive_planning_checkpoint(
        validated_planning_artifact,
        planning_handoff=planning_handoff,
        source_discrepancy_report=source_discrepancy_report,
        source_evaluated_graph=source_evaluated_graph,
        fresh_plan=fresh_plan,
        planner_program_state=planner_program_state,
        previous_discrepancy_report=previous_discrepancy_report,
        candidate_match=candidate_match,
        budget_units=budget_units,
        minimum_utility=minimum_utility,
        previous_validated_planning_context=previous_validated_planning_context,
        recursive_limits=limits,
    )
    inputs = {
        "planning_handoff": copy.deepcopy(dict(planning_handoff)),
        "source_discrepancy_report": copy.deepcopy(dict(source_discrepancy_report)),
        "source_evaluated_graph": copy.deepcopy(dict(source_evaluated_graph)),
        "fresh_plan": copy.deepcopy(dict(fresh_plan)),
        "planner_program_state": copy.deepcopy(dict(planner_program_state)),
        "previous_discrepancy_report": None if previous_discrepancy_report is None else copy.deepcopy(dict(previous_discrepancy_report)),
        "candidate_match": None if candidate_match is None else copy.deepcopy(dict(candidate_match)),
        "budget_units": float(budget_units),
        "minimum_utility": float(minimum_utility),
        "previous_validated_planning_context": None if previous_validated_planning_context is None else copy.deepcopy(dict(previous_validated_planning_context)),
        "recursive_limits": dict(limits),
    }
    result: dict[str, Any] = {
        "schema_version": PUBLIC_RECURSIVE_PLANNING_CONTEXT_SCHEMA_VERSION,
        "policy_version": PUBLIC_RECURSIVE_PLANNING_CONTEXT_POLICY_VERSION,
        "validated_planning_artifact": copy.deepcopy(dict(validated_planning_artifact)),
        "validation_inputs": inputs,
        "bindings": {
            "validated_checkpoint_sha256": verification["validated_checkpoint_sha256"],
            "recursive_checkpoint_sha256": verification["recursive_checkpoint"]["checkpoint_sha256"],
            "recursive_resource_budget_sha256": verification["recursive_resource_budget"]["budget_sha256"],
            "fresh_plan_sha256": _sha(fresh_plan.get("plan_sha256"), "fresh_plan.plan_sha256"),
            "source_discrepancy_report_sha256": _sha(planning_handoff.get("source_discrepancy_report_sha256"), "source_discrepancy_report_sha256"),
        },
        "authority_boundary": {
            "raw_checkpoint_authoritative_without_reconstruction": False,
            "caller_authored_execution_record_accepted": False,
            "authorization_granted": False,
            "execution_performed": False,
            "scientific_status_changed": False,
        },
    }
    result["context_sha256"] = _canonical_sha256(result)
    return result


def validate_public_recursive_planning_context(context: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(_mapping(context, "validated_planning_context"))
    embedded = _sha(value.get("context_sha256"), "context_sha256")
    unsigned = dict(value)
    unsigned.pop("context_sha256", None)
    if _canonical_sha256(unsigned) != embedded:
        raise PublicRecursivePlanningError("planning context SHA does not match canonical content")
    if value.get("schema_version") != PUBLIC_RECURSIVE_PLANNING_CONTEXT_SCHEMA_VERSION:
        raise PublicRecursivePlanningError("planning context schema_version drifted")
    inputs = _mapping(value.get("validation_inputs"), "validation_inputs")
    artifact = _mapping(value.get("validated_planning_artifact"), "validated_planning_artifact")
    previous_context = _optional_mapping(
        inputs.get("previous_validated_planning_context"),
        "previous_validated_planning_context",
    )
    rebuilt = build_public_recursive_planning_checkpoint(
        planning_handoff=_mapping(inputs.get("planning_handoff"), "validation_inputs.planning_handoff"),
        source_discrepancy_report=_mapping(inputs.get("source_discrepancy_report"), "validation_inputs.source_discrepancy_report"),
        source_evaluated_graph=_mapping(inputs.get("source_evaluated_graph"), "validation_inputs.source_evaluated_graph"),
        fresh_plan=_mapping(inputs.get("fresh_plan"), "validation_inputs.fresh_plan"),
        planner_program_state=_mapping(inputs.get("planner_program_state"), "validation_inputs.planner_program_state"),
        previous_discrepancy_report=_optional_mapping(inputs.get("previous_discrepancy_report"), "previous_discrepancy_report"),
        candidate_match=_optional_mapping(inputs.get("candidate_match"), "candidate_match"),
        budget_units=float(inputs.get("budget_units", 8.0)),
        minimum_utility=float(inputs.get("minimum_utility", 0.01)),
        previous_validated_planning_context=previous_context,
        recursive_limits=_mapping(inputs.get("recursive_limits"), "recursive_limits"),
    )
    if rebuilt != artifact:
        raise PublicRecursivePlanningError("planning context does not reconstruct its validated artifact")
    checkpoint = _mapping(artifact.get("recursive_checkpoint"), "recursive_checkpoint")
    budget = _mapping(artifact.get("recursive_resource_budget"), "recursive_resource_budget")
    return {
        "context_sha256": embedded,
        "validated_planning_artifact": dict(artifact),
        "validation_inputs": dict(inputs),
        "recursive_checkpoint": dict(checkpoint),
        "recursive_resource_budget": dict(budget),
        "recursive_limits": dict(_mapping(budget.get("limits"), "recursive_resource_budget.limits")),
        "deterministically_reconstructed": True,
        "authorization_granted": False,
        "execution_performed": False,
    }


build_discrepancy_planning_handoff = build_public_recursive_discrepancy_planning_handoff
validate_discrepancy_planning_handoff = validate_public_recursive_discrepancy_planning_handoff
build_validated_recursive_planning_checkpoint = build_public_recursive_planning_checkpoint
validate_validated_recursive_planning_checkpoint = validate_public_recursive_planning_checkpoint


__all__ = [
    "PublicRecursivePlanningError",
    "build_discrepancy_planning_handoff",
    "build_external_evidence_waiting_program_state",
    "build_heat_recursive_planner_program_state",
    "build_public_candidate_match_record",
    "build_public_recursive_discrepancy_planning_handoff",
    "build_public_recursive_planning_checkpoint",
    "build_public_recursive_planning_context",
    "build_validated_recursive_planning_checkpoint",
    "validate_discrepancy_planning_handoff",
    "validate_public_recursive_discrepancy_planning_handoff",
    "validate_public_recursive_planning_checkpoint",
    "validate_public_recursive_planning_context",
    "validate_validated_recursive_planning_checkpoint",
]
