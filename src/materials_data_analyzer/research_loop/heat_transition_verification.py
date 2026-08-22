"""Repository-pinned domain verification for reference-heat epistemic transitions.

A transition verifier decision must not be handwritten by the acceptance driver.  This
module derives the v1.1 domain-verification decision only after the existing heat report
verifier recomputes the exact solver result, checks immutable-ledger bindings, and proves
that the transition is about the narrowly declared numerical-reference hypothesis.

The decision authenticates one computational diagnostic relation.  It does not establish
empirical material/process validity or positive scientific closeout.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .authenticated_inference_binding import (
    DOMAIN_VERIFICATION_DECISION_SCHEMA_VERSION,
)
from .heat_conduction_action import (
    ACTION_VERSION as HEAT_ACTION_VERSION,
    verify_heat_conduction_action_report_pinned,
)
from .kernel import ResearchLoopError

REFERENCE_HEAT_NUMERICAL_VALIDITY_TARGET = (
    "The audited reference heat-conduction solver is numerically valid within its "
    "declared analytical benchmark."
)
HEAT_TRANSITION_VERIFIER_ID = "repository-pinned-reference-heat-verifier-v1.0"


class HeatTransitionVerificationError(ResearchLoopError):
    """Raised when the exact heat transition cannot be domain-verified."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HeatTransitionVerificationError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _snapshot_json(path: str | Path, *, field: str) -> tuple[dict[str, Any], bytes, str]:
    try:
        resolved = Path(path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise HeatTransitionVerificationError(f"{field} does not resolve") from exc
    if not resolved.is_file():
        raise HeatTransitionVerificationError(f"{field} must be a file")
    raw = resolved.read_bytes()
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HeatTransitionVerificationError(f"{field} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise HeatTransitionVerificationError(f"{field} root must be an object")
    return value, raw, hashlib.sha256(raw).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HeatTransitionVerificationError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise HeatTransitionVerificationError(f"{field} must be a sequence")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise HeatTransitionVerificationError(f"{field} must be non-empty trimmed text")
    return value


def _request_record(path: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    value, raw, digest = _snapshot_json(path, field="heat_execution_request")
    return value, {
        "path": str(Path(path).expanduser().resolve(strict=True)),
        "sha256": digest,
        "bytes": len(raw),
    }


def build_heat_transition_verification_decision(
    *,
    base_graph_path: str | Path,
    proposal_path: str | Path,
    action_report_path: str | Path,
    execution_request_path: str | Path,
) -> dict[str, Any]:
    """Derive a v1.1 transition verifier decision from the pinned heat result."""
    base, _base_raw, base_sha = _snapshot_json(base_graph_path, field="base_graph")
    proposal, _proposal_raw, proposal_sha = _snapshot_json(
        proposal_path,
        field="transition_proposal",
    )
    request, request_record = _request_record(execution_request_path)
    try:
        verified = verify_heat_conduction_action_report_pinned(
            action_report_path,
            request_value=request,
            request_path=execution_request_path,
            request_record=request_record,
        )
    except ResearchLoopError as exc:
        raise HeatTransitionVerificationError(
            "heat transition verifier could not reproduce the exact typed execution"
        ) from exc
    if (
        verified.get("deterministic_recomputation_verified") is not True
        or verified.get("ledger_artifact_binding_verified") is not True
        or verified.get("registered_outcome")
        != "numerically_validated_reference_solution"
        or verified.get("validation_state") != "passed"
        or verified.get("run_status") != "completed"
        or verified.get("empirical_validation_performed") is not False
        or verified.get("scientific_status_upgrade_authorized") is not False
    ):
        raise HeatTransitionVerificationError(
            "only a pinned completed numerical-reference validation may enter this verifier"
        )

    if proposal.get("schema_version") != "1.0":
        raise HeatTransitionVerificationError("unsupported transition proposal schema")
    if proposal.get("base_graph_id") != base.get("graph_id"):
        raise HeatTransitionVerificationError(
            "transition proposal base_graph_id differs from exact base graph"
        )
    if proposal.get("base_graph_sha256") != base_sha:
        raise HeatTransitionVerificationError(
            "transition proposal base_graph_sha256 differs from exact base bytes"
        )
    target_id = _text(proposal.get("target_node_id"), "transition_proposal.target_node_id")
    nodes = _sequence(base.get("nodes"), "base_graph.nodes")
    targets = [
        _mapping(item, "base_graph.target")
        for item in nodes
        if isinstance(item, Mapping) and item.get("node_id") == target_id
    ]
    if len(targets) != 1:
        raise HeatTransitionVerificationError(
            "heat transition target must identify exactly one base-graph node"
        )
    target = targets[0]
    if target.get("node_type") != "hypothesis":
        raise HeatTransitionVerificationError(
            "heat transition verifier is restricted to a hypothesis target"
        )
    if target.get("statement") != REFERENCE_HEAT_NUMERICAL_VALIDITY_TARGET:
        raise HeatTransitionVerificationError(
            "heat transition verifier cannot be reused for an arbitrary scientific claim"
        )
    metadata = _mapping(target.get("metadata"), "base_graph.target.metadata")
    if metadata.get("claim_scope") != "computational":
        raise HeatTransitionVerificationError(
            "reference heat validity target must have computational claim_scope"
        )

    source_action = _mapping(
        proposal.get("source_action"),
        "transition_proposal.source_action",
    )
    expected_action_id = _text(request.get("action_id"), "heat_execution_request.action_id")
    if (
        source_action.get("action_id") != expected_action_id
        or source_action.get("action_class") != "simulation"
        or source_action.get("action_version") != HEAT_ACTION_VERSION
        or source_action.get("execution_mode") != "typed_local_action"
    ):
        raise HeatTransitionVerificationError(
            "transition source_action differs from the exact audited heat execution"
        )

    result_node = _mapping(
        proposal.get("result_node"),
        "transition_proposal.result_node",
    )
    if result_node.get("node_type") != "simulation":
        raise HeatTransitionVerificationError(
            "reference heat result_node must be a simulation"
        )
    result_metadata = _mapping(
        result_node.get("metadata"),
        "transition_proposal.result_node.metadata",
    )
    if result_metadata.get("result_origin") != "authorized_local_simulation":
        raise HeatTransitionVerificationError(
            "reference heat result origin must be authorized_local_simulation"
        )
    bindings = _sequence(
        result_node.get("artifact_bindings"),
        "transition_proposal.result_node.artifact_bindings",
    )
    bound_shas = {
        item.get("sha256")
        for item in bindings
        if isinstance(item, Mapping) and isinstance(item.get("sha256"), str)
    }
    if verified.get("solver_result_sha256") not in bound_shas:
        raise HeatTransitionVerificationError(
            "transition result artifacts do not contain the pinned solver-result bytes"
        )

    inference = _mapping(
        proposal.get("proposed_inference"),
        "transition_proposal.proposed_inference",
    )
    if inference.get("relation") != "supports":
        raise HeatTransitionVerificationError(
            "reference numerical-validation transition supports only the computational validity target"
        )
    inference_edge_id = _text(
        inference.get("inference_edge_id"),
        "transition_proposal.proposed_inference.inference_edge_id",
    )
    result_node_id = _text(result_node.get("node_id"), "transition_proposal.result_node.node_id")
    transition_id = _text(proposal.get("transition_id"), "transition_proposal.transition_id")

    return {
        "schema_version": DOMAIN_VERIFICATION_DECISION_SCHEMA_VERSION,
        "decision_id": f"heat-domain-verification:{transition_id}",
        "transition_id": transition_id,
        "proposal_sha256": proposal_sha,
        "base_graph_sha256": base_sha,
        "inference_edge_id": inference_edge_id,
        "result_node_id": result_node_id,
        "target_node_id": target_id,
        "relation": "supports",
        "inference_scope": "computational",
        "verifier_id": HEAT_TRANSITION_VERIFIER_ID,
        "rationale": (
            "The repository-pinned heat verifier deterministically recomputed the exact "
            "solver result and re-established its immutable-ledger binding. This verifies "
            "only the declared computational reference benchmark."
        ),
        "limitations": [
            "No empirical material or process validation was performed.",
            "The authenticated transition producer must preserve this relation as diagnostic before independent consumer interpretation.",
            "Positive scientific closeout is not granted by this verification.",
        ],
        "domain_verified": True,
    }


def publish_heat_transition_verification_decision(
    *,
    base_graph_path: str | Path,
    proposal_path: str | Path,
    action_report_path: str | Path,
    execution_request_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Write the derived verification decision once and return its exact binding."""
    decision = build_heat_transition_verification_decision(
        base_graph_path=base_graph_path,
        proposal_path=proposal_path,
        action_report_path=action_report_path,
        execution_request_path=execution_request_path,
    )
    output = Path(output_path).expanduser().resolve()
    if output.exists():
        raise HeatTransitionVerificationError(
            "verification decision output_path must not already exist"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = (
        json.dumps(decision, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")
    output.write_bytes(raw)
    return {
        "decision": decision,
        "binding": {
            "path": str(output),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        },
        "pinned_heat_verification_performed": True,
        "empirical_validation_performed": False,
        "scientific_status_upgrade_authorized": False,
    }


__all__ = [
    "HEAT_TRANSITION_VERIFIER_ID",
    "REFERENCE_HEAT_NUMERICAL_VALIDITY_TARGET",
    "HeatTransitionVerificationError",
    "build_heat_transition_verification_decision",
    "publish_heat_transition_verification_decision",
]
