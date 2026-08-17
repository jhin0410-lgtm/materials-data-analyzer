"""Exact-byte human review release for otherwise fail-closed scientific evidence.

A release records that a human reviewer has examined one exact evidence artifact and
its exact semantic/lineage contracts for specific downstream uses.  Approval removes
only the human-review blocker for those exact bytes and uses; it does not establish
comparability, independence, calibration, scientific support, or engineering readiness.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .kernel import ResearchLoopError

SCIENTIFIC_REVIEW_RELEASE_SCHEMA_VERSION = "1.0"
SCIENTIFIC_REVIEW_POLICY_VERSION = "1.0"
_ALLOWED_DECISIONS = {"approved", "rejected"}
_ALLOWED_USES = {
    "scientific_intake",
    "descriptive_analysis",
    "cross_source_comparison",
    "external_validation",
    "model_training",
    "model_evaluation",
    "hypothesis_support",
    "experiment_planning",
}


class ScientificReviewReleaseError(ResearchLoopError):
    """Raised when an exact review release cannot be authenticated."""


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScientificReviewReleaseError(f"{field} must be non-empty text")
    if value != value.strip():
        raise ScientificReviewReleaseError(f"{field} must not contain edge whitespace")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field).lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ScientificReviewReleaseError(f"{field} must be lowercase SHA-256")
    return text


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
        raise ScientificReviewReleaseError(
            "review release must be canonical-JSON serializable"
        ) from exc


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _uses(values: Sequence[str], field: str) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _text(value, f"{field} item")
        if text not in _ALLOWED_USES:
            raise ScientificReviewReleaseError(
                f"{field} contains unsupported downstream use: {text}"
            )
        if text in result:
            raise ScientificReviewReleaseError(f"{field} must not contain duplicates")
        result.append(text)
    return sorted(result)


def build_review_request(
    *,
    candidate_id: str,
    evidence_artifact_sha256: str,
    semantic_contract_sha256: str,
    lineage_sha256: str,
    intake_artifact_sha256: str | None,
    requested_uses: Sequence[str],
) -> dict[str, Any]:
    uses = _uses(requested_uses, "requested_uses")
    if not uses:
        raise ScientificReviewReleaseError("requested_uses must not be empty")
    request = {
        "schema_version": SCIENTIFIC_REVIEW_RELEASE_SCHEMA_VERSION,
        "policy_version": SCIENTIFIC_REVIEW_POLICY_VERSION,
        "candidate_id": _text(candidate_id, "candidate_id"),
        "evidence_artifact_sha256": _sha(
            evidence_artifact_sha256,
            "evidence_artifact_sha256",
        ),
        "semantic_contract_sha256": _sha(
            semantic_contract_sha256,
            "semantic_contract_sha256",
        ),
        "lineage_sha256": _sha(lineage_sha256, "lineage_sha256"),
        "intake_artifact_sha256": (
            None
            if intake_artifact_sha256 is None
            else _sha(intake_artifact_sha256, "intake_artifact_sha256")
        ),
        "requested_uses": uses,
        "scientific_status_changed": False,
    }
    request["review_request_id"] = "review-request:" + canonical_sha256(request)[:24]
    return request


def build_review_decision(
    request: Mapping[str, Any],
    *,
    reviewer_id: str,
    decision: str,
    allowed_uses: Sequence[str],
    excluded_uses: Sequence[str],
    review_notes: str,
) -> dict[str, Any]:
    validated = validate_review_request(request)
    decision_text = _text(decision, "decision")
    if decision_text not in _ALLOWED_DECISIONS:
        raise ScientificReviewReleaseError(
            f"decision must be one of {sorted(_ALLOWED_DECISIONS)}"
        )
    allowed = _uses(allowed_uses, "allowed_uses")
    excluded = _uses(excluded_uses, "excluded_uses")
    if set(allowed) & set(excluded):
        raise ScientificReviewReleaseError(
            "allowed_uses and excluded_uses must not overlap"
        )
    requested = set(validated["requested_uses"])
    if not set(allowed).issubset(requested):
        raise ScientificReviewReleaseError(
            "allowed_uses must be a subset of requested_uses"
        )
    if decision_text == "rejected" and allowed:
        raise ScientificReviewReleaseError("rejected review cannot allow downstream uses")
    if decision_text == "approved" and not allowed:
        raise ScientificReviewReleaseError("approved review must allow at least one use")
    decision_record = {
        "schema_version": SCIENTIFIC_REVIEW_RELEASE_SCHEMA_VERSION,
        "policy_version": SCIENTIFIC_REVIEW_POLICY_VERSION,
        "review_request_id": validated["review_request_id"],
        "review_request_sha256": canonical_sha256(validated),
        "reviewer_id": _text(reviewer_id, "reviewer_id"),
        "decision": decision_text,
        "allowed_uses": allowed,
        "excluded_uses": excluded,
        "review_notes": _text(review_notes, "review_notes"),
        "scientific_status_changed": False,
        "approval_is_not_scientific_support": True,
    }
    decision_record["review_release_id"] = (
        "review-release:" + canonical_sha256(decision_record)[:24]
    )
    return decision_record


def validate_review_request(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ScientificReviewReleaseError("review request must be an object")
    expected = {
        "schema_version",
        "policy_version",
        "candidate_id",
        "evidence_artifact_sha256",
        "semantic_contract_sha256",
        "lineage_sha256",
        "intake_artifact_sha256",
        "requested_uses",
        "scientific_status_changed",
        "review_request_id",
    }
    if set(value) != expected:
        raise ScientificReviewReleaseError("review request keys do not match schema")
    if value["schema_version"] != SCIENTIFIC_REVIEW_RELEASE_SCHEMA_VERSION:
        raise ScientificReviewReleaseError("unsupported review request schema_version")
    if value["policy_version"] != SCIENTIFIC_REVIEW_POLICY_VERSION:
        raise ScientificReviewReleaseError("unsupported review request policy_version")
    if value["scientific_status_changed"] is not False:
        raise ScientificReviewReleaseError("review request cannot change scientific status")
    candidate_id = _text(value["candidate_id"], "candidate_id")
    evidence_sha = _sha(value["evidence_artifact_sha256"], "evidence_artifact_sha256")
    semantic_sha = _sha(value["semantic_contract_sha256"], "semantic_contract_sha256")
    lineage_sha = _sha(value["lineage_sha256"], "lineage_sha256")
    intake = value["intake_artifact_sha256"]
    intake_sha = None if intake is None else _sha(intake, "intake_artifact_sha256")
    if not isinstance(value["requested_uses"], list):
        raise ScientificReviewReleaseError("requested_uses must be a list")
    uses = _uses(value["requested_uses"], "requested_uses")
    if not uses:
        raise ScientificReviewReleaseError("requested_uses must not be empty")
    normalized = {
        "schema_version": SCIENTIFIC_REVIEW_RELEASE_SCHEMA_VERSION,
        "policy_version": SCIENTIFIC_REVIEW_POLICY_VERSION,
        "candidate_id": candidate_id,
        "evidence_artifact_sha256": evidence_sha,
        "semantic_contract_sha256": semantic_sha,
        "lineage_sha256": lineage_sha,
        "intake_artifact_sha256": intake_sha,
        "requested_uses": uses,
        "scientific_status_changed": False,
    }
    expected_id = "review-request:" + canonical_sha256(normalized)[:24]
    if value["review_request_id"] != expected_id:
        raise ScientificReviewReleaseError("review_request_id does not match exact request")
    normalized["review_request_id"] = expected_id
    return normalized


def verify_review_release(
    *,
    request: Mapping[str, Any],
    decision: Mapping[str, Any],
    candidate_id: str,
    evidence_artifact_sha256: str,
    semantic_contract_sha256: str,
    lineage_sha256: str,
    intake_artifact_sha256: str | None,
    downstream_use: str,
) -> dict[str, Any]:
    validated_request = validate_review_request(request)
    if not isinstance(decision, Mapping):
        raise ScientificReviewReleaseError("review decision must be an object")
    expected_keys = {
        "schema_version",
        "policy_version",
        "review_request_id",
        "review_request_sha256",
        "reviewer_id",
        "decision",
        "allowed_uses",
        "excluded_uses",
        "review_notes",
        "scientific_status_changed",
        "approval_is_not_scientific_support",
        "review_release_id",
    }
    if set(decision) != expected_keys:
        raise ScientificReviewReleaseError("review decision keys do not match schema")
    if decision["schema_version"] != SCIENTIFIC_REVIEW_RELEASE_SCHEMA_VERSION:
        raise ScientificReviewReleaseError("unsupported review decision schema_version")
    if decision["policy_version"] != SCIENTIFIC_REVIEW_POLICY_VERSION:
        raise ScientificReviewReleaseError("unsupported review decision policy_version")
    if decision["scientific_status_changed"] is not False:
        raise ScientificReviewReleaseError("review decision cannot change scientific status")
    if decision["approval_is_not_scientific_support"] is not True:
        raise ScientificReviewReleaseError("review decision must preserve scientific boundary")
    if decision["review_request_id"] != validated_request["review_request_id"]:
        raise ScientificReviewReleaseError("review decision is bound to another request")
    if _sha(decision["review_request_sha256"], "review_request_sha256") != canonical_sha256(
        validated_request
    ):
        raise ScientificReviewReleaseError("review decision request SHA mismatch")
    reviewer_id = _text(decision["reviewer_id"], "reviewer_id")
    decision_text = _text(decision["decision"], "decision")
    if decision_text not in _ALLOWED_DECISIONS:
        raise ScientificReviewReleaseError("unsupported review decision")
    if not isinstance(decision["allowed_uses"], list) or not isinstance(
        decision["excluded_uses"], list
    ):
        raise ScientificReviewReleaseError("review use lists are invalid")
    allowed = _uses(decision["allowed_uses"], "allowed_uses")
    excluded = _uses(decision["excluded_uses"], "excluded_uses")
    notes = _text(decision["review_notes"], "review_notes")
    release_without_id = {
        "schema_version": SCIENTIFIC_REVIEW_RELEASE_SCHEMA_VERSION,
        "policy_version": SCIENTIFIC_REVIEW_POLICY_VERSION,
        "review_request_id": validated_request["review_request_id"],
        "review_request_sha256": canonical_sha256(validated_request),
        "reviewer_id": reviewer_id,
        "decision": decision_text,
        "allowed_uses": allowed,
        "excluded_uses": excluded,
        "review_notes": notes,
        "scientific_status_changed": False,
        "approval_is_not_scientific_support": True,
    }
    expected_release_id = "review-release:" + canonical_sha256(release_without_id)[:24]
    if decision["review_release_id"] != expected_release_id:
        raise ScientificReviewReleaseError("review_release_id does not match exact decision")

    requested_exact = build_review_request(
        candidate_id=candidate_id,
        evidence_artifact_sha256=evidence_artifact_sha256,
        semantic_contract_sha256=semantic_contract_sha256,
        lineage_sha256=lineage_sha256,
        intake_artifact_sha256=intake_artifact_sha256,
        requested_uses=validated_request["requested_uses"],
    )
    if requested_exact != validated_request:
        raise ScientificReviewReleaseError(
            "current evidence/semantic/lineage bytes differ from reviewed request"
        )
    use = _text(downstream_use, "downstream_use")
    if use not in _ALLOWED_USES:
        raise ScientificReviewReleaseError("unsupported downstream_use")
    released = decision_text == "approved" and use in allowed and use not in excluded
    return {
        "review_release_id": expected_release_id,
        "reviewer_id": reviewer_id,
        "downstream_use": use,
        "human_review_blocker_released": released,
        "scientific_status_changed": False,
        "scientific_support_established": False,
        "reason": (
            "exact_review_release_matches_requested_use"
            if released
            else "review_does_not_release_requested_use"
        ),
    }


__all__ = [
    "SCIENTIFIC_REVIEW_POLICY_VERSION",
    "SCIENTIFIC_REVIEW_RELEASE_SCHEMA_VERSION",
    "ScientificReviewReleaseError",
    "build_review_decision",
    "build_review_request",
    "canonical_sha256",
    "validate_review_request",
    "verify_review_release",
]
