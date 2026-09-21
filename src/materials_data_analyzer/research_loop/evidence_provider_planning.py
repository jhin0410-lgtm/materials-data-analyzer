"""Controller integration for authenticated Evidence Provider state.

This module projects provider requirements into planner goals without creating planner actions.
Provider requirements remain planning metadata. Candidate availability, authorization, execution,
and scientific promotion stay owned by their existing independent boundaries.
"""
from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from .evidence_packet import canonical_sha256
from .evidence_provider_contract import (
    AuthenticatedProviderStateInput,
    EvidenceProviderContractError,
    aggregate_provider_requirements,
    validate_provider_requirement_aggregate,
    validate_provider_state,
)

PROVIDER_PLANNING_SCHEMA_VERSION = "1.0"
PROVIDER_PLANNING_POLICY_VERSION = "1.0"
PROVIDER_TRANSITION_SCHEMA_VERSION = "1.0"
PROVIDER_TRANSITION_POLICY_VERSION = "1.0"

_PROVIDER_BINDING_KEYS = frozenset(
    {
        "schema_version",
        "policy_version",
        "aggregate_sha256",
        "composite_binding_sha256",
        "provider_state_sha256s",
        "provider_requirement_count",
        "requirements_projected_as_candidate_actions",
        "exact_candidate_matching_required",
        "execution_authorized",
        "scientific_status_promoted",
    }
)
_TRANSITION_KEYS = frozenset(
    {
        "schema_version",
        "policy_version",
        "transition_type",
        "provider_id",
        "previous_provider_state_sha256",
        "current_provider_state_sha256",
        "previous_aggregate_sha256",
        "current_aggregate_sha256",
        "unchanged_provider_state_sha256s",
        "state_changed",
        "next_planning_cycle_required",
        "stop_reason",
        "authority_boundary",
        "transition_sha256",
    }
)
_TRANSITION_AUTHORITY_KEYS = frozenset(
    {
        "planning_metadata_only",
        "empirical_evidence_created",
        "scientific_status_promoted",
        "downstream_use_authorized",
        "execution_authorized",
    }
)


class EvidenceProviderPlanningError(ValueError):
    """Raised when provider planning composition would weaken provenance or authority."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceProviderPlanningError(message)


def _mapping(value: object, *, field: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{field} must be an object")
    return value


def _sequence(value: object, *, field: str) -> Sequence[object]:
    _require(
        not isinstance(value, (str, bytes, bytearray))
        and isinstance(value, Sequence),
        f"{field} must be a sequence",
    )
    return value


def _text(value: object, *, field: str) -> str:
    _require(
        isinstance(value, str) and bool(value) and value == value.strip(),
        f"{field} must be exact non-empty text",
    )
    return value


def _sha(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    _require(
        len(text) == 64
        and all(character in "0123456789abcdef" for character in text),
        f"{field} must be lowercase SHA-256",
    )
    return text


def _exact_keys(
    value: object,
    expected: frozenset[str],
    *,
    field: str,
) -> Mapping[str, Any]:
    item = _mapping(value, field=field)
    observed = set(item)
    _require(
        observed == expected,
        f"{field} must use exact keys; unknown={sorted(observed - expected)}, "
        f"missing={sorted(expected - observed)}",
    )
    return item


def _typed_equal(observed: object, expected: object) -> bool:
    if isinstance(expected, bool):
        return type(observed) is bool and observed is expected
    if isinstance(expected, int):
        return type(observed) is int and observed == expected
    if expected is None:
        return observed is None
    if isinstance(expected, str):
        return type(observed) is str and observed == expected
    if isinstance(expected, list):
        return (
            isinstance(observed, list)
            and len(observed) == len(expected)
            and all(
                _typed_equal(left, right)
                for left, right in zip(observed, expected, strict=True)
            )
        )
    if isinstance(expected, Mapping):
        return (
            isinstance(observed, Mapping)
            and set(observed) == set(expected)
            and all(_typed_equal(observed[key], expected[key]) for key in expected)
        )
    return type(observed) is type(expected) and observed == expected


def _authority_boundary() -> dict[str, bool]:
    return {
        "planning_metadata_only": True,
        "empirical_evidence_created": False,
        "scientific_status_promoted": False,
        "downstream_use_authorized": False,
        "execution_authorized": False,
    }


def serialize_authenticated_provider_inputs(
    inputs: Sequence[AuthenticatedProviderStateInput],
) -> list[dict[str, Any]]:
    """Return canonical-JSON-friendly provider inputs for persisted validation context."""

    result: list[dict[str, Any]] = []
    for index, item in enumerate(inputs):
        _require(
            isinstance(item, AuthenticatedProviderStateInput),
            f"provider input[{index}] must be AuthenticatedProviderStateInput",
        )
        state = validate_provider_state(item.state)
        trusted = _sha(
            item.trusted_provider_state_sha256,
            field=f"provider input[{index}].trusted_provider_state_sha256",
        )
        _require(
            state["provider_state_sha256"] == trusted,
            f"provider input[{index}] does not match external trust-root SHA-256",
        )
        result.append(
            {
                "state": copy.deepcopy(state),
                "trusted_provider_state_sha256": trusted,
            }
        )
    return result


def deserialize_authenticated_provider_inputs(
    values: object,
) -> list[AuthenticatedProviderStateInput]:
    """Restore and validate persisted JSON-friendly provider inputs."""

    result: list[AuthenticatedProviderStateInput] = []
    for index, raw in enumerate(_sequence(values, field="provider_state_inputs")):
        item = _mapping(raw, field=f"provider_state_inputs[{index}]")
        _require(
            set(item) == {"state", "trusted_provider_state_sha256"},
            f"provider_state_inputs[{index}] must use exact keys",
        )
        state = validate_provider_state(
            _mapping(item.get("state"), field=f"provider_state_inputs[{index}].state")
        )
        trusted = _sha(
            item.get("trusted_provider_state_sha256"),
            field=f"provider_state_inputs[{index}].trusted_provider_state_sha256",
        )
        _require(
            state["provider_state_sha256"] == trusted,
            f"provider_state_inputs[{index}] external trust root mismatch",
        )
        result.append(
            AuthenticatedProviderStateInput(
                state=state,
                trusted_provider_state_sha256=trusted,
            )
        )
    return result


def _provider_binding(aggregate: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_provider_requirement_aggregate(aggregate)
    requirements = validated["requirements"]
    assert isinstance(requirements, list)
    return {
        "schema_version": PROVIDER_PLANNING_SCHEMA_VERSION,
        "policy_version": PROVIDER_PLANNING_POLICY_VERSION,
        "aggregate_sha256": validated["aggregate_sha256"],
        "composite_binding_sha256": validated["composite_binding_sha256"],
        "provider_state_sha256s": copy.deepcopy(
            validated["provider_state_sha256s"]
        ),
        "provider_requirement_count": len(requirements),
        "requirements_projected_as_candidate_actions": False,
        "exact_candidate_matching_required": True,
        "execution_authorized": False,
        "scientific_status_promoted": False,
    }


def _provider_goal(record: Mapping[str, Any]) -> dict[str, Any]:
    provider_id = _text(record.get("provider_id"), field="provider requirement.provider_id")
    aggregate_requirement_id = _text(
        record.get("aggregate_requirement_id"),
        field="provider requirement.aggregate_requirement_id",
    )
    provider_sha = _sha(
        record.get("provider_state_sha256"),
        field="provider requirement.provider_state_sha256",
    )
    requirement = _mapping(
        record.get("requirement"),
        field="provider requirement.requirement",
    )
    requirement_id = _text(
        requirement.get("requirement_id"),
        field="provider requirement.requirement_id",
    )
    description = _text(
        requirement.get("description"),
        field="provider requirement.description",
    )
    requirement_class = _text(
        requirement.get("requirement_class"),
        field="provider requirement.requirement_class",
    )
    action_class = _text(
        requirement.get("action_class"),
        field="provider requirement.action_class",
    )
    stable = canonical_sha256(
        {
            "provider_id": provider_id,
            "provider_state_sha256": provider_sha,
            "aggregate_requirement_id": aggregate_requirement_id,
        }
    )[:16]
    return {
        "goal_id": f"provider:{provider_id}:{stable}",
        "workstream_id": f"provider:{provider_id}",
        "research_question": (
            f"What authenticated evidence or analysis is required to resolve "
            f"provider requirement {requirement_id}?"
        ),
        "goal_statement": description,
        "status": "active",
        "priority": "high",
        "evidence_requirements": [description],
        "claim_boundary": {
            "provider_id": provider_id,
            "provider_state_sha256": provider_sha,
            "aggregate_requirement_id": aggregate_requirement_id,
            "requirement_id": requirement_id,
            "requirement_class": requirement_class,
            "requested_action_semantics": action_class,
            "scientific_status": "unchanged",
            "planning_metadata_only": True,
            "candidate_availability_asserted": False,
            "authorization_granted": False,
        },
        # Critical boundary: provider metadata may create a planning gap, never an action candidate.
        "action_frontier": [],
        "provider_requirement_overlay": True,
    }


def build_provider_planner_program_state(
    base_program_state: Mapping[str, Any],
    inputs: Sequence[AuthenticatedProviderStateInput],
) -> dict[str, Any]:
    """Append deterministic provider goals while leaving all action candidates untouched."""

    aggregate = aggregate_provider_requirements(inputs)
    base = copy.deepcopy(dict(_mapping(base_program_state, field="base_program_state")))
    goals_raw = base.get("generated_goals")
    goals = [
        copy.deepcopy(dict(_mapping(item, field=f"generated_goals[{index}]")))
        for index, item in enumerate(
            _sequence(goals_raw, field="base_program_state.generated_goals")
        )
    ]
    _require(
        all(item.get("provider_requirement_overlay") is not True for item in goals),
        "base program may not pre-author provider overlay goals",
    )
    existing_ids = {
        _text(item.get("goal_id"), field="base generated goal.goal_id")
        for item in goals
    }

    provider_goals: list[dict[str, Any]] = []
    for raw in aggregate["requirements"]:
        record = _mapping(raw, field="provider aggregate requirement")
        goal = _provider_goal(record)
        _require(
            goal["goal_id"] not in existing_ids,
            "provider overlay goal collides with existing goal_id",
        )
        existing_ids.add(goal["goal_id"])
        provider_goals.append(goal)

    base["generated_goals"] = goals + provider_goals
    base["evidence_provider_binding"] = _provider_binding(aggregate)
    return base


def validate_provider_planner_program_state(
    program_state: Mapping[str, Any],
    inputs: Sequence[AuthenticatedProviderStateInput],
) -> dict[str, Any]:
    """Validate provider binding/goals without trusting non-provider program content."""

    program = copy.deepcopy(dict(_mapping(program_state, field="program_state")))
    aggregate = aggregate_provider_requirements(inputs)
    expected_binding = _provider_binding(aggregate)
    observed_binding = _exact_keys(
        program.get("evidence_provider_binding"),
        _PROVIDER_BINDING_KEYS,
        field="evidence_provider_binding",
    )
    _require(
        _typed_equal(observed_binding, expected_binding),
        "planner program provider binding differs from authenticated aggregate",
    )

    goals = _sequence(program.get("generated_goals"), field="program_state.generated_goals")
    for index, raw in enumerate(goals):
        item = _mapping(raw, field=f"generated_goals[{index}]")
        goal_id = _text(item.get("goal_id"), field=f"generated_goals[{index}].goal_id")
        workstream_id = item.get("workstream_id")
        if goal_id.startswith("provider:") or (
            isinstance(workstream_id, str) and workstream_id.startswith("provider:")
        ):
            _require(
                item.get("provider_requirement_overlay") is True,
                "provider namespace goal must be authenticated provider overlay",
            )
    observed_provider_goals = [
        dict(_mapping(item, field=f"generated_goals[{index}]"))
        for index, item in enumerate(goals)
        if isinstance(item, Mapping)
        and item.get("provider_requirement_overlay") is True
    ]
    expected_provider_goals = [
        _provider_goal(_mapping(item, field="provider aggregate requirement"))
        for item in aggregate["requirements"]
    ]
    _require(
        _typed_equal(observed_provider_goals, expected_provider_goals),
        "planner program provider goals differ from authenticated provider requirements",
    )
    _require(
        all(goal.get("action_frontier") == [] for goal in observed_provider_goals),
        "provider goals may not create planner action candidates",
    )
    result: dict[str, Any] = {
        "aggregate_sha256": aggregate["aggregate_sha256"],
        "provider_goal_count": len(observed_provider_goals),
        "provider_requirement_count": len(aggregate["requirements"]),
        "provider_candidates_created": False,
        "exact_candidate_matching_required": True,
        "authorization_granted": False,
        "execution_performed": False,
        "scientific_status_changed": False,
    }
    result["verification_sha256"] = canonical_sha256(result)
    return result


def _provider_id_from_input(item: AuthenticatedProviderStateInput, *, field: str) -> str:
    state = validate_provider_state(item.state)
    trusted = _sha(
        item.trusted_provider_state_sha256,
        field=f"{field}.trusted_provider_state_sha256",
    )
    _require(
        state["provider_state_sha256"] == trusted,
        f"{field} external trust-root SHA-256 mismatch",
    )
    provider = _mapping(state.get("provider"), field=f"{field}.provider")
    return _text(provider.get("provider_id"), field=f"{field}.provider_id")


def build_provider_state_transition(
    previous_inputs: Sequence[AuthenticatedProviderStateInput],
    replacement_input: AuthenticatedProviderStateInput,
) -> dict[str, Any]:
    """Replace exactly one provider state and describe whether new planning information exists."""

    previous_aggregate = aggregate_provider_requirements(previous_inputs)
    replacement_provider_id = _provider_id_from_input(
        replacement_input,
        field="replacement_input",
    )
    prior_by_provider = {
        _provider_id_from_input(item, field=f"previous_input[{index}]"): item
        for index, item in enumerate(previous_inputs)
    }
    _require(
        len(prior_by_provider) == len(previous_inputs),
        "previous provider inputs contain duplicate provider identity",
    )
    _require(
        replacement_provider_id in prior_by_provider,
        "provider transition may replace only an existing provider",
    )

    previous_item = prior_by_provider[replacement_provider_id]
    previous_state = validate_provider_state(previous_item.state)
    replacement_state = validate_provider_state(replacement_input.state)
    updated_inputs = [
        replacement_input
        if _provider_id_from_input(item, field=f"previous_input[{index}]")
        == replacement_provider_id
        else item
        for index, item in enumerate(previous_inputs)
    ]
    current_aggregate = aggregate_provider_requirements(updated_inputs)
    state_changed = (
        previous_state["provider_state_sha256"]
        != replacement_state["provider_state_sha256"]
    )
    unchanged = [
        item
        for item in current_aggregate["provider_state_sha256s"]
        if item["provider_id"] != replacement_provider_id
    ]

    result: dict[str, Any] = {
        "schema_version": PROVIDER_TRANSITION_SCHEMA_VERSION,
        "policy_version": PROVIDER_TRANSITION_POLICY_VERSION,
        "transition_type": "single_provider_state_replacement",
        "provider_id": replacement_provider_id,
        "previous_provider_state_sha256": previous_state["provider_state_sha256"],
        "current_provider_state_sha256": replacement_state["provider_state_sha256"],
        "previous_aggregate_sha256": previous_aggregate["aggregate_sha256"],
        "current_aggregate_sha256": current_aggregate["aggregate_sha256"],
        "unchanged_provider_state_sha256s": copy.deepcopy(unchanged),
        "state_changed": state_changed,
        "next_planning_cycle_required": state_changed,
        "stop_reason": None if state_changed else "no_new_provider_information",
        "authority_boundary": _authority_boundary(),
    }
    result["transition_sha256"] = canonical_sha256(result)
    return result


def validate_provider_input_successor(
    previous_inputs: Sequence[AuthenticatedProviderStateInput],
    current_inputs: Sequence[AuthenticatedProviderStateInput],
    *,
    transition: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify that a recursive provider set is unchanged or changes exactly one provider."""

    previous_aggregate = aggregate_provider_requirements(previous_inputs)
    current_aggregate = aggregate_provider_requirements(current_inputs)

    def by_provider(
        values: Sequence[AuthenticatedProviderStateInput],
        *,
        field: str,
    ) -> dict[str, AuthenticatedProviderStateInput]:
        result: dict[str, AuthenticatedProviderStateInput] = {}
        for index, item in enumerate(values):
            provider_id = _provider_id_from_input(
                item,
                field=f"{field}[{index}]",
            )
            _require(
                provider_id not in result,
                f"{field} contains duplicate provider identity",
            )
            result[provider_id] = item
        return result

    previous_by_provider = by_provider(previous_inputs, field="previous_inputs")
    current_by_provider = by_provider(current_inputs, field="current_inputs")
    _require(
        set(previous_by_provider) == set(current_by_provider),
        "recursive provider successor may not add or remove provider identities",
    )

    changed: list[str] = []
    for provider_id in sorted(previous_by_provider):
        previous_state = validate_provider_state(
            previous_by_provider[provider_id].state
        )
        current_state = validate_provider_state(
            current_by_provider[provider_id].state
        )
        if (
            previous_state["provider_state_sha256"]
            != current_state["provider_state_sha256"]
        ):
            changed.append(provider_id)

    _require(
        len(changed) <= 1,
        "recursive provider successor may change at most one provider state",
    )

    transition_verification: dict[str, Any] | None = None
    if not changed:
        _require(
            transition is None,
            "unchanged provider set must not claim a state-changing transition",
        )
        state_changed = False
        changed_provider_id = None
    else:
        _require(
            transition is not None,
            "changed provider set requires an authenticated single-provider transition",
        )
        changed_provider_id = changed[0]
        transition_verification = validate_provider_state_transition(
            transition,
            previous_inputs,
            current_by_provider[changed_provider_id],
        )
        _require(
            transition_verification["state_changed"] is True,
            "changed provider set requires a state-changing transition",
        )
        _require(
            transition_verification["provider_id"] == changed_provider_id,
            "provider transition changed-provider identity mismatch",
        )
        _require(
            transition_verification["previous_aggregate_sha256"]
            == previous_aggregate["aggregate_sha256"]
            and transition_verification["current_aggregate_sha256"]
            == current_aggregate["aggregate_sha256"],
            "provider transition aggregate ancestry mismatch",
        )
        state_changed = True

    result: dict[str, Any] = {
        "previous_aggregate_sha256": previous_aggregate["aggregate_sha256"],
        "current_aggregate_sha256": current_aggregate["aggregate_sha256"],
        "provider_identity_set_unchanged": True,
        "changed_provider_count": len(changed),
        "changed_provider_id": changed_provider_id,
        "state_changed": state_changed,
        "transition_verification": copy.deepcopy(transition_verification),
        "multiple_provider_changes_accepted": False,
        "provider_add_remove_accepted": False,
        "scientific_status_promoted": False,
        "execution_authorized": False,
    }
    result["successor_verification_sha256"] = canonical_sha256(result)
    return result


def _remove_verified_provider_overlay(
    program_state: Mapping[str, Any],
    previous_inputs: Sequence[AuthenticatedProviderStateInput],
) -> dict[str, Any]:
    """Remove only a previously authenticated provider overlay from a planner program."""

    program = copy.deepcopy(dict(_mapping(program_state, field="program_state")))
    if "evidence_provider_binding" not in program:
        goals = _sequence(program.get("generated_goals"), field="program_state.generated_goals")
        for index, raw in enumerate(goals):
            item = _mapping(raw, field=f"generated_goals[{index}]")
            goal_id = _text(item.get("goal_id"), field=f"generated_goals[{index}].goal_id")
            workstream_id = item.get("workstream_id")
            _require(
                item.get("provider_requirement_overlay") is not True
                and not goal_id.startswith("provider:")
                and not (
                    isinstance(workstream_id, str)
                    and workstream_id.startswith("provider:")
                ),
                "unbound base planner program contains provider namespace state",
            )
        return program

    validate_provider_planner_program_state(program, previous_inputs)
    goals = _sequence(program.get("generated_goals"), field="program_state.generated_goals")
    program["generated_goals"] = [
        copy.deepcopy(dict(_mapping(item, field=f"generated_goals[{index}]")))
        for index, item in enumerate(goals)
        if not (
            isinstance(item, Mapping)
            and item.get("provider_requirement_overlay") is True
        )
    ]
    program.pop("evidence_provider_binding", None)
    return program


def build_provider_successor_planner_program_state(
    base_program_state: Mapping[str, Any],
    previous_inputs: Sequence[AuthenticatedProviderStateInput],
    replacement_input: AuthenticatedProviderStateInput,
) -> dict[str, Any]:
    """Build provider-only successor planning state only when authenticated provider information changed."""

    applied = apply_provider_state_transition(
        previous_inputs,
        replacement_input,
    )
    transition = applied["transition"]
    successor: dict[str, Any] | None = None
    if transition["state_changed"] is True:
        updated_inputs = deserialize_authenticated_provider_inputs(
            applied["provider_state_inputs"]
        )
        clean_base = _remove_verified_provider_overlay(
            base_program_state,
            previous_inputs,
        )
        successor = build_provider_planner_program_state(
            clean_base,
            updated_inputs,
        )

    result: dict[str, Any] = {
        "transition": copy.deepcopy(transition),
        "successor_planner_program_state": successor,
        "provider_state_inputs": copy.deepcopy(applied["provider_state_inputs"]),
        "provider_requirement_aggregate": copy.deepcopy(
            applied["provider_requirement_aggregate"]
        ),
        "next_planning_cycle_required": transition["state_changed"] is True,
        "stop_reason": (
            None
            if transition["state_changed"] is True
            else "no_new_provider_information"
        ),
        "authority_boundary": _authority_boundary(),
    }
    result["successor_bundle_sha256"] = canonical_sha256(result)
    return result


def validate_provider_successor_planner_program_state(
    value: object,
    base_program_state: Mapping[str, Any],
    previous_inputs: Sequence[AuthenticatedProviderStateInput],
    replacement_input: AuthenticatedProviderStateInput,
) -> dict[str, Any]:
    """Recompute a provider-only successor bundle from authenticated source state."""

    supplied = dict(_mapping(value, field="ProviderSuccessorPlanningBundle"))
    digest = _sha(
        supplied.pop("successor_bundle_sha256", None),
        field="successor_bundle_sha256",
    )
    _require(
        canonical_sha256(supplied) == digest,
        "ProviderSuccessorPlanningBundle self-hash mismatch",
    )
    supplied["successor_bundle_sha256"] = digest
    expected = build_provider_successor_planner_program_state(
        base_program_state,
        previous_inputs,
        replacement_input,
    )
    _require(
        _typed_equal(supplied, expected),
        "ProviderSuccessorPlanningBundle differs from authenticated recomputation",
    )
    return expected


def validate_provider_state_transition(
    value: object,
    previous_inputs: Sequence[AuthenticatedProviderStateInput],
    replacement_input: AuthenticatedProviderStateInput,
) -> dict[str, Any]:
    """Recompute an affected-provider transition from exact authenticated inputs."""

    supplied = dict(_exact_keys(value, _TRANSITION_KEYS, field="ProviderStateTransition"))
    digest = _sha(supplied.pop("transition_sha256"), field="transition_sha256")
    _require(
        canonical_sha256(supplied) == digest,
        "ProviderStateTransition self-hash mismatch",
    )
    supplied["transition_sha256"] = digest
    _require(
        supplied.get("schema_version") == PROVIDER_TRANSITION_SCHEMA_VERSION
        and supplied.get("policy_version") == PROVIDER_TRANSITION_POLICY_VERSION
        and supplied.get("transition_type") == "single_provider_state_replacement",
        "unsupported ProviderStateTransition contract",
    )
    boundary = _exact_keys(
        supplied.get("authority_boundary"),
        _TRANSITION_AUTHORITY_KEYS,
        field="authority_boundary",
    )
    _require(
        _typed_equal(boundary, _authority_boundary()),
        "ProviderStateTransition authority boundary drifted",
    )
    rebuilt = build_provider_state_transition(previous_inputs, replacement_input)
    _require(
        _typed_equal(supplied, rebuilt),
        "ProviderStateTransition differs from authenticated recomputation",
    )
    return rebuilt


def apply_provider_state_transition(
    previous_inputs: Sequence[AuthenticatedProviderStateInput],
    replacement_input: AuthenticatedProviderStateInput,
) -> dict[str, Any]:
    """Apply exactly one authenticated provider replacement and return replayable next state."""

    transition = build_provider_state_transition(previous_inputs, replacement_input)
    provider_id = transition["provider_id"]
    updated_inputs: list[AuthenticatedProviderStateInput] = []
    replacements = 0
    for index, item in enumerate(previous_inputs):
        current_provider = _provider_id_from_input(
            item,
            field=f"previous_input[{index}]",
        )
        if current_provider == provider_id:
            updated_inputs.append(replacement_input)
            replacements += 1
        else:
            updated_inputs.append(item)
    _require(replacements == 1, "provider transition must replace exactly one provider")
    aggregate = aggregate_provider_requirements(updated_inputs)
    _require(
        aggregate["aggregate_sha256"] == transition["current_aggregate_sha256"],
        "applied provider transition aggregate diverged from transition record",
    )
    return {
        "transition": transition,
        "provider_state_inputs": serialize_authenticated_provider_inputs(updated_inputs),
        "provider_requirement_aggregate": aggregate,
        "next_planning_cycle_required": transition["next_planning_cycle_required"],
        "stop_reason": transition["stop_reason"],
        "authority_boundary": _authority_boundary(),
    }


__all__ = [
    "EvidenceProviderPlanningError",
    "PROVIDER_PLANNING_POLICY_VERSION",
    "PROVIDER_PLANNING_SCHEMA_VERSION",
    "PROVIDER_TRANSITION_POLICY_VERSION",
    "PROVIDER_TRANSITION_SCHEMA_VERSION",
    "apply_provider_state_transition",
    "build_provider_planner_program_state",
    "build_provider_state_transition",
    "build_provider_successor_planner_program_state",
    "deserialize_authenticated_provider_inputs",
    "serialize_authenticated_provider_inputs",
    "validate_provider_input_successor",
    "validate_provider_planner_program_state",
    "validate_provider_state_transition",
    "validate_provider_successor_planner_program_state",
]
