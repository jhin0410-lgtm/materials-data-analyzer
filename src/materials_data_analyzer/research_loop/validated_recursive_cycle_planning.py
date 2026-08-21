"""Validated public planning entry for bounded recursive research cycles.

Every published checkpoint is reconstructed from the exact hardened discrepancy handoff
and deterministic planner inputs. Successor cycles additionally reconstruct the entire
predecessor validated-planning artifact from its own original inputs; a caller-authored
raw predecessor checkpoint is never accepted as ancestry on its own.

The published checkpoint also carries an immutable recursive resource-budget binding.
That budget counts planning cycles and authorization action slots rather than claiming
that an action executed; execution truth remains owned by the independent typed executor
and immutable-ledger evidence chain.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .autonomous_inquiry_plan_verifier import validate_autonomous_inquiry_plan
from .discrepancy_planning_handoff_policy import (
    validate_policy_hardened_discrepancy_planning_handoff,
)
from .kernel import ResearchLoopError
from .recursive_research_cycle_controller import (
    _build_recursive_research_cycle_checkpoint,
)
from .recursive_resource_budget import (
    apply_recursive_resource_budget,
    normalize_recursive_limits,
)

VALIDATED_RECURSIVE_PLANNING_SCHEMA_VERSION = "1.0"
VALIDATED_RECURSIVE_PLANNING_POLICY_VERSION = "1.1"


class ValidatedRecursivePlanningError(ResearchLoopError):
    """Raised when validated recursive-planning ancestry cannot be reconstructed."""


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidatedRecursivePlanningError(f"{field} must be an object")
    return value


def _optional_mapping(value: object, field: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    return _mapping(value, field)


def _context_float(context: Mapping[str, Any], field: str, default: float) -> float:
    value = context.get(field, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidatedRecursivePlanningError(
            f"previous validation_inputs.{field} must be numeric"
        )
    return float(value)


def _context_recursive_limits(
    context: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    value = context.get("recursive_limits")
    if value is None:
        return None
    return _mapping(value, "previous validation_inputs.recursive_limits")


def _reconstruct_predecessor_context(
    context: Mapping[str, Any],
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    ctx = _mapping(context, "previous_validated_planning_context")
    artifact = _mapping(
        ctx.get("validated_planning_artifact"),
        "previous_validated_planning_context.validated_planning_artifact",
    )
    inputs = _mapping(
        ctx.get("validation_inputs"),
        "previous_validated_planning_context.validation_inputs",
    )
    verification = validate_validated_recursive_planning_checkpoint(
        artifact,
        planning_handoff=_mapping(
            inputs.get("planning_handoff"),
            "previous validation_inputs.planning_handoff",
        ),
        source_discrepancy_report=_mapping(
            inputs.get("source_discrepancy_report"),
            "previous validation_inputs.source_discrepancy_report",
        ),
        source_evaluated_graph=_mapping(
            inputs.get("source_evaluated_graph"),
            "previous validation_inputs.source_evaluated_graph",
        ),
        fresh_plan=_mapping(
            inputs.get("fresh_plan"), "previous validation_inputs.fresh_plan"
        ),
        planner_program_state=_mapping(
            inputs.get("planner_program_state"),
            "previous validation_inputs.planner_program_state",
        ),
        source_hypothesis_portfolio=_optional_mapping(
            inputs.get("source_hypothesis_portfolio"),
            "previous validation_inputs.source_hypothesis_portfolio",
        ),
        previous_discrepancy_report=_optional_mapping(
            inputs.get("previous_discrepancy_report"),
            "previous validation_inputs.previous_discrepancy_report",
        ),
        candidate_match=_optional_mapping(
            inputs.get("candidate_match"),
            "previous validation_inputs.candidate_match",
        ),
        planner_critic_report=_optional_mapping(
            inputs.get("planner_critic_report"),
            "previous validation_inputs.planner_critic_report",
        ),
        planner_reasoning_proposal=_optional_mapping(
            inputs.get("planner_reasoning_proposal"),
            "previous validation_inputs.planner_reasoning_proposal",
        ),
        budget_units=_context_float(inputs, "budget_units", 8.0),
        minimum_utility=_context_float(inputs, "minimum_utility", 0.01),
        previous_validated_planning_context=_optional_mapping(
            inputs.get("previous_validated_planning_context"),
            "previous validation_inputs.previous_validated_planning_context",
        ),
        recursive_limits=_context_recursive_limits(inputs),
    )
    checkpoint = _mapping(
        verification.get("recursive_checkpoint"),
        "previous validated planning recursive_checkpoint",
    )
    resource_budget = _mapping(
        verification.get("recursive_resource_budget"),
        "previous validated planning recursive_resource_budget",
    )
    digest = verification.get("validated_checkpoint_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValidatedRecursivePlanningError(
            "previous validated planning artifact omitted canonical SHA-256"
        )
    return dict(checkpoint), digest, dict(resource_budget)


def build_validated_recursive_planning_checkpoint(
    *,
    planning_handoff: Mapping[str, Any],
    source_discrepancy_report: Mapping[str, Any],
    source_evaluated_graph: Mapping[str, Any],
    fresh_plan: Mapping[str, Any],
    planner_program_state: Mapping[str, Any],
    source_hypothesis_portfolio: Mapping[str, Any] | None = None,
    previous_discrepancy_report: Mapping[str, Any] | None = None,
    candidate_match: Mapping[str, Any] | None = None,
    planner_critic_report: Mapping[str, Any] | None = None,
    planner_reasoning_proposal: Mapping[str, Any] | None = None,
    budget_units: float = 8.0,
    minimum_utility: float = 0.01,
    previous_checkpoint: Mapping[str, Any] | None = None,
    previous_validated_planning_context: Mapping[str, Any] | None = None,
    recursive_limits: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        handoff_verification = validate_policy_hardened_discrepancy_planning_handoff(
            planning_handoff,
            discrepancy_report=source_discrepancy_report,
            evaluated_graph=source_evaluated_graph,
            hypothesis_portfolio=source_hypothesis_portfolio,
            previous_discrepancy_report=previous_discrepancy_report,
        )
    except ResearchLoopError as exc:
        raise ValidatedRecursivePlanningError(
            "planning handoff failed hardened discrepancy-source reconstruction"
        ) from exc
    planner_verification = validate_autonomous_inquiry_plan(
        fresh_plan,
        program_state=planner_program_state,
        critic_report=planner_critic_report,
        validated_reasoning_proposal=planner_reasoning_proposal,
        budget_units=budget_units,
        minimum_utility=minimum_utility,
    )

    reconstructed_previous: dict[str, Any] | None = None
    previous_artifact_sha: str | None = None
    previous_resource_budget: dict[str, Any] | None = None
    if previous_validated_planning_context is not None:
        (
            reconstructed_previous,
            previous_artifact_sha,
            previous_resource_budget,
        ) = _reconstruct_predecessor_context(previous_validated_planning_context)
        if (
            previous_checkpoint is not None
            and dict(previous_checkpoint) != reconstructed_previous
        ):
            raise ValidatedRecursivePlanningError(
                "raw previous checkpoint differs from reconstructed predecessor"
            )
    elif previous_checkpoint is not None:
        raise ValidatedRecursivePlanningError(
            "raw predecessor checkpoint is not accepted without deterministic "
            "validated-planning reconstruction"
        )

    effective_limits: Mapping[str, Any] | None = recursive_limits
    if effective_limits is None and previous_resource_budget is not None:
        effective_limits = _mapping(
            previous_resource_budget.get("limits"),
            "previous recursive_resource_budget.limits",
        )
    normalized_limits = normalize_recursive_limits(effective_limits)

    base_checkpoint = _build_recursive_research_cycle_checkpoint(
        planning_handoff=planning_handoff,
        fresh_plan=fresh_plan,
        candidate_match=candidate_match,
        previous_checkpoint=reconstructed_previous,
    )
    checkpoint, resource_budget = apply_recursive_resource_budget(
        checkpoint=base_checkpoint,
        fresh_plan=fresh_plan,
        previous_checkpoint=reconstructed_previous,
        previous_budget=previous_resource_budget,
        recursive_limits=normalized_limits,
    )
    if (
        planner_verification["plan_sha256"]
        != checkpoint["ancestry"]["fresh_plan_sha256"]
    ):
        raise ValidatedRecursivePlanningError(
            "verified planner SHA diverged before recursive checkpoint publication"
        )
    if (
        handoff_verification["handoff_sha256"]
        != checkpoint["ancestry"]["planning_handoff_sha256"]
    ):
        raise ValidatedRecursivePlanningError(
            "verified discrepancy handoff SHA diverged before checkpoint publication"
        )

    result: dict[str, Any] = {
        "schema_version": VALIDATED_RECURSIVE_PLANNING_SCHEMA_VERSION,
        "policy_version": VALIDATED_RECURSIVE_PLANNING_POLICY_VERSION,
        "handoff_verification": handoff_verification,
        "planner_verification": planner_verification,
        "recursive_checkpoint": checkpoint,
        "recursive_resource_budget": resource_budget,
        "predecessor_validation": (
            None
            if reconstructed_previous is None
            else {
                "validated_planning_artifact_sha256": previous_artifact_sha,
                "recursive_checkpoint_sha256": reconstructed_previous[
                    "checkpoint_sha256"
                ],
                "recursive_resource_budget_sha256": previous_resource_budget[
                    "budget_sha256"
                ],
                "deterministically_reconstructed": True,
            }
        ),
        "autonomy_boundary": {
            "source_discrepancy_hardening_verified": True,
            "planner_reconstruction_verified": True,
            "predecessor_reconstruction_verified": reconstructed_previous is not None,
            "recursive_resource_limits_enforced": True,
            "raw_predecessor_checkpoint_trusted": False,
            "critic_proposal_executed_directly": False,
            "planner_candidate_injected": False,
            "authorization_granted": False,
            "request_compiled": False,
            "execution_performed": False,
            "scientific_status_changed": False,
        },
    }
    result["validated_checkpoint_sha256"] = _canonical_sha256(result)
    return result


def validate_validated_recursive_planning_checkpoint(
    artifact: Mapping[str, Any],
    *,
    planning_handoff: Mapping[str, Any],
    source_discrepancy_report: Mapping[str, Any],
    source_evaluated_graph: Mapping[str, Any],
    fresh_plan: Mapping[str, Any],
    planner_program_state: Mapping[str, Any],
    source_hypothesis_portfolio: Mapping[str, Any] | None = None,
    previous_discrepancy_report: Mapping[str, Any] | None = None,
    candidate_match: Mapping[str, Any] | None = None,
    planner_critic_report: Mapping[str, Any] | None = None,
    planner_reasoning_proposal: Mapping[str, Any] | None = None,
    budget_units: float = 8.0,
    minimum_utility: float = 0.01,
    previous_checkpoint: Mapping[str, Any] | None = None,
    previous_validated_planning_context: Mapping[str, Any] | None = None,
    recursive_limits: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    supplied = dict(_mapping(artifact, "validated planning artifact"))
    if supplied.get("schema_version") != VALIDATED_RECURSIVE_PLANNING_SCHEMA_VERSION:
        raise ValidatedRecursivePlanningError(
            "validated planning artifact schema_version drifted"
        )
    if supplied.get("policy_version") != VALIDATED_RECURSIVE_PLANNING_POLICY_VERSION:
        raise ValidatedRecursivePlanningError(
            "validated planning artifact policy_version drifted"
        )
    embedded = supplied.get("validated_checkpoint_sha256")
    if not isinstance(embedded, str) or len(embedded) != 64:
        raise ValidatedRecursivePlanningError(
            "validated planning artifact SHA-256 is malformed"
        )
    unsigned = dict(supplied)
    unsigned.pop("validated_checkpoint_sha256", None)
    if _canonical_sha256(unsigned) != embedded:
        raise ValidatedRecursivePlanningError(
            "validated planning artifact SHA-256 does not match canonical content"
        )

    # Validation must replay against an externally expected limit contract. If no
    # expected contract is supplied, repository defaults are authoritative; limits
    # embedded in the caller-provided artifact are never used to validate themselves.
    normalized_limits = normalize_recursive_limits(recursive_limits)

    rebuilt = build_validated_recursive_planning_checkpoint(
        planning_handoff=planning_handoff,
        source_discrepancy_report=source_discrepancy_report,
        source_evaluated_graph=source_evaluated_graph,
        fresh_plan=fresh_plan,
        planner_program_state=planner_program_state,
        source_hypothesis_portfolio=source_hypothesis_portfolio,
        previous_discrepancy_report=previous_discrepancy_report,
        candidate_match=candidate_match,
        planner_critic_report=planner_critic_report,
        planner_reasoning_proposal=planner_reasoning_proposal,
        budget_units=budget_units,
        minimum_utility=minimum_utility,
        previous_checkpoint=previous_checkpoint,
        previous_validated_planning_context=previous_validated_planning_context,
        recursive_limits=normalized_limits,
    )
    if rebuilt != supplied:
        raise ValidatedRecursivePlanningError(
            "validated planning artifact differs from deterministic reconstruction"
        )
    checkpoint = _mapping(
        rebuilt.get("recursive_checkpoint"),
        "validated planning artifact recursive_checkpoint",
    )
    resource_budget = _mapping(
        rebuilt.get("recursive_resource_budget"),
        "validated planning artifact recursive_resource_budget",
    )
    return {
        "validated_checkpoint_sha256": embedded,
        "recursive_checkpoint": dict(checkpoint),
        "recursive_resource_budget": dict(resource_budget),
        "handoff_verification": dict(rebuilt["handoff_verification"]),
        "planner_verification": dict(rebuilt["planner_verification"]),
        "predecessor_validation": rebuilt.get("predecessor_validation"),
        "authorization_granted": False,
        "execution_performed": False,
        "scientific_status_changed": False,
    }


__all__ = [
    "VALIDATED_RECURSIVE_PLANNING_POLICY_VERSION",
    "VALIDATED_RECURSIVE_PLANNING_SCHEMA_VERSION",
    "ValidatedRecursivePlanningError",
    "build_validated_recursive_planning_checkpoint",
    "validate_validated_recursive_planning_checkpoint",
]
