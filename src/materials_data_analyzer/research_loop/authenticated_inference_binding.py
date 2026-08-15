"""Fail-closed authentication for one proposed directional inference edge.

This module owns only the byte-bound identity contract between a reasoning proposal and
its domain-verification decision. It does not decide whether a scientific relation is
true, execute an action, or mutate an epistemic graph.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .kernel import ResearchLoopError

AUTHENTICATED_INFERENCE_BINDING_SCHEMA_VERSION = "1.0"
DOMAIN_VERIFICATION_DECISION_SCHEMA_VERSION = "1.1"

_DIRECTIONAL_RELATIONS = {"supports", "contradicts", "falsifies"}
_INFERENCE_SCOPES = {"structural", "computational", "empirical_derived", "empirical_direct"}
_DECISION_KEYS_V11 = {
    "schema_version",
    "decision_id",
    "transition_id",
    "proposal_sha256",
    "base_graph_sha256",
    "inference_edge_id",
    "result_node_id",
    "target_node_id",
    "relation",
    "inference_scope",
    "verifier_id",
    "rationale",
    "limitations",
    "domain_verified",
}


class AuthenticatedInferenceBindingError(ResearchLoopError):
    """Raised when exact inference-edge provenance cannot be authenticated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuthenticatedInferenceBindingError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _json_object_from_exact_bytes(raw: bytes, *, field: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthenticatedInferenceBindingError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise AuthenticatedInferenceBindingError(f"{field} root must be an object")
    return value


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuthenticatedInferenceBindingError(f"{field} must be non-empty text")
    return value.strip()


def _sha256_text(value: object, field: str) -> str:
    text = _nonempty_text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise AuthenticatedInferenceBindingError(
            f"{field} must be a lowercase 64-character SHA-256"
        )
    return text


def _proposal_inference(proposal: Mapping[str, Any]) -> Mapping[str, Any]:
    proposed = proposal.get("proposed_inference")
    if not isinstance(proposed, Mapping):
        raise AuthenticatedInferenceBindingError(
            "proposal.proposed_inference must be an object"
        )
    return proposed


def _validate_decision_v11(decision: Mapping[str, Any]) -> None:
    keys = set(decision)
    missing = sorted(_DECISION_KEYS_V11 - keys)
    unknown = sorted(keys - _DECISION_KEYS_V11)
    if missing:
        raise AuthenticatedInferenceBindingError(
            "domain verification decision is missing required keys: " + ", ".join(missing)
        )
    if unknown:
        raise AuthenticatedInferenceBindingError(
            "domain verification decision has unknown keys: " + ", ".join(unknown)
        )
    if decision.get("schema_version") != DOMAIN_VERIFICATION_DECISION_SCHEMA_VERSION:
        raise AuthenticatedInferenceBindingError(
            "authenticated inference binding requires domain verification decision schema v1.1"
        )
    if decision.get("domain_verified") is not True:
        raise AuthenticatedInferenceBindingError(
            "domain verification decision must set domain_verified=true"
        )

    for field in (
        "decision_id",
        "transition_id",
        "inference_edge_id",
        "result_node_id",
        "target_node_id",
        "verifier_id",
        "rationale",
    ):
        _nonempty_text(decision.get(field), f"domain verification decision {field}")
    _sha256_text(
        decision.get("proposal_sha256"),
        "domain verification decision proposal_sha256",
    )
    _sha256_text(
        decision.get("base_graph_sha256"),
        "domain verification decision base_graph_sha256",
    )

    relation = _nonempty_text(
        decision.get("relation"), "domain verification decision relation"
    )
    if relation not in _DIRECTIONAL_RELATIONS:
        raise AuthenticatedInferenceBindingError(
            "domain verification decision relation is unsupported"
        )
    scope = _nonempty_text(
        decision.get("inference_scope"), "domain verification decision inference_scope"
    )
    if scope not in _INFERENCE_SCOPES:
        raise AuthenticatedInferenceBindingError(
            "domain verification decision inference_scope is unsupported"
        )

    limitations = decision.get("limitations")
    if not isinstance(limitations, list):
        raise AuthenticatedInferenceBindingError(
            "domain verification decision limitations must be a list"
        )
    seen: set[str] = set()
    for index, raw in enumerate(limitations):
        text = _nonempty_text(raw, f"domain verification decision limitations[{index}]")
        if text in seen:
            raise AuthenticatedInferenceBindingError(
                "domain verification decision limitations must not contain duplicates"
            )
        seen.add(text)


def authenticate_inference_binding(
    *,
    proposal_bytes: bytes,
    verification_decision_bytes: bytes,
    expected_base_graph_sha256: str,
) -> dict[str, Any]:
    """Authenticate exact proposal↔verifier identity for one directional edge.

    Both JSON objects are parsed from the exact bytes whose SHA-256 values enter the
    returned binding. The result is provenance metadata only; it is not scientific
    evidence and grants no execution, stop/reframe, or positive-closeout authority.
    """
    if not isinstance(proposal_bytes, bytes):
        raise AuthenticatedInferenceBindingError("proposal_bytes must be bytes")
    if not isinstance(verification_decision_bytes, bytes):
        raise AuthenticatedInferenceBindingError(
            "verification_decision_bytes must be bytes"
        )
    proposal = _json_object_from_exact_bytes(proposal_bytes, field="proposal")
    decision = _json_object_from_exact_bytes(
        verification_decision_bytes, field="domain verification decision"
    )
    proposal_sha = hashlib.sha256(proposal_bytes).hexdigest()
    verifier_sha = hashlib.sha256(verification_decision_bytes).hexdigest()
    base_graph_sha = _sha256_text(
        expected_base_graph_sha256, "expected_base_graph_sha256"
    )
    _validate_decision_v11(decision)

    if decision.get("proposal_sha256") != proposal_sha:
        raise AuthenticatedInferenceBindingError(
            "domain verification decision proposal_sha256 does not match exact proposal bytes"
        )
    if decision.get("base_graph_sha256") != base_graph_sha:
        raise AuthenticatedInferenceBindingError(
            "domain verification decision base_graph_sha256 does not match expected base graph"
        )

    proposed = _proposal_inference(proposal)
    edge_id = _nonempty_text(
        proposed.get("inference_edge_id"), "proposal proposed_inference.inference_edge_id"
    )
    result_node = proposal.get("result_node")
    if not isinstance(result_node, Mapping):
        raise AuthenticatedInferenceBindingError("proposal.result_node must be an object")
    result_node_id = _nonempty_text(
        result_node.get("node_id"), "proposal result_node.node_id"
    )
    target_node_id = _nonempty_text(
        proposal.get("target_node_id"), "proposal target_node_id"
    )
    relation = _nonempty_text(
        proposed.get("relation"), "proposal proposed_inference.relation"
    )
    if relation not in _DIRECTIONAL_RELATIONS:
        raise AuthenticatedInferenceBindingError("proposal directional relation is unsupported")

    expected_pairs = {
        "inference_edge_id": edge_id,
        "result_node_id": result_node_id,
        "target_node_id": target_node_id,
        "relation": relation,
    }
    for field, expected in expected_pairs.items():
        if decision.get(field) != expected:
            raise AuthenticatedInferenceBindingError(
                f"domain verification decision {field} does not match proposal"
            )

    return {
        "schema_version": AUTHENTICATED_INFERENCE_BINDING_SCHEMA_VERSION,
        "transition_id": _nonempty_text(
            decision.get("transition_id"), "domain verification decision transition_id"
        ),
        "inference_edge_id": edge_id,
        "result_node_id": result_node_id,
        "target_node_id": target_node_id,
        "relation": relation,
        "inference_scope": _nonempty_text(
            decision.get("inference_scope"),
            "domain verification decision inference_scope",
        ),
        "proposal_sha256": proposal_sha,
        "base_graph_sha256": base_graph_sha,
        "verification_decision_sha256": verifier_sha,
        "domain_verified": True,
        "scientific_status_changed": False,
        "execution_authorized": False,
        "positive_closeout_granted": False,
    }


__all__ = [
    "AUTHENTICATED_INFERENCE_BINDING_SCHEMA_VERSION",
    "DOMAIN_VERIFICATION_DECISION_SCHEMA_VERSION",
    "AuthenticatedInferenceBindingError",
    "authenticate_inference_binding",
]
