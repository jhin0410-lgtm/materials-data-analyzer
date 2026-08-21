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
    AUTHENTICATED_TRANSITION_CONSUMER_POLICY_VERSION,
    AUTHENTICATED_TRANSITION_CONSUMER_SCHEMA_VERSION,
    authenticate_transition_bundle,
)
from .hypothesis_portfolio import (
    HYPOTHESIS_PORTFOLIO_POLICY_VERSION,
    HYPOTHESIS_PORTFOLIO_SCHEMA_VERSION,
)
from .kernel import ResearchLoopError
from .recursive_research_cycle_controller import (
    RECURSIVE_CYCLE_POLICY_VERSION,
    RECURSIVE_CYCLE_SCHEMA_VERSION,
)

RECURSIVE_EVIDENCE_POLICY_VERSION = "1.0"
VERIFIED_EXECUTION_RECORD_SCHEMA_VERSION = "1.0"
EPISTEMIC_TRANSITION_RECORD_SCHEMA_VERSION = "1.0"
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
) -> tuple[str, dict[str, Any], str]:
    if value.get("schema_version") != RECURSIVE_CYCLE_SCHEMA_VERSION:
        raise RecursiveResearchEvidenceError(
            "unsupported recursive checkpoint schema_version"
        )
    if value.get("policy_version") != RECURSIVE_CYCLE_POLICY_VERSION:
        raise RecursiveResearchEvidenceError(
            "unsupported recursive checkpoint policy_version"
        )
    digest = _embedded_sha(value, field="checkpoint", sha_field="checkpoint_sha256")
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

    planner = _mapping(
        value.get("fresh_planner_state"), "checkpoint.fresh_planner_state"
    )
    selected_action_id = _text(
        planner.get("selected_candidate_id"),
        "checkpoint.fresh_planner_state.selected_candidate_id",
    )
    match = _mapping(value.get("candidate_match"), "checkpoint.candidate_match")
    if match.get("candidate_action_id") != selected_action_id:
        raise RecursiveResearchEvidenceError(
            "checkpoint candidate match differs from planner-selected action"
        )
    return digest, target, selected_action_id


def _execution_record(
    value: Mapping[str, Any],
    *,
    checkpoint_sha: str,
    selected_action_id: str,
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
    if value.get("authorization_status") != (
        "explicit_request_authorized_by_existing_chain"
    ):
        raise RecursiveResearchEvidenceError(
            "execution record does not attest existing-chain explicit authorization"
        )
    if value.get("independent_verification_status") != "verified_by_existing_chain":
        raise RecursiveResearchEvidenceError(
            "execution record is not marked as independently verified by the existing chain"
        )
    action_id = _text(value.get("action_id"), "verified_execution_record.action_id")
    if action_id != selected_action_id:
        raise RecursiveResearchEvidenceError(
            "verified execution action_id differs from planner-selected checkpoint candidate"
        )
    for field in ("action_type", "action_version"):
        _text(value.get(field), f"verified_execution_record.{field}")
    for field in ("request_sha256", "registry_sha256", "result_sha256"):
        _sha(value.get(field), f"verified_execution_record.{field}")
    outcome = _text(
        value.get("execution_outcome"),
        "verified_execution_record.execution_outcome",
    )
    if outcome not in {"completed", "rejected", "failed"}:
        raise RecursiveResearchEvidenceError(
            "unsupported verified execution outcome"
        )
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
        "action_type": value["action_type"],
        "action_version": value["action_version"],
        "request_sha256": value["request_sha256"],
        "registry_sha256": value["registry_sha256"],
        "result_sha256": value["result_sha256"],
        "execution_outcome": outcome,
        "execution_success": success,
    }


def _graph_target(
    graph: Mapping[str, Any], target: Mapping[str, Any]
) -> tuple[str, dict[str, Any]]:
    if graph.get("graph_id") != target["graph_id"]:
        raise RecursiveResearchEvidenceError(
            "evaluated graph identity changed across recursive cycle"
        )
    nodes = _sequence(graph.get("nodes"), "evaluated_graph.nodes")
    matches = [
        item
        for item in nodes
        if isinstance(item, Mapping) and item.get("node_id") == target["node_id"]
    ]
    if len(matches) != 1:
        raise RecursiveResearchEvidenceError(
            "recursive target must resolve to exactly one evaluated graph node"
        )
    node = matches[0]
    if (
        node.get("node_type") != target["node_type"]
        or node.get("statement") != target["statement"]
    ):
        raise RecursiveResearchEvidenceError(
            "evaluated graph target identity was substituted"
        )
    assessments = _sequence(graph.get("assessments"), "evaluated_graph.assessments")
    assessed = [
        item
        for item in assessments
        if isinstance(item, Mapping) and item.get("node_id") == target["node_id"]
    ]
    if len(assessed) != 1:
        raise RecursiveResearchEvidenceError(
            "recursive target requires exactly one evaluated epistemic assessment"
        )
    assessment = dict(assessed[0])
    _text(assessment.get("status"), "evaluated_graph target assessment.status")
    return _canonical_sha256(graph), assessment


def build_epistemic_transition_record_from_authenticated_bundle(
    bundle_root: str | Path,
    *,
    verified_execution_record: Mapping[str, Any],
    evaluated_graph: Mapping[str, Any],
) -> dict[str, Any]:
    """Adapt the production authenticated-transition consumer into the recursive record.

    The consumer is executed here; callers cannot satisfy this adapter with asserted
    booleans alone. The exact successor graph file is re-read and checksum-compared to
    the consumer report, then compared with the graph object passed into recursion.
    """
    execution = _mapping(verified_execution_record, "verified_execution_record")
    execution_sha = _embedded_sha(
        execution,
        field="verified_execution_record",
        sha_field="verification_record_sha256",
    )
    graph = dict(_mapping(evaluated_graph, "evaluated_graph"))
    consumer = authenticate_transition_bundle(bundle_root)
    if consumer.get("schema_version") != AUTHENTICATED_TRANSITION_CONSUMER_SCHEMA_VERSION:
        raise RecursiveResearchEvidenceError(
            "authenticated transition consumer schema_version drifted"
        )
    if consumer.get("consumer_policy_version") != (
        AUTHENTICATED_TRANSITION_CONSUMER_POLICY_VERSION
    ):
        raise RecursiveResearchEvidenceError(
            "authenticated transition consumer policy_version drifted"
        )
    if consumer.get("current_transition_exact_provenance_authenticated") is not True:
        raise RecursiveResearchEvidenceError(
            "authenticated transition consumer did not authenticate exact provenance"
        )
    authority = _mapping(
        consumer.get("authority_boundary"),
        "authenticated_transition_consumer.authority_boundary",
    )
    if authority.get("scientific_authority_applied") is not False:
        raise RecursiveResearchEvidenceError(
            "authenticated transition consumer cannot imply scientific authority"
        )
    if authority.get("scientific_status_changed") is not False:
        raise RecursiveResearchEvidenceError(
            "authenticated transition consumer cannot change scientific status"
        )

    graph_binding = _mapping(
        consumer.get("graph_binding"),
        "authenticated_transition_consumer.graph_binding",
    )
    graph_path = _text(
        graph_binding.get("path"),
        "authenticated_transition_consumer.graph_binding.path",
    )
    expected_file_sha = _sha(
        graph_binding.get("sha256"),
        "authenticated_transition_consumer.graph_binding.sha256",
    )
    root = Path(
        _text(
            consumer.get("bundle_root"),
            "authenticated_transition_consumer.bundle_root",
        )
    )
    candidate = (root / graph_path).resolve(strict=True)
    try:
        candidate.relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise RecursiveResearchEvidenceError(
            "authenticated successor graph path escapes bundle root"
        ) from exc
    try:
        raw_graph = candidate.read_bytes()
    except OSError as exc:
        raise RecursiveResearchEvidenceError(
            "authenticated successor graph bytes are unreadable"
        ) from exc
    if hashlib.sha256(raw_graph).hexdigest() != expected_file_sha:
        raise RecursiveResearchEvidenceError(
            "authenticated successor graph bytes changed after consumer verification"
        )
    try:
        parsed = json.loads(raw_graph.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecursiveResearchEvidenceError(
            "authenticated successor graph is not UTF-8 JSON"
        ) from exc
    if not isinstance(parsed, dict) or parsed != graph:
        raise RecursiveResearchEvidenceError(
            "evaluated graph differs from authenticated successor graph bytes"
        )

    target_node_id = _text(
        consumer.get("target_node_id"),
        "authenticated_transition_consumer.target_node_id",
    )
    if not any(
        isinstance(item, Mapping) and item.get("node_id") == target_node_id
        for item in _sequence(graph.get("nodes"), "evaluated_graph.nodes")
    ):
        raise RecursiveResearchEvidenceError(
            "authenticated transition target is absent from evaluated graph"
        )
    report_sha = _canonical_sha256(consumer)
    record: dict[str, Any] = {
        "schema_version": EPISTEMIC_TRANSITION_RECORD_SCHEMA_VERSION,
        "verified_execution_record_sha256": execution_sha,
        "evaluated_graph_canonical_sha256": _canonical_sha256(graph),
        "target_node_id": target_node_id,
        "transition_id": _text(
            consumer.get("transition_id"),
            "authenticated_transition_consumer.transition_id",
        ),
        "consumer_verification_sha256": report_sha,
        "consumer_verification_status": "verified_by_authenticated_transition_consumer",
        "execution_completion_treated_as_scientific_support": False,
        "authenticated_consumer_graph_file_sha256": expected_file_sha,
    }
    record["transition_record_sha256"] = _canonical_sha256(record)
    return record


def _transition_record(
    value: Mapping[str, Any],
    *,
    execution_sha: str,
    graph_sha: str,
    target: Mapping[str, Any],
) -> tuple[str, dict[str, Any]]:
    if value.get("schema_version") != EPISTEMIC_TRANSITION_RECORD_SCHEMA_VERSION:
        raise RecursiveResearchEvidenceError(
            "unsupported epistemic transition verification record schema_version"
        )
    digest = _embedded_sha(
        value,
        field="epistemic_transition_record",
        sha_field="transition_record_sha256",
    )
    if value.get("verified_execution_record_sha256") != execution_sha:
        raise RecursiveResearchEvidenceError(
            "epistemic transition record is bound to a different execution verification"
        )
    if value.get("evaluated_graph_canonical_sha256") != graph_sha:
        raise RecursiveResearchEvidenceError(
            "epistemic transition record is bound to a different evaluated graph"
        )
    if value.get("target_node_id") != target["node_id"]:
        raise RecursiveResearchEvidenceError(
            "epistemic transition target substitution detected"
        )
    _text(value.get("transition_id"), "epistemic_transition_record.transition_id")
    _sha(
        value.get("consumer_verification_sha256"),
        "epistemic_transition_record.consumer_verification_sha256",
    )
    if value.get("consumer_verification_status") != (
        "verified_by_authenticated_transition_consumer"
    ):
        raise RecursiveResearchEvidenceError(
            "epistemic transition was not verified by the authenticated transition consumer"
        )
    if value.get("execution_completion_treated_as_scientific_support") is not False:
        raise RecursiveResearchEvidenceError(
            "execution completion cannot be treated as a directional epistemic relation"
        )
    graph_file_sha = value.get("authenticated_consumer_graph_file_sha256")
    if graph_file_sha is not None:
        _sha(
            graph_file_sha,
            "epistemic_transition_record.authenticated_consumer_graph_file_sha256",
        )
    return digest, {
        "transition_id": value["transition_id"],
        "consumer_verification_sha256": value["consumer_verification_sha256"],
        "authenticated_consumer_graph_file_sha256": graph_file_sha,
    }


def _portfolio(
    value: Mapping[str, Any],
    *,
    graph: Mapping[str, Any],
    graph_sha: str,
    target: Mapping[str, Any],
    assessment: Mapping[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    if value.get("schema_version") != HYPOTHESIS_PORTFOLIO_SCHEMA_VERSION:
        raise RecursiveResearchEvidenceError(
            "unsupported hypothesis portfolio schema_version"
        )
    if value.get("policy_version") != HYPOTHESIS_PORTFOLIO_POLICY_VERSION:
        raise RecursiveResearchEvidenceError(
            "unsupported hypothesis portfolio policy_version"
        )
    digest = _embedded_sha(
        value, field="hypothesis_portfolio", sha_field="portfolio_sha256"
    )
    if value.get("graph_id") != graph.get("graph_id"):
        raise RecursiveResearchEvidenceError("hypothesis portfolio graph_id drifted")
    binding = _mapping(
        value.get("evaluated_graph_binding"),
        "hypothesis_portfolio.evaluated_graph_binding",
    )
    if binding.get("canonical_sha256") != graph_sha:
        raise RecursiveResearchEvidenceError(
            "hypothesis portfolio is not bound to the current evaluated graph"
        )
    if target["node_type"] != "hypothesis":
        return digest, None
    records = _sequence(value.get("hypotheses"), "hypothesis_portfolio.hypotheses")
    matches = [
        item
        for item in records
        if isinstance(item, Mapping) and item.get("hypothesis_id") == target["node_id"]
    ]
    if len(matches) != 1:
        raise RecursiveResearchEvidenceError(
            "target hypothesis must resolve to exactly one portfolio record"
        )
    record = dict(matches[0])
    if record.get("statement") != target["statement"]:
        raise RecursiveResearchEvidenceError(
            "portfolio hypothesis statement drifted"
        )
    status = _text(
        assessment.get("status"), "evaluated_graph target assessment.status"
    )
    if record.get("epistemic_status") != status:
        raise RecursiveResearchEvidenceError(
            "portfolio epistemic status does not match evaluated graph assessment"
        )
    expected = _STATUS_TO_PORTFOLIO.get(status)
    if expected is None:
        raise RecursiveResearchEvidenceError(
            "unsupported evaluated epistemic status for portfolio persistence"
        )
    state = _text(
        record.get("portfolio_state"),
        "hypothesis_portfolio target portfolio_state",
    )
    directive = _text(
        record.get("research_directive"),
        "hypothesis_portfolio target research_directive",
    )
    if state != expected[0]:
        raise RecursiveResearchEvidenceError(
            "portfolio_state does not match deterministic epistemic-status semantics"
        )
    if directive != expected[1]:
        raise RecursiveResearchEvidenceError(
            "portfolio research_directive does not match deterministic epistemic-status semantics"
        )
    return digest, {
        "hypothesis_id": target["node_id"],
        "epistemic_status": status,
        "portfolio_state": state,
        "research_directive": directive,
    }


def advance_recursive_cycle_after_verified_transition(
    *,
    authorization_checkpoint: Mapping[str, Any],
    verified_execution_record: Mapping[str, Any],
    epistemic_transition_record: Mapping[str, Any],
    evaluated_graph: Mapping[str, Any],
    hypothesis_portfolio: Mapping[str, Any],
    previous_progression: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind verified execution -> graph transition -> portfolio and request re-diagnosis."""
    checkpoint_sha, target, selected_action_id = _checkpoint(
        _mapping(authorization_checkpoint, "authorization_checkpoint")
    )
    execution_sha, execution = _execution_record(
        _mapping(verified_execution_record, "verified_execution_record"),
        checkpoint_sha=checkpoint_sha,
        selected_action_id=selected_action_id,
    )
    graph = _mapping(evaluated_graph, "evaluated_graph")
    graph_sha, assessment = _graph_target(graph, target)
    transition_sha, transition = _transition_record(
        _mapping(epistemic_transition_record, "epistemic_transition_record"),
        execution_sha=execution_sha,
        graph_sha=graph_sha,
        target=target,
    )
    portfolio_sha, portfolio_state = _portfolio(
        _mapping(hypothesis_portfolio, "hypothesis_portfolio"),
        graph=graph,
        graph_sha=graph_sha,
        target=target,
        assessment=assessment,
    )

    previous_sha = None
    if previous_progression is not None:
        previous = _mapping(previous_progression, "previous_progression")
        previous_sha = _embedded_sha(
            previous,
            field="previous_progression",
            sha_field="progression_sha256",
        )
        if previous.get("target") != target:
            raise RecursiveResearchEvidenceError(
                "recursive progression target changed across iterations"
            )
        prior_ancestry = _mapping(
            previous.get("ancestry"), "previous_progression.ancestry"
        )
        if prior_ancestry.get("evaluated_graph_canonical_sha256") == graph_sha:
            raise RecursiveResearchEvidenceError(
                "recursive cycle produced no new evaluated graph information state"
            )

    portfolio_state_name = (
        portfolio_state.get("portfolio_state")
        if portfolio_state is not None
        else None
    )
    if portfolio_state_name == "retired_falsified_within_verified_scope":
        status = "bounded_stop_hypothesis_retired"
        re_diagnosis_required = False
        stop_reason = (
            "Target hypothesis remains retired/falsified within verified scope."
        )
    elif portfolio_state_name == "positive_closeout_required":
        status = "bounded_stop_domain_closeout_required"
        re_diagnosis_required = False
        stop_reason = (
            "Positive scientific closeout requires separate domain review."
        )
    else:
        status = "re_diagnosis_required"
        re_diagnosis_required = True
        stop_reason = None

    result: dict[str, Any] = {
        "schema_version": RECURSIVE_CYCLE_SCHEMA_VERSION,
        "policy_version": RECURSIVE_EVIDENCE_POLICY_VERSION,
        "cycle_id": authorization_checkpoint.get("cycle_id"),
        "cycle_index": authorization_checkpoint.get("cycle_index"),
        "progression_status": status,
        "target": dict(target),
        "ancestry": {
            "previous_progression_sha256": previous_sha,
            "authorization_checkpoint_sha256": checkpoint_sha,
            "verified_execution_record_sha256": execution_sha,
            "epistemic_transition_record_sha256": transition_sha,
            "evaluated_graph_canonical_sha256": graph_sha,
            "hypothesis_portfolio_sha256": portfolio_sha,
        },
        "verified_execution": execution,
        "verified_epistemic_transition": transition,
        "target_epistemic_assessment": dict(assessment),
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
    "EPISTEMIC_TRANSITION_RECORD_SCHEMA_VERSION",
    "RECURSIVE_EVIDENCE_POLICY_VERSION",
    "RecursiveResearchEvidenceError",
    "VERIFIED_EXECUTION_RECORD_SCHEMA_VERSION",
    "advance_recursive_cycle_after_verified_transition",
    "build_epistemic_transition_record_from_authenticated_bundle",
]
