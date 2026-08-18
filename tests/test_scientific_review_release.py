from __future__ import annotations

import pytest

from materials_data_analyzer.research_loop.scientific_review_release import (
    ScientificReviewReleaseError,
    build_review_decision,
    build_review_request,
    canonical_sha256,
    verify_review_release,
)


EVIDENCE_SHA = "a" * 64
SEMANTIC_SHA = "b" * 64
LINEAGE_SHA = "c" * 64
INTAKE_SHA = "d" * 64


def _request():
    return build_review_request(
        candidate_id="federated-evidence:test",
        evidence_artifact_sha256=EVIDENCE_SHA,
        semantic_contract_sha256=SEMANTIC_SHA,
        lineage_sha256=LINEAGE_SHA,
        intake_artifact_sha256=INTAKE_SHA,
        requested_uses=["scientific_intake"],
    )


def _verify(request, decision, *, downstream_use: str = "scientific_intake"):
    return verify_review_release(
        request=request,
        decision=decision,
        candidate_id="federated-evidence:test",
        evidence_artifact_sha256=EVIDENCE_SHA,
        semantic_contract_sha256=SEMANTIC_SHA,
        lineage_sha256=LINEAGE_SHA,
        intake_artifact_sha256=INTAKE_SHA,
        downstream_use=downstream_use,
    )


def test_exact_approved_request_releases_only_human_review_blocker() -> None:
    request = _request()
    decision = build_review_decision(
        request,
        reviewer_id="reviewer:test",
        decision="approved",
        allowed_uses=["scientific_intake"],
        excluded_uses=[],
        review_notes="Exact evidence, semantic proposal, lineage proposal, and intake bytes reviewed.",
    )
    result = _verify(request, decision)
    assert result["human_review_blocker_released"] is True
    assert result["scientific_status_changed"] is False
    assert result["scientific_support_established"] is False


def test_changed_semantic_bytes_invalidate_prior_review_release() -> None:
    request = _request()
    decision = build_review_decision(
        request,
        reviewer_id="reviewer:test",
        decision="approved",
        allowed_uses=["scientific_intake"],
        excluded_uses=[],
        review_notes="Exact request reviewed.",
    )
    with pytest.raises(ScientificReviewReleaseError, match="current evidence/semantic/lineage bytes"):
        verify_review_release(
            request=request,
            decision=decision,
            candidate_id="federated-evidence:test",
            evidence_artifact_sha256=EVIDENCE_SHA,
            semantic_contract_sha256="e" * 64,
            lineage_sha256=LINEAGE_SHA,
            intake_artifact_sha256=INTAKE_SHA,
            downstream_use="scientific_intake",
        )


def test_rejected_review_never_releases_requested_use() -> None:
    request = _request()
    decision = build_review_decision(
        request,
        reviewer_id="reviewer:test",
        decision="rejected",
        allowed_uses=[],
        excluded_uses=["scientific_intake"],
        review_notes="Review rejected pending stronger semantic lineage evidence.",
    )
    result = _verify(request, decision)
    assert result["human_review_blocker_released"] is False
    assert result["scientific_status_changed"] is False
    assert result["scientific_support_established"] is False


def test_verifier_rejects_canonical_decision_that_allows_unrequested_use() -> None:
    request = _request()
    decision = build_review_decision(
        request,
        reviewer_id="reviewer:test",
        decision="approved",
        allowed_uses=["scientific_intake"],
        excluded_uses=[],
        review_notes="Exact request reviewed.",
    )
    decision["allowed_uses"] = ["descriptive_analysis"]
    release_without_id = {
        key: value for key, value in decision.items() if key != "review_release_id"
    }
    decision["review_release_id"] = (
        "review-release:" + canonical_sha256(release_without_id)[:24]
    )
    with pytest.raises(ScientificReviewReleaseError, match="subset of requested_uses"):
        _verify(request, decision, downstream_use="descriptive_analysis")
