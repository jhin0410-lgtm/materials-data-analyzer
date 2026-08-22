"""Public execution/progression boundary for the real-evidence recursive replay.

Callers provide a reconstructable public planning context and authoritative execution
artifacts.  They cannot provide a self-certified execution record.  This facade rebuilds
historical authorization/execution from request, registry, report and immutable ledger,
then delegates the already-hardened recursive scientific-state comparison internally.

The facade does not create scientific authority.  Authenticated transition edges remain
subject to the existing transition consumer and graph policy.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .kernel import ResearchLoopError
from .public_recursive_discrepancy import validate_public_recursive_discrepancy_report
from .public_recursive_planning import (
    build_public_recursive_discrepancy_planning_handoff,
    validate_public_recursive_planning_context,
)
from .recursive_authorized_execution_evidence import (
    build_authenticated_recursive_execution_record,
)
from .recursive_research_cycle_evidence import (
    _advance_recursive_cycle_after_verified_transition,
)
from .recursive_resource_budget import normalize_recursive_limits

PUBLIC_RECURSIVE_REDIAGNOSIS_SCHEMA_VERSION = "1.0"
PUBLIC_RECURSIVE_REDIAGNOSIS_POLICY_VERSION = "1.0"
PUBLIC_RECURSIVE_REPLAY_MANIFEST_SCHEMA_VERSION = "1.0"
PUBLIC_RECURSIVE_REPLAY_MANIFEST_POLICY_VERSION = "1.0"


class PublicRecursiveProgressionError(ResearchLoopError):
    """Raised when public recursive progression ancestry cannot be reconstructed."""


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
        raise PublicRecursiveProgressionError(
            "public recursive progression state must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PublicRecursiveProgressionError(f"{field} must be an object")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise PublicRecursiveProgressionError(f"{field} must be non-empty trimmed text")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise PublicRecursiveProgressionError(f"{field} must be lowercase SHA-256")
    return text


def _verified_sha(
    value: Mapping[str, Any],
    *,
    sha_field: str,
    field: str,
) -> str:
    snapshot = dict(_mapping(value, field))
    digest = _sha(snapshot.pop(sha_field, None), f"{field}.{sha_field}")
    if _canonical_sha256(snapshot) != digest:
        raise PublicRecursiveProgressionError(
            f"{field}.{sha_field} does not match canonical content"
        )
    return digest


def _same_limits(
    supplied: Mapping[str, Any] | None,
    expected: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = normalize_recursive_limits(supplied)
    if normalized != dict(expected):
        raise PublicRecursiveProgressionError(
            "recursive_limits differ from the validated planning ancestry"
        )
    return normalized


def advance_public_recursive_cycle_after_verified_transition(
    *,
    validated_planning_context: Mapping[str, Any],
    recursive_limits: Mapping[str, Any],
    execution_adapter_id: str,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
    action_report_path: str | Path,
    transition_bundle_root: str | Path,
    program_state: Mapping[str, Any],
    previous_progression: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Advance a cycle without any caller-authored execution-evidence parameter."""
    planning = validate_public_recursive_planning_context(validated_planning_context)
    checkpoint = _mapping(planning.get("recursive_checkpoint"), "recursive_checkpoint")
    expected_limits = _mapping(planning.get("recursive_limits"), "recursive_limits")
    _same_limits(recursive_limits, expected_limits)
    if checkpoint.get("checkpoint_status") != "explicit_authorization_required":
        raise PublicRecursiveProgressionError(
            "execution requires an authorization-open validated checkpoint"
        )
    match = _mapping(checkpoint.get("candidate_match"), "checkpoint.candidate_match")
    checkpoint_sha = _sha(checkpoint.get("checkpoint_sha256"), "checkpoint.checkpoint_sha256")
    action_id = _text(match.get("candidate_action_id"), "candidate_match.candidate_action_id")
    action_class = _text(
        match.get("candidate_action_class"),
        "candidate_match.candidate_action_class",
    )
    try:
        execution_record = build_authenticated_recursive_execution_record(
            source_checkpoint_sha256=checkpoint_sha,
            expected_candidate_action_id=action_id,
            expected_candidate_action_class=action_class,
            adapter_id=execution_adapter_id,
            repository_root=repository_root,
            research_run=research_run,
            action_registry_path=action_registry_path,
            request_path=request_path,
            action_report_path=action_report_path,
        )
    except ResearchLoopError as exc:
        raise PublicRecursiveProgressionError(
            "typed execution/authorization could not be reconstructed from immutable state"
        ) from exc

    inputs = _mapping(planning.get("validation_inputs"), "validation_inputs")
    fresh_plan = _mapping(inputs.get("fresh_plan"), "validation_inputs.fresh_plan")
    source_graph = _mapping(
        inputs.get("source_evaluated_graph"),
        "validation_inputs.source_evaluated_graph",
    )
    try:
        progression = _advance_recursive_cycle_after_verified_transition(
            authorization_checkpoint=checkpoint,
            verified_execution_record=execution_record,
            transition_bundle_root=transition_bundle_root,
            fresh_plan=fresh_plan,
            program_state=program_state,
            previous_progression=previous_progression,
            source_evaluated_graph=source_graph,
            require_authorization_provenance=True,
        )
    except ResearchLoopError as exc:
        raise PublicRecursiveProgressionError(
            "authenticated transition progression failed planning/execution/graph ancestry"
        ) from exc
    value = dict(progression)
    value["public_progression_binding"] = {
        "validated_planning_context_sha256": planning["context_sha256"],
        "validated_planning_artifact_sha256": planning[
            "validated_planning_artifact"
        ]["validated_checkpoint_sha256"],
        "recursive_limits": dict(expected_limits),
        "caller_authored_execution_record_accepted": False,
        "execution_record_reconstructed_from_immutable_state": True,
        "transition_bundle_independently_consumed": True,
        "scientific_authority_created_by_public_facade": False,
    }
    value.pop("progression_sha256", None)
    value["progression_sha256"] = _canonical_sha256(value)
    return value


def validate_public_recursive_progression(
    progression: Mapping[str, Any],
    *,
    validated_planning_context: Mapping[str, Any],
    recursive_limits: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the published wrapper and exact planning/limit ancestry."""
    digest = _verified_sha(
        progression,
        sha_field="progression_sha256",
        field="progression",
    )
    planning = validate_public_recursive_planning_context(validated_planning_context)
    expected_limits = _mapping(planning.get("recursive_limits"), "recursive_limits")
    _same_limits(recursive_limits, expected_limits)
    binding = _mapping(
        progression.get("public_progression_binding"),
        "progression.public_progression_binding",
    )
    if binding.get("validated_planning_context_sha256") != planning["context_sha256"]:
        raise PublicRecursiveProgressionError(
            "progression is bound to a different validated planning context"
        )
    if binding.get("recursive_limits") != dict(expected_limits):
        raise PublicRecursiveProgressionError(
            "progression recursive limits differ from validated planning context"
        )
    if binding.get("caller_authored_execution_record_accepted") is not False:
        raise PublicRecursiveProgressionError(
            "public progression cannot accept caller-authored execution evidence"
        )
    if binding.get("execution_record_reconstructed_from_immutable_state") is not True:
        raise PublicRecursiveProgressionError(
            "progression lacks immutable execution reconstruction provenance"
        )
    if binding.get("transition_bundle_independently_consumed") is not True:
        raise PublicRecursiveProgressionError(
            "progression lacks authenticated transition-consumer provenance"
        )
    checkpoint = _mapping(planning.get("recursive_checkpoint"), "recursive_checkpoint")
    ancestry = _mapping(progression.get("ancestry"), "progression.ancestry")
    if ancestry.get("authorization_checkpoint_sha256") != checkpoint.get("checkpoint_sha256"):
        raise PublicRecursiveProgressionError(
            "progression is bound to a different authorization checkpoint"
        )
    verified_execution = _mapping(
        progression.get("verified_execution"),
        "progression.verified_execution",
    )
    if verified_execution.get("preexecution_authorization_verification_sha256") is None:
        raise PublicRecursiveProgressionError(
            "progression omitted reconstructed pre-execution authorization provenance"
        )
    transition = _mapping(
        progression.get("verified_epistemic_transition"),
        "progression.verified_epistemic_transition",
    )
    if transition.get("current_transition_exact_provenance_authenticated") is not True:
        raise PublicRecursiveProgressionError(
            "progression omitted exact authenticated transition provenance"
        )
    return {
        "progression_sha256": digest,
        "progression_status": progression.get("progression_status"),
        "cycle_index": progression.get("cycle_index"),
        "validated_planning_context_sha256": planning["context_sha256"],
        "recursive_limits": dict(expected_limits),
        "caller_authored_execution_record_accepted": False,
    }


def complete_public_recursive_cycle_with_rediagnosis(
    *,
    validated_planning_context: Mapping[str, Any],
    progression: Mapping[str, Any],
    current_discrepancy_report: Mapping[str, Any],
    previous_discrepancy_report: Mapping[str, Any],
    evaluated_graph: Mapping[str, Any],
    recursive_limits: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate fresh re-diagnosis and emit the next planning-only handoff."""
    planning = validate_public_recursive_planning_context(validated_planning_context)
    progression_check = validate_public_recursive_progression(
        progression,
        validated_planning_context=validated_planning_context,
        recursive_limits=recursive_limits,
    )
    if progression.get("progression_status") != "re_diagnosis_required":
        raise PublicRecursiveProgressionError(
            "progression does not require a fresh discrepancy diagnosis"
        )
    inputs = _mapping(planning.get("validation_inputs"), "validation_inputs")
    source_report = _mapping(
        inputs.get("source_discrepancy_report"),
        "validation_inputs.source_discrepancy_report",
    )
    previous_sha = _verified_sha(
        previous_discrepancy_report,
        sha_field="report_sha256",
        field="previous_discrepancy_report",
    )
    if previous_sha != source_report.get("report_sha256") or dict(previous_discrepancy_report) != dict(source_report):
        raise PublicRecursiveProgressionError(
            "re-diagnosis previous report differs from validated planning source"
        )
    try:
        current_check = validate_public_recursive_discrepancy_report(
            current_discrepancy_report,
            evaluated_graph=evaluated_graph,
            previous_report=previous_discrepancy_report,
        )
    except ResearchLoopError as exc:
        raise PublicRecursiveProgressionError(
            "current discrepancy failed public physics/provenance reconstruction"
        ) from exc
    current_sha = _sha(
        current_check.get("report_sha256"),
        "validated_current_discrepancy_report.report_sha256",
    )
    if current_sha == previous_sha:
        raise PublicRecursiveProgressionError(
            "re-diagnosis cannot reuse the previous discrepancy report"
        )
    progression_target = _mapping(progression.get("target"), "progression.target")
    current_target = _mapping(current_discrepancy_report.get("target"), "current.target")
    previous_target = _mapping(previous_discrepancy_report.get("target"), "previous.target")
    for field in ("graph_id", "node_id", "node_type", "statement"):
        if current_target.get(field) != progression_target.get(field):
            raise PublicRecursiveProgressionError(
                f"current re-diagnosis target differs from authenticated progression: {field}"
            )
    for field in ("node_id", "node_type", "statement"):
        if current_target.get(field) != previous_target.get(field):
            raise PublicRecursiveProgressionError(
                f"stable recursive target identity changed: {field}"
            )
    next_handoff = build_public_recursive_discrepancy_planning_handoff(
        current_discrepancy_report,
        evaluated_graph=evaluated_graph,
        previous_discrepancy_report=previous_discrepancy_report,
    )
    result: dict[str, Any] = {
        "schema_version": PUBLIC_RECURSIVE_REDIAGNOSIS_SCHEMA_VERSION,
        "policy_version": PUBLIC_RECURSIVE_REDIAGNOSIS_POLICY_VERSION,
        "cycle_id": progression.get("cycle_id"),
        "cycle_index": progression.get("cycle_index"),
        "completion_status": "next_planning_handoff_ready",
        "target": dict(current_target),
        "ancestry": {
            "validated_planning_context_sha256": planning["context_sha256"],
            "progression_sha256": progression_check["progression_sha256"],
            "previous_discrepancy_report_sha256": previous_sha,
            "current_discrepancy_report_sha256": current_sha,
            "evaluated_graph_canonical_sha256": _canonical_sha256(evaluated_graph),
            "next_planning_handoff_sha256": next_handoff["handoff_sha256"],
        },
        "validated_rediagnosis": {
            "report_sha256": current_sha,
            "iteration_index": current_check.get("iteration_index"),
            "diagnosis_types": list(current_check.get("diagnosis_types", [])),
            "physics_hardening_verified": True,
            "provenance_hardening_verified": True,
            "scientific_status_changed": False,
            "automatic_execution_authorized": False,
        },
        "next_planning_handoff": next_handoff,
        "recursive_limits": dict(planning["recursive_limits"]),
        "autonomy_boundary": {
            "scientific_evidence_created": False,
            "epistemic_edge_created": False,
            "planner_candidate_created": False,
            "authorization_granted": False,
            "request_compiled": False,
            "execution_performed": False,
            "automatic_execution_authorized": False,
            "synthetic_empirical_measurement_created": False,
            "scientific_status_changed": False,
        },
    }
    result["completion_sha256"] = _canonical_sha256(result)
    return result


def build_public_recursive_replay_manifest(
    *,
    cycle1_planning_context: Mapping[str, Any],
    cycle1_progression: Mapping[str, Any],
    cycle1_completion: Mapping[str, Any],
    cycle2_planning_context: Mapping[str, Any],
    recursive_limits: Mapping[str, Any],
) -> dict[str, Any]:
    """Build machine-readable evidence for one two-cycle public composition replay."""
    c1 = validate_public_recursive_planning_context(cycle1_planning_context)
    c2 = validate_public_recursive_planning_context(cycle2_planning_context)
    limits = _same_limits(recursive_limits, _mapping(c1["recursive_limits"], "cycle1 limits"))
    if dict(c2["recursive_limits"]) != limits:
        raise PublicRecursiveProgressionError(
            "cycle2 recursive limits differ from cycle1 ancestry"
        )
    progression_sha = _verified_sha(
        cycle1_progression,
        sha_field="progression_sha256",
        field="cycle1_progression",
    )
    completion_sha = _verified_sha(
        cycle1_completion,
        sha_field="completion_sha256",
        field="cycle1_completion",
    )
    cp1 = _mapping(c1["recursive_checkpoint"], "cycle1 checkpoint")
    cp2 = _mapping(c2["recursive_checkpoint"], "cycle2 checkpoint")
    if cp1.get("cycle_index") != 1 or cp2.get("cycle_index") != 2:
        raise PublicRecursiveProgressionError(
            "public replay requires exact cycle indexes one then two"
        )
    if cp2.get("ancestry", {}).get("previous_checkpoint_sha256") != cp1.get("checkpoint_sha256"):
        raise PublicRecursiveProgressionError(
            "cycle2 checkpoint does not descend from exact cycle1 checkpoint"
        )
    p1 = _mapping(c1["validation_inputs"], "cycle1 inputs")
    p2 = _mapping(c2["validation_inputs"], "cycle2 inputs")
    plan1 = _mapping(p1.get("fresh_plan"), "cycle1 fresh_plan")
    plan2 = _mapping(p2.get("fresh_plan"), "cycle2 fresh_plan")
    plan1_sha = _sha(plan1.get("plan_sha256"), "cycle1 plan_sha256")
    plan2_sha = _sha(plan2.get("plan_sha256"), "cycle2 plan_sha256")
    if plan1_sha == plan2_sha:
        raise PublicRecursiveProgressionError("cycle2 stale-plan reuse detected")
    science = _mapping(
        cycle1_progression.get("scientific_state_comparison"),
        "scientific_state_comparison",
    )
    base = _mapping(science.get("base"), "scientific_state_comparison.base")
    successor = _mapping(science.get("successor"), "scientific_state_comparison.successor")
    if base.get("fingerprint_sha256") != successor.get("fingerprint_sha256"):
        raise PublicRecursiveProgressionError(
            "diagnostic transition unexpectedly changed verified target scientific state"
        )
    if science.get("graph_version_bookkeeping_counts_as_new_information") is not False:
        raise PublicRecursiveProgressionError(
            "graph-version churn was incorrectly counted as scientific information"
        )
    result: dict[str, Any] = {
        "schema_version": PUBLIC_RECURSIVE_REPLAY_MANIFEST_SCHEMA_VERSION,
        "policy_version": PUBLIC_RECURSIVE_REPLAY_MANIFEST_POLICY_VERSION,
        "acceptance_status": "public_api_two_cycle_replay_reached_bounded_second_cycle",
        "cycle1": {
            "planning_context_sha256": c1["context_sha256"],
            "validated_planning_artifact_sha256": c1["validated_planning_artifact"]["validated_checkpoint_sha256"],
            "recursive_checkpoint_sha256": cp1["checkpoint_sha256"],
            "fresh_plan_sha256": plan1_sha,
            "progression_sha256": progression_sha,
            "completion_sha256": completion_sha,
            "progression_status": cycle1_progression.get("progression_status"),
        },
        "cycle2": {
            "planning_context_sha256": c2["context_sha256"],
            "validated_planning_artifact_sha256": c2["validated_planning_artifact"]["validated_checkpoint_sha256"],
            "recursive_checkpoint_sha256": cp2["checkpoint_sha256"],
            "fresh_plan_sha256": plan2_sha,
            "checkpoint_status": cp2.get("checkpoint_status"),
            "predecessor_checkpoint_sha256": cp2.get("ancestry", {}).get("previous_checkpoint_sha256"),
        },
        "recursive_limits": limits,
        "scientific_state": {
            "cycle1_target_base_fingerprint_sha256": base.get("fingerprint_sha256"),
            "cycle1_target_successor_fingerprint_sha256": successor.get("fingerprint_sha256"),
            "diagnostic_transition_changed_verified_target_state": False,
            "graph_version_churn_counted_as_scientific_information": False,
        },
        "scientific_boundary": {
            "repository_owned_audited_heat_solver_used": True,
            "immutable_heat_execution_ledger_replayed": True,
            "pinned_heat_domain_verifier_used": True,
            "synthetic_empirical_measurement_used": False,
            "caller_authored_execution_record_used": False,
            "empirical_material_or_process_validation_established": False,
            "hypothesis_truth_established": False,
            "positive_scientific_closeout_granted": False,
            "physical_experiment_executed": False,
        },
    }
    result["manifest_sha256"] = _canonical_sha256(result)
    return result


advance_recursive_cycle_after_verified_transition = advance_public_recursive_cycle_after_verified_transition
complete_recursive_cycle_with_rediagnosis = complete_public_recursive_cycle_with_rediagnosis


__all__ = [
    "PUBLIC_RECURSIVE_REDIAGNOSIS_POLICY_VERSION",
    "PUBLIC_RECURSIVE_REDIAGNOSIS_SCHEMA_VERSION",
    "PUBLIC_RECURSIVE_REPLAY_MANIFEST_POLICY_VERSION",
    "PUBLIC_RECURSIVE_REPLAY_MANIFEST_SCHEMA_VERSION",
    "PublicRecursiveProgressionError",
    "advance_public_recursive_cycle_after_verified_transition",
    "advance_recursive_cycle_after_verified_transition",
    "build_public_recursive_replay_manifest",
    "complete_public_recursive_cycle_with_rediagnosis",
    "complete_recursive_cycle_with_rediagnosis",
    "validate_public_recursive_progression",
]
