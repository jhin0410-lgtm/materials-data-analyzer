"""Hardened post-execution progression for bounded recursive research cycles.

The public path reconstructs validated planning, independently reconstructs typed execution
(including historical authorization), re-authenticates the exact transition bundle,
requires its exact base scientific graph to match the planning source, and compares
status-affecting scientific state rather than graph-version bookkeeping.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import recursive_research_cycle_evidence_legacy as _legacy
from .authenticated_transition_consumer import (
    AuthenticatedTransitionConsumerError,
    authenticate_transition_bundle,
)
from .epistemic_graph import EpistemicGraphError, evaluate_epistemic_graph
from .hypothesis_portfolio import HypothesisPortfolioError, build_hypothesis_portfolio
from .kernel import ResearchLoopError
from .recursive_authorized_execution_evidence import (
    RECURSIVE_EXECUTION_EVIDENCE_POLICY_VERSION,
    build_authenticated_recursive_execution_record,
)
from .recursive_scientific_state import (
    evaluated_graph_scientific_identity_sha256,
    target_scientific_state_fingerprint,
)
from .validated_recursive_cycle_planning import (
    validate_validated_recursive_planning_checkpoint,
)

RECURSIVE_EVIDENCE_POLICY_VERSION = _legacy.RECURSIVE_EVIDENCE_POLICY_VERSION
VERIFIED_EXECUTION_RECORD_SCHEMA_VERSION = _legacy.VERIFIED_EXECUTION_RECORD_SCHEMA_VERSION
RecursiveResearchEvidenceError = _legacy.RecursiveResearchEvidenceError
_mapping = _legacy._mapping
_sequence = _legacy._sequence
_text = _legacy._text
_sha = _legacy._sha
_embedded_sha = _legacy._embedded_sha
_checkpoint = _legacy._checkpoint
_fresh_plan = _legacy._fresh_plan
_read_bound_json = _legacy._read_bound_json
_target_assessment = _legacy._target_assessment


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


def _verified_execution_record(
    value: Mapping[str, Any],
    *,
    checkpoint_sha: str,
    expected_action_id: str,
    expected_action_type: str,
    require_authorization_provenance: bool,
) -> tuple[str, dict[str, Any]]:
    if not require_authorization_provenance:
        return _legacy._execution_record(
            value,
            checkpoint_sha=checkpoint_sha,
            expected_action_id=expected_action_id,
            expected_action_type=expected_action_type,
        )
    if (
        value.get("schema_version") != VERIFIED_EXECUTION_RECORD_SCHEMA_VERSION
        or value.get("policy_version") != RECURSIVE_EXECUTION_EVIDENCE_POLICY_VERSION
    ):
        raise RecursiveResearchEvidenceError(
            "unsupported verified execution record schema/policy version"
        )
    digest = _embedded_sha(
        value,
        field="verified_execution_record",
        sha_field="verification_record_sha256",
    )
    if value.get("source_checkpoint_sha256") != checkpoint_sha:
        raise RecursiveResearchEvidenceError(
            "verified execution record is bound to a different recursive checkpoint"
        )
    if (
        value.get("authorization_status")
        != "preexecution_authorization_deterministically_reconstructed"
    ):
        raise RecursiveResearchEvidenceError(
            "execution record lacks deterministic pre-execution authorization reconstruction"
        )
    if value.get("independent_verification_status") != "verified_by_existing_chain":
        raise RecursiveResearchEvidenceError(
            "execution record is not independently verified by the existing chain"
        )
    action_id = _text(value.get("action_id"), "verified_execution_record.action_id")
    action_type = _text(
        value.get("action_type"), "verified_execution_record.action_type"
    )
    action_version = _text(
        value.get("action_version"), "verified_execution_record.action_version"
    )
    if action_id != expected_action_id or action_type != expected_action_type:
        raise RecursiveResearchEvidenceError(
            "verified execution identity differs from planner-selected checkpoint action"
        )
    for field in ("request_sha256", "registry_sha256", "result_sha256"):
        _sha(value.get(field), f"verified_execution_record.{field}")
    outcome = _text(
        value.get("execution_outcome"), "verified_execution_record.execution_outcome"
    )
    success = value.get("execution_success")
    if (
        outcome not in {"completed", "rejected", "failed"}
        or not isinstance(success, bool)
        or success != (outcome == "completed")
    ):
        raise RecursiveResearchEvidenceError(
            "verified execution outcome/success contract drifted"
        )
    if value.get("scientific_evidence_upgraded") is not False:
        raise RecursiveResearchEvidenceError(
            "execution verification cannot itself upgrade scientific evidence"
        )
    concrete = _mapping(
        value.get("concrete_execution"), "verified_execution_record.concrete_execution"
    )
    authorization = _mapping(
        concrete.get("preexecution_authorization"),
        "verified_execution_record.concrete_execution.preexecution_authorization",
    )
    auth_sha = _embedded_sha(
        authorization,
        field="preexecution_authorization",
        sha_field="verification_sha256",
    )
    if (
        authorization.get("verification_status")
        != "preexecution_authorization_deterministically_reconstructed"
        or authorization.get("action_id") != action_id
        or authorization.get("candidate_action_class") != action_type
        or authorization.get("execution_registry_verified") is not True
        or authorization.get("selected_action_binding_verified") is not True
        or authorization.get("budget_verified") is not True
        or authorization.get("execution_performed_by_replay") is not False
    ):
        raise RecursiveResearchEvidenceError(
            "pre-execution authorization provenance is incomplete or inconsistent"
        )
    return digest, {
        "action_id": action_id,
        "action_type": action_type,
        "action_version": action_version,
        "request_sha256": value["request_sha256"],
        "registry_sha256": value["registry_sha256"],
        "result_sha256": value["result_sha256"],
        "execution_outcome": outcome,
        "execution_success": success,
        "preexecution_authorization_verification_sha256": auth_sha,
    }


def _authenticated_transition(
    *,
    bundle_root: str | Path,
    execution: Mapping[str, Any],
    source_target: Mapping[str, Any],
    program_state: Mapping[str, Any],
    source_evaluated_graph: Mapping[str, Any] | None,
) -> tuple[
    str,
    dict[str, Any],
    dict[str, Any],
    str,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    try:
        report = authenticate_transition_bundle(bundle_root)
    except (AuthenticatedTransitionConsumerError, OSError, ValueError) as exc:
        raise RecursiveResearchEvidenceError(
            "authenticated transition bundle failed independent consumer verification"
        ) from exc
    if report.get("current_transition_exact_provenance_authenticated") is not True:
        raise RecursiveResearchEvidenceError(
            "authenticated transition consumer did not establish exact provenance"
        )
    root = Path(
        _text(report.get("bundle_root"), "transition_consumer.bundle_root")
    ).resolve(strict=True)
    base_graph = _read_bound_json(
        root,
        report.get("base_graph_binding"),
        field="transition_consumer.base_graph_binding",
    )
    proposal = _read_bound_json(
        root,
        report.get("proposal_binding"),
        field="transition_consumer.proposal_binding",
    )
    graph = _read_bound_json(
        root,
        report.get("graph_binding"),
        field="transition_consumer.graph_binding",
    )
    source_action = _mapping(
        proposal.get("source_action"), "transition proposal.source_action"
    )
    if (
        source_action.get("action_id") != execution["action_id"]
        or source_action.get("action_class") != execution["action_type"]
        or source_action.get("action_version") != execution["action_version"]
    ):
        raise RecursiveResearchEvidenceError(
            "authenticated transition proposal action identity differs from verified execution"
        )
    if (
        proposal.get("base_graph_id") != source_target["graph_id"]
        or proposal.get("target_node_id") != source_target["node_id"]
        or report.get("target_node_id") != source_target["node_id"]
    ):
        raise RecursiveResearchEvidenceError(
            "authenticated transition base/target differs from recursive checkpoint"
        )
    if report.get("transition_id") != proposal.get("transition_id"):
        raise RecursiveResearchEvidenceError(
            "transition consumer transition_id differs from exact proposal"
        )
    successor_graph_id = _text(
        proposal.get("new_graph_id"), "transition proposal.new_graph_id"
    )
    if graph.get("graph_id") != successor_graph_id:
        raise RecursiveResearchEvidenceError(
            "authenticated successor graph_id differs from exact transition proposal"
        )
    result_node = _mapping(
        proposal.get("result_node"), "transition proposal.result_node"
    )
    result_bindings = _sequence(
        result_node.get("artifact_bindings"),
        "transition proposal.result_node.artifact_bindings",
    )
    result_shas = {
        item.get("sha256")
        for item in result_bindings
        if isinstance(item, Mapping) and isinstance(item.get("sha256"), str)
    }
    if execution["result_sha256"] not in result_shas:
        raise RecursiveResearchEvidenceError(
            "verified execution result SHA is absent from transition result artifacts"
        )
    try:
        base_evaluated = evaluate_epistemic_graph(
            base_graph,
            program_state=program_state,
            artifact_root=root,
        )
        successor_evaluated = evaluate_epistemic_graph(
            graph,
            program_state=program_state,
            artifact_root=root,
        )
    except (EpistemicGraphError, OSError, ValueError) as exc:
        raise RecursiveResearchEvidenceError(
            "authenticated base/successor graphs could not be independently evaluated"
        ) from exc
    base_identity = evaluated_graph_scientific_identity_sha256(base_evaluated)
    planning_identity = None
    if source_evaluated_graph is not None:
        planning_identity = evaluated_graph_scientific_identity_sha256(
            source_evaluated_graph
        )
        if planning_identity != base_identity:
            raise RecursiveResearchEvidenceError(
                "authenticated transition base graph differs from the exact planning source graph"
            )
    base_state = target_scientific_state_fingerprint(
        base_evaluated,
        target_node_id=source_target["node_id"],
    )
    successor_state = target_scientific_state_fingerprint(
        successor_evaluated,
        target_node_id=source_target["node_id"],
    )
    current_target, assessment = _target_assessment(
        successor_evaluated,
        source_target=source_target,
        successor_graph_id=successor_graph_id,
    )
    report_sha = _canonical_sha256(report)
    graph_binding = _mapping(
        report.get("graph_binding"), "transition_consumer.graph_binding"
    )
    base_binding = _mapping(
        report.get("base_graph_binding"), "transition_consumer.base_graph_binding"
    )
    transition = {
        "transition_id": report["transition_id"],
        "base_graph_id": proposal["base_graph_id"],
        "new_graph_id": successor_graph_id,
        "target_node_id": report["target_node_id"],
        "inference_edge_id": report.get("inference_edge_id"),
        "relation": report.get("relation"),
        "inference_scope": report.get("inference_scope"),
        "authenticated_base_graph_sha256": _sha(
            base_binding.get("sha256"),
            "transition_consumer.base_graph_binding.sha256",
        ),
        "authenticated_successor_graph_sha256": _sha(
            graph_binding.get("sha256"),
            "transition_consumer.graph_binding.sha256",
        ),
        "authenticated_base_graph_scientific_identity_sha256": base_identity,
        "planning_source_graph_scientific_identity_sha256": planning_identity,
        "planning_source_graph_binding_verified": source_evaluated_graph is not None,
        "base_target_scientific_state_sha256": base_state["fingerprint_sha256"],
        "successor_target_scientific_state_sha256": successor_state[
            "fingerprint_sha256"
        ],
        "transition_consumer_report_sha256": report_sha,
        "current_transition_exact_provenance_authenticated": True,
        "execution_completion_treated_as_scientific_support": False,
        "scientific_authority_applied_by_recursive_controller": False,
    }
    return (
        report_sha,
        transition,
        successor_evaluated,
        _canonical_sha256(successor_evaluated),
        current_target,
        assessment,
        base_state,
        successor_state,
    )


def _authoritative_portfolio(
    *,
    evaluated_graph: Mapping[str, Any],
    fresh_plan: Mapping[str, Any],
    target: Mapping[str, Any],
    assessment: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str | None, dict[str, Any] | None]:
    if target.get("node_type") != "hypothesis":
        return None, None, None
    try:
        portfolio = build_hypothesis_portfolio(
            evaluated_graph,
            plan=fresh_plan,
            previous_portfolio=None,
        )
    except HypothesisPortfolioError as exc:
        raise RecursiveResearchEvidenceError(
            "authoritative hypothesis portfolio refresh failed"
        ) from exc
    digest = _sha(
        portfolio.get("portfolio_sha256"),
        "authoritative_hypothesis_portfolio.portfolio_sha256",
    )
    records = _sequence(
        portfolio.get("hypotheses"), "hypothesis_portfolio.hypotheses"
    )
    matches = [
        item
        for item in records
        if isinstance(item, Mapping)
        and item.get("hypothesis_id") == target.get("node_id")
    ]
    if len(matches) != 1:
        raise RecursiveResearchEvidenceError(
            "target hypothesis must resolve to exactly one authoritative portfolio record"
        )
    record = dict(matches[0])
    if (
        record.get("statement") != target.get("statement")
        or record.get("epistemic_status") != assessment.get("status")
    ):
        raise RecursiveResearchEvidenceError(
            "authoritative portfolio target state differs from evaluated graph"
        )
    return portfolio, digest, record


def _advance_recursive_cycle_after_verified_transition(
    *,
    authorization_checkpoint: Mapping[str, Any],
    verified_execution_record: Mapping[str, Any],
    transition_bundle_root: str | Path,
    fresh_plan: Mapping[str, Any],
    program_state: Mapping[str, Any],
    previous_progression: Mapping[str, Any] | None = None,
    source_evaluated_graph: Mapping[str, Any] | None = None,
    require_authorization_provenance: bool = False,
) -> dict[str, Any]:
    checkpoint = _mapping(authorization_checkpoint, "authorization_checkpoint")
    (
        checkpoint_sha,
        source_target,
        expected_action_id,
        expected_action_type,
        expected_plan_sha,
    ) = _checkpoint(checkpoint)
    cycle_index = checkpoint.get("cycle_index")
    if isinstance(cycle_index, bool) or not isinstance(cycle_index, int) or cycle_index < 1:
        raise RecursiveResearchEvidenceError(
            "checkpoint.cycle_index must be an integer >= 1"
        )
    checkpoint_ancestry = _mapping(
        checkpoint.get("ancestry"), "checkpoint.ancestry"
    )
    previous_checkpoint_sha = checkpoint_ancestry.get("previous_checkpoint_sha256")
    previous_sha = None
    if cycle_index == 1:
        if previous_checkpoint_sha is not None or previous_progression is not None:
            raise RecursiveResearchEvidenceError(
                "cycle-one checkpoint/progression cannot carry predecessor ancestry"
            )
    else:
        expected_previous_checkpoint_sha = _sha(
            previous_checkpoint_sha,
            "checkpoint.ancestry.previous_checkpoint_sha256",
        )
        if previous_progression is None:
            raise RecursiveResearchEvidenceError(
                "successor recursive cycle requires the exact previous progression"
            )
        previous = _mapping(previous_progression, "previous_progression")
        if (
            previous.get("schema_version") != _legacy.RECURSIVE_CYCLE_SCHEMA_VERSION
            or previous.get("policy_version") != RECURSIVE_EVIDENCE_POLICY_VERSION
        ):
            raise RecursiveResearchEvidenceError(
                "previous progression schema/policy version drifted"
            )
        previous_sha = _embedded_sha(
            previous,
            field="previous_progression",
            sha_field="progression_sha256",
        )
        if previous.get("cycle_index") != cycle_index - 1:
            raise RecursiveResearchEvidenceError(
                "previous progression is not the immediately preceding cycle"
            )
        previous_target = _mapping(
            previous.get("target"), "previous_progression.target"
        )
        for field in ("graph_id", "node_id", "node_type", "statement"):
            if previous_target.get(field) != source_target.get(field):
                raise RecursiveResearchEvidenceError(
                    "previous progression does not terminate at current checkpoint "
                    f"target: {field}"
                )
        prior_ancestry = _mapping(
            previous.get("ancestry"), "previous_progression.ancestry"
        )
        if (
            prior_ancestry.get("authorization_checkpoint_sha256")
            != expected_previous_checkpoint_sha
        ):
            raise RecursiveResearchEvidenceError(
                "previous progression is not bound to the checkpoint predecessor"
            )
    plan, plan_sha = _fresh_plan(
        _mapping(fresh_plan, "fresh_plan"),
        expected_sha=expected_plan_sha,
    )
    execution_sha, execution = _verified_execution_record(
        _mapping(verified_execution_record, "verified_execution_record"),
        checkpoint_sha=checkpoint_sha,
        expected_action_id=expected_action_id,
        expected_action_type=expected_action_type,
        require_authorization_provenance=require_authorization_provenance,
    )
    (
        transition_report_sha,
        transition,
        evaluated_graph,
        graph_sha,
        current_target,
        assessment,
        base_state,
        successor_state,
    ) = _authenticated_transition(
        bundle_root=transition_bundle_root,
        execution=execution,
        source_target=source_target,
        program_state=_mapping(program_state, "program_state"),
        source_evaluated_graph=source_evaluated_graph,
    )
    portfolio, portfolio_sha, portfolio_state = _authoritative_portfolio(
        evaluated_graph=evaluated_graph,
        fresh_plan=plan,
        target=current_target,
        assessment=assessment,
    )
    no_new = (
        cycle_index > 1
        and base_state["fingerprint_sha256"]
        == successor_state["fingerprint_sha256"]
    )
    portfolio_state_name = (
        portfolio_state.get("portfolio_state") if portfolio_state is not None else None
    )
    assessment_status = assessment.get("status")
    if portfolio_state_name == "retired_falsified_within_verified_scope":
        status, re_diag, reason = (
            "bounded_stop_hypothesis_retired",
            False,
            "Target hypothesis remains retired/falsified within verified scope.",
        )
    elif (
        current_target.get("node_type") != "hypothesis"
        and assessment_status == "falsified_within_verified_scope"
    ):
        status, re_diag, reason = (
            "bounded_stop_target_falsified",
            False,
            "Target claim/conclusion is falsified within verified scope.",
        )
    elif portfolio_state_name == "positive_closeout_required" or (
        current_target.get("node_type") != "hypothesis"
        and assessment_status == "provisionally_supported"
    ):
        status, re_diag, reason = (
            "bounded_stop_domain_closeout_required",
            False,
            "Positive scientific closeout requires separate domain review.",
        )
    elif no_new:
        status, re_diag, reason = (
            "bounded_stop_no_new_scientific_information",
            False,
            "Successor execution added only diagnostic/version bookkeeping; the target's "
            "status-affecting verified scientific state did not change.",
        )
    else:
        status, re_diag, reason = "re_diagnosis_required", True, None
    result = {
        "schema_version": _legacy.RECURSIVE_CYCLE_SCHEMA_VERSION,
        "policy_version": RECURSIVE_EVIDENCE_POLICY_VERSION,
        "cycle_id": checkpoint.get("cycle_id"),
        "cycle_index": cycle_index,
        "progression_status": status,
        "source_target": dict(source_target),
        "target": dict(current_target),
        "ancestry": {
            "previous_progression_sha256": previous_sha,
            "authorization_checkpoint_sha256": checkpoint_sha,
            "fresh_plan_sha256": plan_sha,
            "verified_execution_record_sha256": execution_sha,
            "authenticated_transition_consumer_report_sha256": transition_report_sha,
            "authenticated_base_graph_sha256": transition[
                "authenticated_base_graph_sha256"
            ],
            "authenticated_successor_graph_sha256": transition[
                "authenticated_successor_graph_sha256"
            ],
            "evaluated_graph_canonical_sha256": graph_sha,
            "hypothesis_portfolio_sha256": portfolio_sha,
        },
        "verified_execution": execution,
        "verified_epistemic_transition": transition,
        "target_epistemic_assessment": dict(assessment),
        "hypothesis_portfolio": portfolio,
        "target_hypothesis_portfolio_state": portfolio_state,
        "scientific_state_comparison": {
            "base": base_state,
            "successor": successor_state,
            "no_new_scientific_information": no_new,
            "graph_version_bookkeeping_counts_as_new_information": False,
            "diagnostic_only_edges_count_as_verified_state_change": False,
        },
        "re_diagnosis": {
            "required": re_diag,
            "performed": False,
            "previous_discrepancy_report_reuse_authorized": False,
        },
        "bounded_stop": {
            "stopped": not re_diag,
            "reason": reason,
        },
        "autonomy_boundary": {
            "verification_authority_created_by_controller": False,
            "authorization_created_by_controller": False,
            "execution_performed_by_controller": False,
            "epistemic_interpretation_created_by_controller": False,
            "epistemic_edge_created_by_controller": False,
            "hypothesis_state_invented_by_controller": False,
            "automatic_execution_authorized": False,
            "scientific_status_changed_by_controller": False,
        },
    }
    result["progression_sha256"] = _canonical_sha256(result)
    return result


def advance_recursive_cycle_after_verified_transition(
    *,
    validated_planning_artifact: Mapping[str, Any],
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
    try:
        planning_verification = validate_validated_recursive_planning_checkpoint(
            validated_planning_artifact,
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
            recursive_limits=recursive_limits,
        )
    except ResearchLoopError as exc:
        raise RecursiveResearchEvidenceError(
            "post-execution progression requires the exact validated planning artifact"
        ) from exc
    checkpoint = _mapping(
        planning_verification.get("recursive_checkpoint"),
        "validated_planning_artifact.recursive_checkpoint",
    )
    (
        checkpoint_sha,
        _source_target,
        expected_action_id,
        expected_action_class,
        _expected_plan_sha,
    ) = _checkpoint(checkpoint)
    try:
        execution_record = build_authenticated_recursive_execution_record(
            source_checkpoint_sha256=checkpoint_sha,
            expected_candidate_action_id=expected_action_id,
            expected_candidate_action_class=expected_action_class,
            adapter_id=execution_adapter_id,
            repository_root=repository_root,
            research_run=research_run,
            action_registry_path=action_registry_path,
            request_path=request_path,
            action_report_path=action_report_path,
        )
    except ResearchLoopError as exc:
        raise RecursiveResearchEvidenceError(
            "typed execution/authorization could not be independently reconstructed from "
            "exact request/registry/report/immutable-ledger state"
        ) from exc
    return _advance_recursive_cycle_after_verified_transition(
        authorization_checkpoint=checkpoint,
        verified_execution_record=execution_record,
        transition_bundle_root=transition_bundle_root,
        fresh_plan=fresh_plan,
        program_state=program_state,
        previous_progression=previous_progression,
        source_evaluated_graph=source_evaluated_graph,
        require_authorization_provenance=True,
    )


__all__ = [
    "RECURSIVE_EVIDENCE_POLICY_VERSION",
    "VERIFIED_EXECUTION_RECORD_SCHEMA_VERSION",
    "RecursiveResearchEvidenceError",
    "advance_recursive_cycle_after_verified_transition",
]
