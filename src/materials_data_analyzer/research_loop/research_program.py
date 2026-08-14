"""Mission-level control plane for provenance-aware autonomous materials research.

This layer sits above the immutable research ledger and domain planning adapters. It
may generate bounded research goals from verified blockers and evidence gaps, but it
never invents scientific evidence, silently upgrades claims, executes network access,
or performs physical experiments. Domain-specific scientific hypotheses may be
proposed by an external reasoning provider only through a strict, evidence-bound
proposal contract.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .kernel import ResearchLoopError
from .planning_adapter import available_planning_adapters
from .planning_state import build_research_planning_state

MISSION_SCHEMA_VERSION = "1.0"
PROGRAM_SCHEMA_VERSION = "1.0"
REASONING_PROPOSAL_SCHEMA_VERSION = "1.0"
PROGRAM_POLICY_VERSION = "1.0"

_ALLOWED_GOAL_GENERATION = {"bounded_autonomous", "manual_only"}
_ALLOWED_REASONING_PROPOSALS = {"schema_validated", "disabled"}
_ALLOWED_TYPED_ACTION_AUTONOMY = {"explicit_request", "disabled"}
_ALLOWED_NETWORK_AUTONOMY = {"explicit_authorization", "disabled"}
_ALLOWED_PHYSICAL_EXECUTION = {"external_only", "disabled"}
_ALLOWED_ACTION_CLASSES = {
    "existing_data_reanalysis",
    "external_evidence_search",
    "computational_experiment",
    "sensitivity_analysis",
    "simulation",
    "physical_experiment_design",
    "replication",
    "manual_review",
}
_ALLOWED_PROPOSAL_EXECUTION_MODES = {
    "plan_only",
    "typed_local_action",
    "explicit_authorization_required",
}


class ResearchProgramError(ResearchLoopError):
    """Raised when a mission or autonomous research-program contract is invalid."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ResearchProgramError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise ResearchProgramError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ResearchProgramError(f"JSON root must be an object: {path}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchProgramError(f"{field} must be a non-empty string")
    return value.strip()


def _string_list(value: object, field: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise ResearchProgramError(f"{field} must be a list")
    if not allow_empty and not value:
        raise ResearchProgramError(f"{field} must not be empty")
    result: list[str] = []
    for item in value:
        text = _nonempty_text(item, f"{field} item")
        if text in result:
            raise ResearchProgramError(f"{field} must not contain duplicates")
        result.append(text)
    return result


def _require_exact_keys(
    value: object,
    *,
    required: set[str],
    allowed: set[str],
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ResearchProgramError(f"{field} must be an object")
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise ResearchProgramError(f"{field} is missing required keys: {', '.join(missing)}")
    if unknown:
        raise ResearchProgramError(f"{field} has unknown keys: {', '.join(unknown)}")
    return value


def _enum(value: object, allowed: set[str], field: str) -> str:
    text = _nonempty_text(value, field)
    if text not in allowed:
        raise ResearchProgramError(
            f"{field} must be one of: {', '.join(sorted(allowed))}"
        )
    return text


def validate_research_mission(value: object) -> dict[str, Any]:
    """Validate a bounded mission that permits goal generation but not invented evidence."""
    mission = _require_exact_keys(
        value,
        required={
            "schema_version",
            "mission_id",
            "mission",
            "success_criteria",
            "constraints",
            "stop_rules",
            "autonomy_policy",
            "workstreams",
        },
        allowed={
            "schema_version",
            "mission_id",
            "mission",
            "success_criteria",
            "constraints",
            "stop_rules",
            "autonomy_policy",
            "workstreams",
            "metadata",
        },
        field="research mission",
    )
    if mission["schema_version"] != MISSION_SCHEMA_VERSION:
        raise ResearchProgramError(
            f"unsupported mission schema_version: {mission['schema_version']!r}"
        )

    policy = _require_exact_keys(
        mission["autonomy_policy"],
        required={
            "goal_generation",
            "reasoning_proposals",
            "typed_computational_actions",
            "network_evidence_search",
            "physical_experiment_execution",
        },
        allowed={
            "goal_generation",
            "reasoning_proposals",
            "typed_computational_actions",
            "network_evidence_search",
            "physical_experiment_execution",
        },
        field="autonomy_policy",
    )
    normalized_policy = {
        "goal_generation": _enum(
            policy["goal_generation"], _ALLOWED_GOAL_GENERATION, "autonomy_policy.goal_generation"
        ),
        "reasoning_proposals": _enum(
            policy["reasoning_proposals"],
            _ALLOWED_REASONING_PROPOSALS,
            "autonomy_policy.reasoning_proposals",
        ),
        "typed_computational_actions": _enum(
            policy["typed_computational_actions"],
            _ALLOWED_TYPED_ACTION_AUTONOMY,
            "autonomy_policy.typed_computational_actions",
        ),
        "network_evidence_search": _enum(
            policy["network_evidence_search"],
            _ALLOWED_NETWORK_AUTONOMY,
            "autonomy_policy.network_evidence_search",
        ),
        "physical_experiment_execution": _enum(
            policy["physical_experiment_execution"],
            _ALLOWED_PHYSICAL_EXECUTION,
            "autonomy_policy.physical_experiment_execution",
        ),
    }

    raw_workstreams = mission["workstreams"]
    if not isinstance(raw_workstreams, list) or not raw_workstreams:
        raise ResearchProgramError("workstreams must be a non-empty list")
    adapter_ids = set(available_planning_adapters())
    workstream_ids: set[str] = set()
    normalized_workstreams: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_workstreams):
        item = _require_exact_keys(
            raw,
            required={"workstream_id", "adapter_id", "priority", "role", "enabled"},
            allowed={"workstream_id", "adapter_id", "priority", "role", "enabled"},
            field=f"workstreams[{index}]",
        )
        workstream_id = _nonempty_text(item["workstream_id"], f"workstreams[{index}].workstream_id")
        if workstream_id in workstream_ids:
            raise ResearchProgramError(f"duplicate workstream_id: {workstream_id}")
        workstream_ids.add(workstream_id)
        adapter_id = _nonempty_text(item["adapter_id"], f"workstreams[{index}].adapter_id")
        if adapter_id not in adapter_ids:
            raise ResearchProgramError(f"unsupported planning adapter: {adapter_id}")
        priority = item["priority"]
        if isinstance(priority, bool) or not isinstance(priority, int) or not 1 <= priority <= 100:
            raise ResearchProgramError(
                f"workstreams[{index}].priority must be an integer from 1 to 100"
            )
        enabled = item["enabled"]
        if not isinstance(enabled, bool):
            raise ResearchProgramError(f"workstreams[{index}].enabled must be boolean")
        normalized_workstreams.append(
            {
                "workstream_id": workstream_id,
                "adapter_id": adapter_id,
                "priority": priority,
                "role": _nonempty_text(item["role"], f"workstreams[{index}].role"),
                "enabled": enabled,
            }
        )

    normalized: dict[str, Any] = {
        "schema_version": MISSION_SCHEMA_VERSION,
        "mission_id": _nonempty_text(mission["mission_id"], "mission_id"),
        "mission": _nonempty_text(mission["mission"], "mission"),
        "success_criteria": _string_list(mission["success_criteria"], "success_criteria"),
        "constraints": _string_list(mission["constraints"], "constraints", allow_empty=True),
        "stop_rules": _string_list(mission["stop_rules"], "stop_rules"),
        "autonomy_policy": normalized_policy,
        "workstreams": normalized_workstreams,
    }
    if "metadata" in mission:
        if not isinstance(mission["metadata"], dict):
            raise ResearchProgramError("metadata must be an object when provided")
        normalized["metadata"] = mission["metadata"]
    return normalized


def _load_runtime_context(path: Path | None) -> tuple[dict[str, Any], dict[str, str] | None]:
    if path is None:
        return {"schema_version": "1.0", "workstreams": {}}, None
    resolved = path.expanduser().resolve(strict=True)
    raw = _load_json(resolved)
    context = _require_exact_keys(
        raw,
        required={"schema_version", "workstreams"},
        allowed={"schema_version", "workstreams"},
        field="runtime context",
    )
    if context["schema_version"] != "1.0":
        raise ResearchProgramError("unsupported runtime context schema_version")
    workstreams = context["workstreams"]
    if not isinstance(workstreams, dict):
        raise ResearchProgramError("runtime context workstreams must be an object")
    normalized: dict[str, Any] = {}
    for workstream_id, raw_item in workstreams.items():
        key = _nonempty_text(workstream_id, "runtime context workstream id")
        item = _require_exact_keys(
            raw_item,
            required=set(),
            allowed={"research_run", "action_registry_path"},
            field=f"runtime context {key}",
        )
        normalized[key] = {
            name: _nonempty_text(value, f"runtime context {key}.{name}")
            for name, value in item.items()
        }
    return {"schema_version": "1.0", "workstreams": normalized}, {
        "path": str(resolved),
        "sha256": _sha256_file(resolved),
    }


def _goal_status(stop_state: Mapping[str, Any]) -> str:
    status = stop_state.get("status")
    return {
        "continue": "active",
        "manual_review_gate": "manual_review_required",
        "operationally_blocked": "blocked",
        "terminal_for_current_scope": "scope_exhausted",
    }.get(status, "unknown")


def _program_step_for_goal(goal: Mapping[str, Any]) -> dict[str, Any]:
    status = goal.get("status")
    selected_action = goal.get("selected_action")
    requirements = goal.get("evidence_requirements")
    if status == "runtime_context_required":
        mode = "supply_runtime_context"
    elif status == "manual_review_required":
        mode = "manual_semantic_review"
    elif isinstance(selected_action, Mapping):
        mode = "delegate_typed_action"
    elif isinstance(requirements, list) and requirements:
        mode = "acquire_or_generate_evidence"
    elif status == "blocked":
        mode = "resolve_operational_blocker"
    elif status == "scope_exhausted":
        mode = "evaluate_reopen_or_spawn_new_goal"
    else:
        mode = "reassess_verified_state"
    return {
        "goal_id": goal.get("goal_id"),
        "workstream_id": goal.get("workstream_id"),
        "mode": mode,
        "selected_action": dict(selected_action) if isinstance(selected_action, Mapping) else None,
        "automatic_execution_authorized": False,
        "reason": goal.get("goal_statement"),
    }


def _goal_from_state(
    mission_id: str,
    workstream: Mapping[str, Any],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    workstream_id = str(workstream["workstream_id"])
    research_question = state.get("research_question")
    blocker = state.get("current_blocker")
    gap = state.get("evidence_gap")
    stop_state = state.get("stop_state")
    if not isinstance(blocker, Mapping) or not isinstance(gap, Mapping) or not isinstance(stop_state, Mapping):
        raise ResearchProgramError(
            f"planning state for {workstream_id} is missing blocker/gap/stop contracts"
        )
    blocker_summary = _nonempty_text(blocker.get("summary"), f"{workstream_id}.blocker.summary")
    requirements = gap.get("requirements")
    if not isinstance(requirements, list):
        raise ResearchProgramError(f"{workstream_id}.evidence_gap.requirements must be a list")
    normalized_requirements = [
        _nonempty_text(item, f"{workstream_id}.evidence requirement") for item in requirements
    ]
    question = (
        _nonempty_text(research_question, f"{workstream_id}.research_question")
        if research_question is not None
        else f"Advance the {workstream_id} workstream within the verified claim boundary."
    )
    selected_action = state.get("selected_action")
    return {
        "goal_id": f"{mission_id}:{workstream_id}:resolve-current-blocker",
        "workstream_id": workstream_id,
        "adapter_id": workstream["adapter_id"],
        "role": workstream["role"],
        "priority": workstream["priority"],
        "origin": "self_generated_from_verified_planning_state",
        "research_question": question,
        "goal_statement": f"Resolve the verified blocker without exceeding the claim boundary: {blocker_summary}",
        "status": _goal_status(stop_state),
        "blocker": dict(blocker),
        "evidence_gap_status": gap.get("status"),
        "evidence_requirements": normalized_requirements,
        "selected_action": dict(selected_action) if isinstance(selected_action, Mapping) else None,
        "action_frontier": [
            dict(item) for item in state.get("action_frontier", []) if isinstance(item, Mapping)
        ],
        "claim_boundary": dict(state.get("claim_boundary", {}))
        if isinstance(state.get("claim_boundary"), Mapping)
        else None,
        "epistemic_hypothesis": {
            "type": "readiness_hypothesis",
            "statement": (
                "The current scientific claim should not be advanced until the verified blocker "
                "or evidence gap is resolved and the domain planner is revalidated."
            ),
            "scientific_mechanism_claim": False,
        },
        "scientific_hypothesis_generation_status": "requires_evidence_bound_domain_reasoning_proposal",
        "expected_information_gain": {
            "status": "not_quantified",
            "value": None,
            "boundary": "Priority is mission policy, not an information-gain estimate.",
        },
    }


def _runtime_context_goal(
    mission_id: str,
    workstream: Mapping[str, Any],
) -> dict[str, Any]:
    workstream_id = str(workstream["workstream_id"])
    return {
        "goal_id": f"{mission_id}:{workstream_id}:supply-runtime-context",
        "workstream_id": workstream_id,
        "adapter_id": workstream["adapter_id"],
        "role": workstream["role"],
        "priority": workstream["priority"],
        "origin": "self_generated_from_missing_runtime_context",
        "research_question": f"Restore verified runtime context for {workstream_id} before scientific planning.",
        "goal_statement": (
            "Supply the existing research run and action registry required to reconstruct the "
            "workstream's verified scientific state."
        ),
        "status": "runtime_context_required",
        "blocker": {
            "kind": "runtime_context",
            "code": "required_context_missing",
            "summary": "The adapter requires runtime evidence that was not supplied to this program build.",
        },
        "evidence_gap_status": "runtime_context_missing",
        "evidence_requirements": [
            "Existing research run directory",
            "Versioned action registry path",
        ],
        "selected_action": None,
        "action_frontier": [],
        "claim_boundary": None,
        "epistemic_hypothesis": {
            "type": "readiness_hypothesis",
            "statement": "No new scientific decision is defensible until the prior runtime state is reconstructed.",
            "scientific_mechanism_claim": False,
        },
        "scientific_hypothesis_generation_status": "blocked_by_missing_runtime_context",
        "expected_information_gain": {
            "status": "not_quantified",
            "value": None,
            "boundary": "Restoring provenance is a prerequisite, not a scientific-value estimate.",
        },
    }


def build_research_program(
    mission_path: str | Path,
    *,
    repository_root: str | Path,
    runtime_context_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build a mission-level research agenda from verified domain planning states."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    mission_file = Path(mission_path).expanduser().resolve(strict=True)
    mission = validate_research_mission(_load_json(mission_file))
    context_file = (
        Path(runtime_context_path) if runtime_context_path is not None else None
    )
    runtime_context, context_binding = _load_runtime_context(context_file)
    context_workstreams = runtime_context["workstreams"]

    goals: list[dict[str, Any]] = []
    workstream_states: list[dict[str, Any]] = []
    for workstream in mission["workstreams"]:
        if not workstream["enabled"]:
            workstream_states.append(
                {
                    "workstream_id": workstream["workstream_id"],
                    "adapter_id": workstream["adapter_id"],
                    "status": "disabled_by_mission",
                    "planning_state": None,
                }
            )
            continue
        workstream_id = workstream["workstream_id"]
        adapter_id = workstream["adapter_id"]
        context = context_workstreams.get(workstream_id, {})
        if adapter_id == "nasa-battery" and not {
            "research_run",
            "action_registry_path",
        }.issubset(context):
            goal = _runtime_context_goal(mission["mission_id"], workstream)
            goals.append(goal)
            workstream_states.append(
                {
                    "workstream_id": workstream_id,
                    "adapter_id": adapter_id,
                    "status": "runtime_context_required",
                    "planning_state": None,
                }
            )
            continue
        planning_state = build_research_planning_state(
            adapter_id,
            repository_root=root,
            research_run=context.get("research_run"),
            action_registry_path=context.get("action_registry_path"),
        )
        goal = _goal_from_state(mission["mission_id"], workstream, planning_state)
        goals.append(goal)
        workstream_states.append(
            {
                "workstream_id": workstream_id,
                "adapter_id": adapter_id,
                "status": "verified",
                "planning_state": planning_state,
            }
        )

    if mission["autonomy_policy"]["goal_generation"] == "manual_only":
        goals = []
    goals.sort(key=lambda item: (-int(item["priority"]), str(item["goal_id"])))
    active_goals = [goal for goal in goals if goal["status"] != "scope_exhausted"]
    next_step = _program_step_for_goal(active_goals[0]) if active_goals else None
    return {
        "schema_version": PROGRAM_SCHEMA_VERSION,
        "program_policy_version": PROGRAM_POLICY_VERSION,
        "mission": mission,
        "mission_binding": {
            "path": str(mission_file),
            "sha256": _sha256_file(mission_file),
        },
        "runtime_context_binding": context_binding,
        "workstreams": workstream_states,
        "generated_goals": goals,
        "next_program_step": next_step,
        "autonomy_boundary": {
            "goal_generation_performed": bool(goals),
            "scientific_hypotheses_invented": False,
            "reasoning_proposals_may_be_schema_validated": (
                mission["autonomy_policy"]["reasoning_proposals"] == "schema_validated"
            ),
            "typed_action_execution_performed": False,
            "network_access_performed": False,
            "physical_experiment_execution_available": False,
            "scientific_evidence_upgraded": False,
        },
    }


def _known_evidence_bindings(program_state: Mapping[str, Any]) -> set[tuple[str, str, str]]:
    known: set[tuple[str, str, str]] = set()
    workstreams = program_state.get("workstreams")
    if not isinstance(workstreams, list):
        raise ResearchProgramError("program_state.workstreams must be a list")
    for item in workstreams:
        if not isinstance(item, Mapping):
            continue
        workstream_id = item.get("workstream_id")
        planning_state = item.get("planning_state")
        if not isinstance(workstream_id, str) or not isinstance(planning_state, Mapping):
            continue
        bindings = planning_state.get("evidence_bindings")
        if not isinstance(bindings, list):
            continue
        for binding in bindings:
            if not isinstance(binding, Mapping):
                continue
            role = binding.get("role")
            sha256 = binding.get("sha256")
            if isinstance(role, str) and isinstance(sha256, str):
                known.add((workstream_id, role, sha256))
    return known


def validate_reasoning_proposal(
    proposal: object,
    program_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate an evidence-bound scientific reasoning proposal for planning only."""
    root = _require_exact_keys(
        proposal,
        required={
            "schema_version",
            "proposal_id",
            "goal_id",
            "research_question",
            "evidence_bindings",
            "new_hypotheses",
            "proposed_actions",
            "known_limitations",
            "stop_condition",
        },
        allowed={
            "schema_version",
            "proposal_id",
            "goal_id",
            "research_question",
            "evidence_bindings",
            "new_hypotheses",
            "proposed_actions",
            "known_limitations",
            "stop_condition",
        },
        field="reasoning proposal",
    )
    if root["schema_version"] != REASONING_PROPOSAL_SCHEMA_VERSION:
        raise ResearchProgramError("unsupported reasoning proposal schema_version")

    goals = program_state.get("generated_goals")
    if not isinstance(goals, list):
        raise ResearchProgramError("program_state.generated_goals must be a list")
    goal_id = _nonempty_text(root["goal_id"], "reasoning proposal goal_id")
    matching = [goal for goal in goals if isinstance(goal, Mapping) and goal.get("goal_id") == goal_id]
    if len(matching) != 1:
        raise ResearchProgramError("reasoning proposal must bind exactly one generated goal")
    goal = matching[0]
    research_question = _nonempty_text(root["research_question"], "reasoning proposal research_question")
    if research_question != goal.get("research_question"):
        raise ResearchProgramError("reasoning proposal research_question does not match the bound goal")

    known_bindings = _known_evidence_bindings(program_state)
    raw_bindings = root["evidence_bindings"]
    if not isinstance(raw_bindings, list):
        raise ResearchProgramError("reasoning proposal evidence_bindings must be a list")
    normalized_bindings: list[dict[str, str]] = []
    for index, raw in enumerate(raw_bindings):
        item = _require_exact_keys(
            raw,
            required={"workstream_id", "role", "sha256"},
            allowed={"workstream_id", "role", "sha256"},
            field=f"reasoning proposal evidence_bindings[{index}]",
        )
        binding = (
            _nonempty_text(item["workstream_id"], "evidence binding workstream_id"),
            _nonempty_text(item["role"], "evidence binding role"),
            _nonempty_text(item["sha256"], "evidence binding sha256"),
        )
        if binding not in known_bindings:
            raise ResearchProgramError(
                "reasoning proposal references evidence that is not bound by the verified program state"
            )
        normalized_bindings.append(
            {"workstream_id": binding[0], "role": binding[1], "sha256": binding[2]}
        )

    raw_hypotheses = root["new_hypotheses"]
    if not isinstance(raw_hypotheses, list):
        raise ResearchProgramError("reasoning proposal new_hypotheses must be a list")
    hypothesis_ids: set[str] = set()
    normalized_hypotheses: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_hypotheses):
        item = _require_exact_keys(
            raw,
            required={"hypothesis_id", "statement", "falsification_criteria", "discriminating_evidence"},
            allowed={"hypothesis_id", "statement", "falsification_criteria", "discriminating_evidence"},
            field=f"reasoning proposal new_hypotheses[{index}]",
        )
        hypothesis_id = _nonempty_text(item["hypothesis_id"], "hypothesis_id")
        if hypothesis_id in hypothesis_ids:
            raise ResearchProgramError(f"duplicate hypothesis_id: {hypothesis_id}")
        hypothesis_ids.add(hypothesis_id)
        normalized_hypotheses.append(
            {
                "hypothesis_id": hypothesis_id,
                "statement": _nonempty_text(item["statement"], "hypothesis statement"),
                "falsification_criteria": _string_list(
                    item["falsification_criteria"], "falsification_criteria"
                ),
                "discriminating_evidence": _string_list(
                    item["discriminating_evidence"], "discriminating_evidence"
                ),
                "status": "proposed_not_evidence_upgraded",
            }
        )

    raw_actions = root["proposed_actions"]
    if not isinstance(raw_actions, list):
        raise ResearchProgramError("reasoning proposal proposed_actions must be a list")
    action_ids: set[str] = set()
    normalized_actions: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_actions):
        item = _require_exact_keys(
            raw,
            required={
                "action_id",
                "action_class",
                "description",
                "rationale",
                "required_evidence",
                "expected_outcome",
                "execution_mode",
            },
            allowed={
                "action_id",
                "action_class",
                "description",
                "rationale",
                "required_evidence",
                "expected_outcome",
                "execution_mode",
            },
            field=f"reasoning proposal proposed_actions[{index}]",
        )
        action_id = _nonempty_text(item["action_id"], "action_id")
        if action_id in action_ids:
            raise ResearchProgramError(f"duplicate action_id: {action_id}")
        action_ids.add(action_id)
        action_class = _enum(item["action_class"], _ALLOWED_ACTION_CLASSES, "action_class")
        execution_mode = _enum(
            item["execution_mode"], _ALLOWED_PROPOSAL_EXECUTION_MODES, "execution_mode"
        )
        if action_class == "external_evidence_search" and execution_mode != "explicit_authorization_required":
            raise ResearchProgramError(
                "external_evidence_search must require explicit authorization"
            )
        if action_class == "physical_experiment_design" and execution_mode != "plan_only":
            raise ResearchProgramError("physical_experiment_design is plan-only")
        if execution_mode == "typed_local_action" and action_class not in {
            "existing_data_reanalysis",
            "computational_experiment",
            "sensitivity_analysis",
            "simulation",
            "replication",
        }:
            raise ResearchProgramError(
                "typed_local_action is allowed only for bounded computational/data actions"
            )
        normalized_actions.append(
            {
                "action_id": action_id,
                "action_class": action_class,
                "description": _nonempty_text(item["description"], "action description"),
                "rationale": _nonempty_text(item["rationale"], "action rationale"),
                "required_evidence": _string_list(
                    item["required_evidence"], "required_evidence", allow_empty=True
                ),
                "expected_outcome": _nonempty_text(item["expected_outcome"], "expected_outcome"),
                "execution_mode": execution_mode,
                "automatic_execution_authorized": False,
            }
        )

    return {
        "schema_version": REASONING_PROPOSAL_SCHEMA_VERSION,
        "proposal_id": _nonempty_text(root["proposal_id"], "proposal_id"),
        "goal_id": goal_id,
        "research_question": research_question,
        "proposal_status": "validated_for_planning_only",
        "evidence_bindings": normalized_bindings,
        "new_hypotheses": normalized_hypotheses,
        "proposed_actions": normalized_actions,
        "known_limitations": _string_list(root["known_limitations"], "known_limitations"),
        "stop_condition": _nonempty_text(root["stop_condition"], "stop_condition"),
        "autonomy_boundary": {
            "scientific_evidence_upgraded": False,
            "automatic_action_execution_authorized": False,
            "network_access_authorized": False,
            "physical_experiment_execution_authorized": False,
        },
    }


def validate_reasoning_proposal_file(
    proposal_path: str | Path,
    program_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Load and validate one reasoning proposal while preserving its exact file binding."""
    path = Path(proposal_path).expanduser().resolve(strict=True)
    result = validate_reasoning_proposal(_load_json(path), program_state)
    return {
        **result,
        "proposal_binding": {"path": str(path), "sha256": _sha256_file(path)},
    }


__all__ = [
    "MISSION_SCHEMA_VERSION",
    "PROGRAM_POLICY_VERSION",
    "PROGRAM_SCHEMA_VERSION",
    "REASONING_PROPOSAL_SCHEMA_VERSION",
    "ResearchProgramError",
    "build_research_program",
    "validate_reasoning_proposal",
    "validate_reasoning_proposal_file",
    "validate_research_mission",
]
