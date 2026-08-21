"""Post-execution progression for bounded recursive research-cycle checkpoints.

The controller does not independently establish authorization, executor correctness, or
domain-verifier authority. Those remain the responsibility of the existing typed
authorization/execution and authenticated epistemic-transition layers. This module
binds those verified outputs to the planner-owned action, evaluated graph, and persistent
hypothesis portfolio before deciding whether the recursive cycle may re-diagnose or stop.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .authenticated_transition_consumer import (
    AuthenticatedTransitionConsumerError,
    authenticate_transition_bundle,
)
from .autonomous_inquiry import AUTONOMOUS_INQUIRY_POLICY_VERSION
from .epistemic_graph import EpistemicGraphError, evaluate_epistemic_graph
from .hypothesis_portfolio import (
    HypothesisPortfolioError,
    build_hypothesis_portfolio,
)
from .kernel import ResearchLoopError
from .recursive_research_cycle_controller import (
    RECURSIVE_CYCLE_POLICY_VERSION,
    RECURSIVE_CYCLE_SCHEMA_VERSION,
)

RECURSIVE_EVIDENCE_POLICY_VERSION = "1.0"
VERIFIED_EXECUTION_RECORD_SCHEMA_VERSION = "1.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STATUS_TO_PORTFOLIO = {
    "inconclusive": (
        "active_discrimination_required",
        "continue_discriminating_research",
    ),
    "provisionally_supported": (
        "positive_closeout_required",
        "seek_domain_closeout_no_auto_promotion",
    ),
    "contested": (
        "contested_discrimination_required",
        "prioritize_discriminating_work",
    ),
    "contradicted_within_verified_scope": (
        "challenge_or_retirement_review",
        "seek_replication_or_scope_review",
    ),
    "falsified_within_verified_scope": (
        "retired_falsified_within_verified_scope",
        "do_not_repeat_without_new_hypothesis_identity",
    ),
}


class RecursiveResearchEvidenceError(ResearchLoopError):
    """Raised when verified-result / graph / portfolio ancestry cannot be preserved."""


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RecursiveResearchEvidenceError(
            "recursive evidence state must be canonical-JSON serializable"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RecursiveResearchEvidenceError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise RecursiveResearchEvidenceError(f"{field} must be a sequence")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise RecursiveResearchEvidenceError(f"{field} must be non-empty trimmed text")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if _SHA256.fullmatch(text) is None:
        raise RecursiveResearchEvidenceError(f"{field} must be lowercase SHA-256")
    return text


def _embedded_sha(value: Mapping[str, Any], *, field: str, sha_field: str) -> str:
    snapshot = dict(value)
    expected = _sha(snapshot.pop(sha_field, None), f"{field}.{sha_field}")
    actual = _canonical_sha256(snapshot)
    if actual != expected:
        raise RecursiveResearchEvidenceError(
            f"{field}.{sha_field} does not match canonical content"
        )
    return expected


def _checkpoint(
    value: Mapping[str, Any],
) -> tuple[str, dict[str, Any], str, str, str]:
    if value.get("schema_version") != RECURSIVE_CYCLE_SCHEMA_VERSION:
        raise RecursiveResearchEvidenceError(
            "unsupported recursive checkpoint schema_version"
        )
    if value.get("policy_version") != RECURSIVE_CYCLE_POLICY_VERSION:
        raise RecursiveResearchEvidenceError(
            "unsupported recursive checkpoint policy_version"
        )
    digest = _embedded_sha(
        value,
        field="checkpoint",
        sha_field="checkpoint_sha256",
    )
    if value.get("checkpoint_status") != "explicit_authorization_required":
        raise RecursiveResearchEvidenceError(
            "post-execution progression requires an explicit_authorization_required checkpoint"
        )
    boundary = _mapping(value.get("autonomy_boundary"), "checkpoint.autonomy_boundary")
    if boundary.get("authorization_granted") is not False:
        raise RecursiveResearchEvidenceError(
            "planning checkpoint must not have self-granted authorization"
        )
    target = dict(_mapping(value.get("target"), "checkpoint.target"))
    for field in ("graph_id", "node_id", "node_type", "statement"):
        _text(target.get(field), f"checkpoint.target.{field}")

    candidate = _mapping(value.get("candidate_match"), "checkpoint.candidate_match")
    action_id = _text(
        candidate.get("candidate_action_id"),
        "checkpoint.candidate_match.candidate_action_id",
    )
    action_class = _text(
        candidate.get("candidate_action_class"),
        "checkpoint.candidate_match.candidate_action_class",
    )
    planner_state = _mapping(
        value.get("fresh_planner_state"), "checkpoint.fresh_planner_state"
    )
    if planner_state.get("selected_candidate_id") != action_id:
        raise RecursiveResearchEvidenceError(
            "checkpoint selected candidate and candidate-match action_id diverge"
        )
    ancestry = _mapping(value.get("ancestry"), "checkpoint.ancestry")
    plan_sha = _sha(
        ancestry.get("fresh_plan_sha256"),
        "checkpoint.ancestry.fresh_plan_sha256",
    )
    return digest, target, action_id, action_class, plan_sha


def _execution_record(
    value: Mapping[str, Any],
    *,
    checkpoint_sha: str,
    expected_action_id: str,
    expected_action_type: str,
) -> tuple[str, dict[str, Any]]:
    if value.get("schema_version") != VERIFIED_EXECUTION_RECORD_SCHEMA_VERSION:
        raise RecursiveResearchEvidenceError(
            "unsupported verified execution record schema_version"
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
        != "explicit_request_authorized_by_existing_chain"
    ):
        raise RecursiveResearchEvidenceError(
            "execution record does not attest existing-chain explicit authorization"
        )
    if value.get("independent_verification_status") != "verified_by_existing_chain":
        raise RecursiveResearchEvidenceError(
            "execution record is not marked as independently verified by the existing chain"
        )
    action_id = _text(value.get("action_id"), "verified_execution_record.action_id")
    action_type = _text(value.get("action_type"), "verified_execution_record.action_type")
    action_version = _text(
        value.get("action_version"), "verified_execution_record.action_version"
    )
    if action_id != expected_action_id:
        raise RecursiveResearchEvidenceError(
            "verified execution action_id does not match the planner-selected checkpoint action"
        )
    if action_type != expected_action_type:
        raise RecursiveResearchEvidenceError(
            "verified execution action_type does not match the checkpoint candidate action class"
        )
    for field in ("request_sha256", "registry_sha256", "result_sha256"):
        _sha(value.get(field), f"verified_execution_record.{field}")
    outcome = _text(
        value.get("execution_outcome"),
        "verified_execution_record.execution_outcome",
    )
    if outcome not in {"completed", "rejected", "failed"}:
        raise RecursiveResearchEvidenceError("unsupported verified execution outcome")
    success = value.get("execution_success")
    if not isinstance(success, bool):
        raise RecursiveResearchEvidenceError(
            "verified_execution_record.execution_success must be boolean"
        )
    if success != (outcome == "completed"):
        raise RecursiveResearchEvidenceError(
            "rejected/failed execution cannot be represented as verified execution success"
        )
    if value.get("scientific_evidence_upgraded") is not False:
        raise RecursiveResearchEvidenceError(
            "execution verification cannot itself upgrade scientific evidence"
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
    }


def _fresh_plan(value: Mapping[str, Any], *, expected_sha: str) -> tuple[dict[str, Any], str]:
    plan = dict(_mapping(value, "fresh_plan"))
    if plan.get("schema_version") != "1.0":
        raise RecursiveResearchEvidenceError("unsupported fresh plan schema_version")
    if plan.get("policy_version") != AUTONOMOUS_INQUIRY_POLICY_VERSION:
        raise RecursiveResearchEvidenceError("unsupported fresh plan policy_version")
    digest = _embedded_sha(plan, field="fresh_plan", sha_field="plan_sha256")
    if digest != expected_sha:
        raise RecursiveResearchEvidenceError(
            "fresh plan is not the exact plan bound into the authorization checkpoint"
        )
    return plan, digest


def _read_bound_json(
    bundle_root: Path,
    binding_value: object,
    *,
    field: str,
) -> dict[str, Any]:
    binding = _mapping(binding_value, field)
    path_text = _text(binding.get("path"), f"{field}.path")
    expected_sha = _sha(binding.get("sha256"), f"{field}.sha256")
    candidate = bundle_root / path_text
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(bundle_root)
    except (OSError, ValueError) as exc:
        raise RecursiveResearchEvidenceError(
            f"{field} escaped or disappeared after authenticated transition verification"
        ) from exc
    if not resolved.is_file():
        raise RecursiveResearchEvidenceError(f"{field} must remain a regular file")
    raw = resolved.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise RecursiveResearchEvidenceError(
            f"{field} changed after authenticated transition verification"
        )
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecursiveResearchEvidenceError(f"{field} is not valid UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise RecursiveResearchEvidenceError(f"{field} root must be an object")
    return parsed


def _target_assessment(
    evaluated_graph: Mapping[str, Any],
    *,
    source_target: Mapping[str, Any],
    successor_graph_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    nodes = _sequence(evaluated_graph.get("nodes"), "evaluated_graph.nodes")
    matches = [
        item
        for item in nodes
        if isinstance(item, Mapping) and item.get("node_id") == source_target["node_id"]
    ]
    if len(matches) != 1:
        raise RecursiveResearchEvidenceError(
            "recursive target must resolve to exactly one authenticated successor graph node"
        )
    node = matches[0]
    for field in ("node_type", "statement"):
        if node.get(field) != source_target[field]:
            raise RecursiveResearchEvidenceError(
                f"authenticated successor graph target identity drifted: {field}"
            )
    assessments = _sequence(
        evaluated_graph.get("assessments"), "evaluated_graph.assessments"
    )
    assessed = [
        item
        for item in assessments
        if isinstance(item, Mapping) and item.get("node_id") == source_target["node_id"]
    ]
    if len(assessed) != 1:
        raise RecursiveResearchEvidenceError(
            "recursive target requires exactly one evaluated epistemic assessment"
        )
    assessment = dict(assessed[0])
    _text(assessment.get("status"), "evaluated_graph target assessment.status")
    current_target = dict(source_target)
    current_target["graph_id"] = successor_graph_id
    return current_target, assessment


def _authenticated_transition(
    *,
    bundle_root: str | Path,
    execution: Mapping[str, Any],
    source_target: Mapping[str, Any],
    program_state: Mapping[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any], str, dict[str, Any], dict[str, Any]]:
    try:
        report = authenticate_transition_bundle(bundle_root)
    except (AuthenticatedTransitionConsumerError, OSError, ValueError) as exc:
        raise RecursiveResearchEvidenceError(
            "authenticated transition bundle failed independent consumer verification"
        ) from exc
    if report.get("current_transition_exact_provenance_authenticated") is not True:
        raise RecursiveResearchEvidenceError(
            "authenticated transition consumer did not establish exact current-transition provenance"
        )
    root = Path(_text(report.get("bundle_root"), "transition_consumer.bundle_root"))
    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        raise RecursiveResearchEvidenceError(
            "authenticated transition bundle root disappeared after verification"
        ) from exc

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
    source_action = _mapping(proposal.get("source_action"), "transition proposal.source_action")
    if source_action.get("action_id") != execution["action_id"]:
        raise RecursiveResearchEvidenceError(
            "authenticated transition proposal action_id differs from verified execution"
        )
    if source_action.get("action_class") != execution["action_type"]:
        raise RecursiveResearchEvidenceError(
            "authenticated transition proposal action_class differs from verified execution"
        )
    if source_action.get("action_version") != execution["action_version"]:
        raise RecursiveResearchEvidenceError(
            "authenticated transition proposal action_version differs from verified execution"
        )
    if proposal.get("base_graph_id") != source_target["graph_id"]:
        raise RecursiveResearchEvidenceError(
            "authenticated transition base_graph_id differs from recursive checkpoint graph"
        )
    if proposal.get("target_node_id") != source_target["node_id"]:
        raise RecursiveResearchEvidenceError(
            "authenticated transition target differs from recursive checkpoint target"
        )
    if report.get("target_node_id") != source_target["node_id"]:
        raise RecursiveResearchEvidenceError(
            "transition consumer target differs from recursive checkpoint target"
        )
    if report.get("transition_id") != proposal.get("transition_id"):
        raise RecursiveResearchEvidenceError(
            "transition consumer transition_id differs from exact proposal"
        )
    successor_graph_id = _text(proposal.get("new_graph_id"), "transition proposal.new_graph_id")
    if graph.get("graph_id") != successor_graph_id:
        raise RecursiveResearchEvidenceError(
            "authenticated successor graph_id differs from exact transition proposal"
        )
    result_node = _mapping(proposal.get("result_node"), "transition proposal.result_node")
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
            "verified execution result SHA is absent from the authenticated transition result artifacts"
        )

    try:
        evaluated_graph = evaluate_epistemic_graph(
            graph,
            program_state=program_state,
            artifact_root=root,
        )
    except (EpistemicGraphError, OSError, ValueError) as exc:
        raise RecursiveResearchEvidenceError(
            "authenticated successor graph could not be independently evaluated"
        ) from exc
    evaluated_sha = _canonical_sha256(evaluated_graph)
    current_target, assessment = _target_assessment(
        evaluated_graph,
        source_target=source_target,
        successor_graph_id=successor_graph_id,
    )
    report_sha = _canonical_sha256(report)
    graph_binding = _mapping(report.get("graph_binding"), "transition_consumer.graph_binding")
    transition = {
        "transition_id": report["transition_id"],
        "base_graph_id": proposal["base_graph_id"],
        "new_graph_id": successor_graph_id,
        "target_node_id": report["target_node_id"],
        "inference_edge_id": report.get("inference_edge_id"),
        "relation": report.get("relation"),
        "inference_scope": report.get("inference_scope"),
        "authenticated_successor_graph_sha256": _sha(
            graph_binding.get("sha256"),
            "transition_consumer.graph_binding.sha256",
        ),
        "transition_consumer_report_sha256": report_sha,
        "current_transition_exact_provenance_authenticated": True,
        "execution_completion_treated_as_scientific_support": False,
        "scientific_authority_applied_by_recursive_controller": False,
    }
    return (
        report_sha,
        transition,
        evaluated_graph,
        evaluated_sha,
        current_target,
        assessment,
    )


def _authoritative_portfolio(
    *,
    evaluated_graph: Mapping[str, Any],
    fresh_plan: Mapping[str, Any],
    target: Mapping[str, Any],
    assessment: Mapping[str, Any],
) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
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
    if target["node_type"] != "hypothesis":
        return portfolio, digest, None
    records = _sequence(portfolio.get("hypotheses"), "hypothesis_portfolio.hypotheses")
    matches = [
        item
        for item in records
        if isinstance(item, Mapping) and item.get("hypothesis_id") == target["node_id"]
    ]
    if len(matches) != 1:
        raise RecursiveResearchEvidenceError(
            "target hypothesis must resolve to exactly one authoritative portfolio record"
        )
    record = dict(matches[0])
    if record.get("statement") != target["statement"]:
        raise RecursiveResearchEvidenceError(
            "authoritative portfolio hypothesis statement drifted"
        )
    if record.get("epistemic_status") != assessment.get("status"):
        raise RecursiveResearchEvidenceError(
            "authoritative portfolio status differs from evaluated graph assessment"
        )
    return portfolio, digest, record


def advance_recursive_cycle_after_verified_transition(
    *,
    authorization_checkpoint: Mapping[str, Any],
    verified_execution_record: Mapping[str, Any],
    transition_bundle_root: str | Path,
    fresh_plan: Mapping[str, Any],
    program_state: Mapping[str, Any],
    previous_progression: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind verified execution -> authenticated transition -> authoritative portfolio."""
    checkpoint = _mapping(authorization_checkpoint, "authorization_checkpoint")
    (
        checkpoint_sha,
        source_target,
        expected_action_id,
        expected_action_type,
        expected_plan_sha,
    ) = _checkpoint(checkpoint)

    cycle_index = checkpoint.get("cycle_index")
    if (
        isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or cycle_index < 1
    ):
        raise RecursiveResearchEvidenceError(
            "checkpoint.cycle_index must be an integer >= 1"
        )
    checkpoint_ancestry = _mapping(
        checkpoint.get("ancestry"), "checkpoint.ancestry"
    )
    previous_checkpoint_sha = checkpoint_ancestry.get("previous_checkpoint_sha256")
    previous_sha: str | None = None
    previous_evaluated_graph_sha: str | None = None
    if cycle_index == 1:
        if previous_checkpoint_sha is not None:
            raise RecursiveResearchEvidenceError(
                "cycle-one checkpoint cannot carry previous checkpoint ancestry"
            )
        if previous_progression is not None:
            raise RecursiveResearchEvidenceError(
                "cycle-one progression cannot accept a predecessor progression"
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
        if previous.get("schema_version") != RECURSIVE_CYCLE_SCHEMA_VERSION:
            raise RecursiveResearchEvidenceError(
                "previous progression schema_version drifted"
            )
        if previous.get("policy_version") != RECURSIVE_EVIDENCE_POLICY_VERSION:
            raise RecursiveResearchEvidenceError(
                "previous progression policy_version drifted"
            )
        previous_sha = _embedded_sha(
            previous,
            field="previous_progression",
            sha_field="progression_sha256",
        )
        previous_cycle_index = previous.get("cycle_index")
        if (
            isinstance(previous_cycle_index, bool)
            or not isinstance(previous_cycle_index, int)
            or previous_cycle_index != cycle_index - 1
        ):
            raise RecursiveResearchEvidenceError(
                "previous progression is not the immediately preceding cycle"
            )
        previous_target = _mapping(
            previous.get("target"), "previous_progression.target"
        )
        for field in ("graph_id", "node_id", "node_type", "statement"):
            if previous_target.get(field) != source_target.get(field):
                raise RecursiveResearchEvidenceError(
                    f"previous progression does not terminate at current checkpoint target: {field}"
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
        previous_evaluated_graph_sha = _sha(
            prior_ancestry.get("evaluated_graph_canonical_sha256"),
            "previous_progression.ancestry.evaluated_graph_canonical_sha256",
        )

    plan, plan_sha = _fresh_plan(
        _mapping(fresh_plan, "fresh_plan"),
        expected_sha=expected_plan_sha,
    )
    execution_sha, execution = _execution_record(
        _mapping(verified_execution_record, "verified_execution_record"),
        checkpoint_sha=checkpoint_sha,
        expected_action_id=expected_action_id,
        expected_action_type=expected_action_type,
    )
    (
        transition_report_sha,
        transition,
        evaluated_graph,
        graph_sha,
        current_target,
        assessment,
    ) = _authenticated_transition(
        bundle_root=transition_bundle_root,
        execution=execution,
        source_target=source_target,
        program_state=_mapping(program_state, "program_state"),
    )
    portfolio, portfolio_sha, portfolio_state = _authoritative_portfolio(
        evaluated_graph=evaluated_graph,
        fresh_plan=plan,
        target=current_target,
        assessment=assessment,
    )

    if previous_evaluated_graph_sha == graph_sha:
        raise RecursiveResearchEvidenceError(
            "recursive cycle produced no new evaluated graph information state"
        )

    portfolio_state_name = (
        portfolio_state.get("portfolio_state") if portfolio_state is not None else None
    )
    if portfolio_state_name == "retired_falsified_within_verified_scope":
        status = "bounded_stop_hypothesis_retired"
        re_diagnosis_required = False
        stop_reason = "Target hypothesis remains retired/falsified within verified scope."
    elif portfolio_state_name == "positive_closeout_required":
        status = "bounded_stop_domain_closeout_required"
        re_diagnosis_required = False
        stop_reason = "Positive scientific closeout requires separate domain review."
    else:
        status = "re_diagnosis_required"
        re_diagnosis_required = True
        stop_reason = None

    result: dict[str, Any] = {
        "schema_version": RECURSIVE_CYCLE_SCHEMA_VERSION,
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
        "re_diagnosis": {
            "required": re_diagnosis_required,
            "performed": False,
            "previous_discrepancy_report_reuse_authorized": False,
        },
        "bounded_stop": {
            "stopped": not re_diagnosis_required,
            "reason": stop_reason,
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

__all__ = [
    "RECURSIVE_EVIDENCE_POLICY_VERSION",
    "VERIFIED_EXECUTION_RECORD_SCHEMA_VERSION",
    "RecursiveResearchEvidenceError",
    "advance_recursive_cycle_after_verified_transition",
]
