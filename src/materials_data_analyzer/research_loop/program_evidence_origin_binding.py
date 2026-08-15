"""Bridge verified program evidence identity to exact evidence-origin provenance.

This module is deliberately narrow. It proves that one legacy program evidence binding
(`workstream_id`, `role`, `sha256`) is present in the supplied verified program state and
that the same exact evidence bytes participate in an authenticated origin-classification
record. It does not convert that provenance into empirical scientific authority.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from .evidence_origin_binding import (
    EvidenceOriginBindingError,
    authenticate_evidence_origin_binding,
)
from .kernel import ResearchLoopError

PROGRAM_EVIDENCE_ORIGIN_BINDING_SCHEMA_VERSION = "1.0"
_PROGRAM_BINDING_KEYS = {"workstream_id", "role", "sha256"}


class ProgramEvidenceOriginBindingError(ResearchLoopError):
    """Raised when program-evidence/origin provenance cannot be joined exactly."""


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProgramEvidenceOriginBindingError(f"{field} must be a non-empty string")
    return value.strip()


def _strict_text(value: object, field: str) -> str:
    text = _text(value, field)
    if value != text:
        raise ProgramEvidenceOriginBindingError(
            f"{field} must not contain leading or trailing whitespace"
        )
    return text


def _sha256_text(value: object, field: str) -> str:
    text = _strict_text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ProgramEvidenceOriginBindingError(
            f"{field} must be a lowercase SHA-256 hex digest"
        )
    return text


def _exact_program_binding(value: object, *, field: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ProgramEvidenceOriginBindingError(f"{field} must be an object")
    missing = sorted(_PROGRAM_BINDING_KEYS - set(value))
    unknown = sorted(set(value) - _PROGRAM_BINDING_KEYS)
    if missing:
        raise ProgramEvidenceOriginBindingError(
            f"{field} is missing required keys: {', '.join(missing)}"
        )
    if unknown:
        raise ProgramEvidenceOriginBindingError(
            f"{field} has unknown keys: {', '.join(unknown)}"
        )
    return {
        "workstream_id": _strict_text(value["workstream_id"], f"{field}.workstream_id"),
        "role": _strict_text(value["role"], f"{field}.role"),
        "sha256": _sha256_text(value["sha256"], f"{field}.sha256"),
    }


def _verified_program_evidence_matches(
    program_state: Mapping[str, Any], binding: Mapping[str, str]
) -> int:
    workstreams = program_state.get("workstreams")
    if not isinstance(workstreams, list):
        raise ProgramEvidenceOriginBindingError(
            "program_state.workstreams must be a list"
        )
    matches = 0
    normalized_workstream_ids: set[str] = set()
    for index, raw_workstream in enumerate(workstreams):
        if not isinstance(raw_workstream, Mapping):
            raise ProgramEvidenceOriginBindingError(
                f"program_state.workstreams[{index}] must be an object"
            )
        raw_id = raw_workstream.get("workstream_id")
        workstream_id = _strict_text(
            raw_id, f"program_state.workstreams[{index}].workstream_id"
        )
        if workstream_id in normalized_workstream_ids:
            raise ProgramEvidenceOriginBindingError(
                "program_state contains duplicate normalized workstream_id values"
            )
        normalized_workstream_ids.add(workstream_id)
        planning_state = raw_workstream.get("planning_state")
        if planning_state is None:
            # `build_research_program()` legitimately uses None for disabled or
            # runtime-context-blocked workstreams; they contribute no evidence.
            continue
        if not isinstance(planning_state, Mapping):
            raise ProgramEvidenceOriginBindingError(
                f"program_state.workstreams[{index}].planning_state must be an object or null"
            )
        evidence_bindings = planning_state.get("evidence_bindings")
        if not isinstance(evidence_bindings, list):
            raise ProgramEvidenceOriginBindingError(
                f"program_state.workstreams[{index}].planning_state.evidence_bindings must be a list"
            )
        seen_local: set[tuple[str, str]] = set()
        for binding_index, raw_binding in enumerate(evidence_bindings):
            if not isinstance(raw_binding, Mapping):
                raise ProgramEvidenceOriginBindingError(
                    "program-state evidence bindings must be objects"
                )
            role = raw_binding.get("role")
            digest = raw_binding.get("sha256")
            if not isinstance(role, str) or not isinstance(digest, str):
                raise ProgramEvidenceOriginBindingError(
                    "program-state evidence bindings require role and sha256 text"
                )
            normalized_role = _strict_text(
                role,
                f"program_state.workstreams[{index}].planning_state.evidence_bindings[{binding_index}].role",
            )
            normalized_sha = _sha256_text(
                digest,
                f"program_state.workstreams[{index}].planning_state.evidence_bindings[{binding_index}].sha256",
            )
            local_key = (normalized_role, normalized_sha)
            if local_key in seen_local:
                raise ProgramEvidenceOriginBindingError(
                    "program_state contains duplicate evidence role/SHA bindings within one workstream"
                )
            seen_local.add(local_key)
            if (
                workstream_id == binding["workstream_id"]
                and normalized_role == binding["role"]
                and normalized_sha == binding["sha256"]
            ):
                matches += 1
    return matches


def authenticate_program_evidence_origin_binding(
    *,
    program_state: Mapping[str, Any],
    program_evidence_binding: Mapping[str, Any],
    evidence_bytes: bytes,
    origin_declaration_bytes: bytes,
    origin_verification_decision_bytes: bytes,
) -> dict[str, Any]:
    """Authenticate one verified program-evidence identity plus its origin record.

    The program state remains an input trust boundary established by the caller's existing
    verified-program workflow. This function only proves exact membership in that state and
    exact SHA identity with the origin-classification evidence bytes.
    """
    if not isinstance(program_state, Mapping):
        raise ProgramEvidenceOriginBindingError("program_state must be an object")
    binding = _exact_program_binding(
        dict(program_evidence_binding), field="program_evidence_binding"
    )
    exact_evidence_sha = hashlib.sha256(evidence_bytes).hexdigest()
    if exact_evidence_sha != binding["sha256"]:
        raise ProgramEvidenceOriginBindingError(
            "program evidence sha256 does not match exact evidence bytes"
        )
    matches = _verified_program_evidence_matches(program_state, binding)
    if matches != 1:
        if matches == 0:
            raise ProgramEvidenceOriginBindingError(
                "program evidence binding is not present in the supplied verified program state"
            )
        raise ProgramEvidenceOriginBindingError(
            "program evidence binding is ambiguous in the supplied verified program state"
        )
    try:
        origin = authenticate_evidence_origin_binding(
            evidence_bytes=evidence_bytes,
            origin_declaration_bytes=origin_declaration_bytes,
            origin_verification_decision_bytes=origin_verification_decision_bytes,
        )
    except EvidenceOriginBindingError as exc:
        raise ProgramEvidenceOriginBindingError(
            "evidence-origin classification could not be authenticated"
        ) from exc
    if origin.get("evidence_artifact_sha256") != binding["sha256"]:
        raise ProgramEvidenceOriginBindingError(
            "origin binding evidence digest diverges from verified program evidence"
        )

    return {
        "schema_version": PROGRAM_EVIDENCE_ORIGIN_BINDING_SCHEMA_VERSION,
        "program_evidence_binding": dict(binding),
        "evidence_origin_binding": dict(origin),
        "origin_class": origin["origin_class"],
        "verified_program_state_membership_established": True,
        "exact_evidence_identity_joined": True,
        "origin_classification_record_authenticated": True,
        "program_state_provenance_reauthenticated": False,
        "physical_origin_truth_authenticated": False,
        "verifier_identity_or_credential_authenticated": False,
        "scientific_result_validity_authenticated": False,
        "support_independence_established": False,
        "empirical_authority_granted": False,
        "scientific_status_changed": False,
        "execution_authorized": False,
        "positive_closeout_granted": False,
    }


__all__ = [
    "PROGRAM_EVIDENCE_ORIGIN_BINDING_SCHEMA_VERSION",
    "ProgramEvidenceOriginBindingError",
    "authenticate_program_evidence_origin_binding",
]
