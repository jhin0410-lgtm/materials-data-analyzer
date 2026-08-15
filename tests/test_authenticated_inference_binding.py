from __future__ import annotations

import hashlib
import json

import pytest

from materials_data_analyzer.research_loop.authenticated_inference_binding import (
    AuthenticatedInferenceBindingError,
    authenticate_inference_binding,
)


def _proposal_bytes(*, edge_id: str = "edge-1") -> bytes:
    value = {
        "schema_version": "1.0",
        "transition_id": "transition-1",
        "base_graph_id": "base-graph",
        "base_graph_sha256": "b" * 64,
        "new_graph_id": "successor-graph",
        "target_node_id": "target-1",
        "source_action": {
            "action_id": "action-1",
            "action_class": "existing_data_reanalysis",
            "action_version": "1.0",
            "execution_mode": "typed_local_action",
        },
        "result_node": {
            "node_id": "result-1",
            "node_type": "analysis",
            "statement": "Bound result.",
            "artifact_bindings": [],
            "metadata": {"result_origin": "authorized_local_analysis"},
        },
        "input_evidence_bindings": [],
        "proposed_inference": {
            "tests_edge_id": "tests-1",
            "inference_edge_id": edge_id,
            "relation": "supports",
            "rationale": "Bound directional proposal.",
        },
        "limitations": ["Contract fixture only."],
    }
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _decision_bytes(
    proposal: bytes,
    *,
    edge_id: str = "edge-1",
    schema_version: str = "1.1",
    base_graph_sha256: str = "b" * 64,
    extra: dict[str, object] | None = None,
) -> bytes:
    value: dict[str, object] = {
        "schema_version": schema_version,
        "decision_id": "decision-1",
        "transition_id": "transition-1",
        "proposal_sha256": hashlib.sha256(proposal).hexdigest(),
        "base_graph_sha256": base_graph_sha256,
        "inference_edge_id": edge_id,
        "result_node_id": "result-1",
        "target_node_id": "target-1",
        "relation": "supports",
        "inference_scope": "structural",
        "verifier_id": "domain-verifier",
        "rationale": "Verified only within the stated structural scope.",
        "limitations": [],
        "domain_verified": True,
    }
    if extra:
        value.update(extra)
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def test_exact_pretty_printed_proposal_bytes_are_authenticated() -> None:
    proposal = _proposal_bytes()
    decision = _decision_bytes(proposal)

    result = authenticate_inference_binding(
        proposal_bytes=proposal,
        verification_decision_bytes=decision,
        expected_base_graph_sha256="b" * 64,
    )

    assert result["inference_edge_id"] == "edge-1"
    assert result["proposal_sha256"] == hashlib.sha256(proposal).hexdigest()
    assert result["verification_decision_sha256"] == hashlib.sha256(decision).hexdigest()
    assert result["domain_verified"] is True
    assert result["scientific_status_changed"] is False
    assert result["execution_authorized"] is False
    assert result["positive_closeout_granted"] is False


def test_same_triple_reused_for_different_edge_id_is_rejected() -> None:
    proposal = _proposal_bytes(edge_id="edge-1")
    decision = _decision_bytes(proposal, edge_id="edge-2")

    with pytest.raises(
        AuthenticatedInferenceBindingError,
        match="inference_edge_id does not match proposal",
    ):
        authenticate_inference_binding(
            proposal_bytes=proposal,
            verification_decision_bytes=decision,
            expected_base_graph_sha256="b" * 64,
        )


def test_verifier_cannot_bind_a_different_proposal_serialization() -> None:
    proposal = _proposal_bytes()
    parsed = json.loads(proposal.decode("utf-8"))
    reserialized = (json.dumps(parsed, sort_keys=True) + "\n").encode("utf-8")
    assert reserialized != proposal
    decision = _decision_bytes(proposal)

    with pytest.raises(
        AuthenticatedInferenceBindingError,
        match="proposal_sha256 does not match exact proposal bytes",
    ):
        authenticate_inference_binding(
            proposal_bytes=reserialized,
            verification_decision_bytes=decision,
            expected_base_graph_sha256="b" * 64,
        )


def test_base_graph_mismatch_is_rejected() -> None:
    proposal = _proposal_bytes()
    decision = _decision_bytes(proposal, base_graph_sha256="c" * 64)

    with pytest.raises(
        AuthenticatedInferenceBindingError,
        match="base_graph_sha256 does not match expected base graph",
    ):
        authenticate_inference_binding(
            proposal_bytes=proposal,
            verification_decision_bytes=decision,
            expected_base_graph_sha256="b" * 64,
        )


def test_legacy_v10_decision_cannot_claim_authenticated_edge_identity() -> None:
    proposal = _proposal_bytes()
    decision = _decision_bytes(proposal, schema_version="1.0")

    with pytest.raises(
        AuthenticatedInferenceBindingError,
        match="requires domain verification decision schema v1.1",
    ):
        authenticate_inference_binding(
            proposal_bytes=proposal,
            verification_decision_bytes=decision,
            expected_base_graph_sha256="b" * 64,
        )


def test_unknown_verifier_field_is_rejected() -> None:
    proposal = _proposal_bytes()
    decision = _decision_bytes(proposal, extra={"opaque_authority": True})

    with pytest.raises(
        AuthenticatedInferenceBindingError,
        match="unknown keys: opaque_authority",
    ):
        authenticate_inference_binding(
            proposal_bytes=proposal,
            verification_decision_bytes=decision,
            expected_base_graph_sha256="b" * 64,
        )


def test_duplicate_verifier_key_is_rejected() -> None:
    proposal = _proposal_bytes()
    proposal_sha = hashlib.sha256(proposal).hexdigest()
    base_sha = "b" * 64
    raw = (
        "{"
        '"schema_version":"1.1",'
        '"decision_id":"decision-1",'
        '"transition_id":"transition-1",'
        f'"proposal_sha256":"{proposal_sha}",'
        f'"base_graph_sha256":"{base_sha}",'
        '"inference_edge_id":"edge-1",'
        '"inference_edge_id":"edge-2",'
        '"result_node_id":"result-1",'
        '"target_node_id":"target-1",'
        '"relation":"supports",'
        '"inference_scope":"structural",'
        '"verifier_id":"domain-verifier",'
        '"rationale":"duplicate-key test",'
        '"limitations":[],"domain_verified":true}'
    ).encode("utf-8")

    with pytest.raises(
        AuthenticatedInferenceBindingError,
        match="duplicate JSON key is not allowed: inference_edge_id",
    ):
        authenticate_inference_binding(
            proposal_bytes=proposal,
            verification_decision_bytes=raw,
            expected_base_graph_sha256="b" * 64,
        )
