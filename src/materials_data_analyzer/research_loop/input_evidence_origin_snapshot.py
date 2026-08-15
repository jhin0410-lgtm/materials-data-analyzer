"""Build self-contained bundle payloads for authenticated input-evidence origin provenance.

This module is producer support only. It reads one exact sidecar request, authenticates
that request against the proposal's legacy input identities and caller-supplied program
state, then snapshots the already-captured evidence/declaration/verification bytes under
fixed bundle-relative paths. The generated index is bound to the exact transition and
proposal SHA-256.

No scientific or empirical authority is granted here.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .evidence_origin_binding import (
    EvidenceOriginBindingError,
    authenticate_evidence_origin_binding,
)
from .input_evidence_origin_request import (
    InputEvidenceOriginRequestError,
    authenticate_input_evidence_origin_request,
)
from .kernel import ResearchLoopError
from .epistemic_transition import _canonical_json_bytes

INPUT_EVIDENCE_ORIGIN_SNAPSHOT_SCHEMA_VERSION = "1.0"
INPUT_EVIDENCE_ORIGIN_REQUEST_SNAPSHOT_PATH = (
    "provenance/current/input_evidence_origin/request.json"
)
INPUT_EVIDENCE_ORIGIN_SNAPSHOT_MANIFEST_PATH = (
    "provenance/current/input_evidence_origin/snapshot_manifest.json"
)
_EMPIRICAL_ORIGIN_CLASSES = frozenset(
    {"empirical_measurement", "external_physical_experiment"}
)


class InputEvidenceOriginSnapshotError(ResearchLoopError):
    """Raised when self-contained input-evidence snapshots cannot be assembled."""


def _strict_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputEvidenceOriginSnapshotError(f"{field} must be a non-empty string")
    if value != value.strip():
        raise InputEvidenceOriginSnapshotError(
            f"{field} must not contain leading or trailing whitespace"
        )
    return value


def _sha256_text(value: object, field: str) -> str:
    text = _strict_text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise InputEvidenceOriginSnapshotError(
            f"{field} must be a canonical lowercase SHA-256 digest"
        )
    return text


def _read_request_bytes(path: str | Path) -> tuple[Path, bytes, str]:
    try:
        request_path = Path(path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise InputEvidenceOriginSnapshotError(
            "input evidence origin request could not be resolved"
        ) from exc
    if not request_path.is_file():
        raise InputEvidenceOriginSnapshotError(
            "input evidence origin request must resolve to a regular file"
        )
    try:
        request_bytes = request_path.read_bytes()
    except OSError as exc:
        raise InputEvidenceOriginSnapshotError(
            "input evidence origin request became unreadable"
        ) from exc
    return request_path, request_bytes, hashlib.sha256(request_bytes).hexdigest()


def _item_prefix(index: int) -> str:
    return f"provenance/current/input_evidence_origin/items/{index:04d}"


def prepare_input_evidence_origin_snapshots(
    *,
    request_path: str | Path,
    proposal_input_evidence_bindings: Sequence[Mapping[str, Any]],
    program_state: Mapping[str, Any],
    artifact_root: str | Path,
    transition_id: str,
    proposal_sha256: str,
) -> dict[str, Any]:
    """Authenticate one sidecar request and return exact bundle payloads + index metadata."""
    transition = _strict_text(transition_id, "transition_id")
    proposal_sha = _sha256_text(proposal_sha256, "proposal_sha256")
    request_source, request_bytes, request_sha = _read_request_bytes(request_path)
    try:
        authenticated = authenticate_input_evidence_origin_request(
            request_bytes=request_bytes,
            proposal_input_evidence_bindings=proposal_input_evidence_bindings,
            program_state=program_state,
            artifact_root=artifact_root,
        )
    except InputEvidenceOriginRequestError as exc:
        raise InputEvidenceOriginSnapshotError(
            "input evidence origin request authentication failed"
        ) from exc

    # Do not use the mutable informational report as authority. Reconstruct the bundle
    # index from exact proposal identities and exact captured payload bytes.
    proposal_bindings = list(proposal_input_evidence_bindings)
    if len(authenticated.payloads) != len(proposal_bindings):
        raise InputEvidenceOriginSnapshotError(
            "authenticated request payload cardinality diverges from proposal input evidence"
        )

    payloads: dict[str, bytes] = {
        INPUT_EVIDENCE_ORIGIN_REQUEST_SNAPSHOT_PATH: request_bytes,
    }
    items: list[dict[str, Any]] = []
    all_empirical = True
    for index, (raw_binding, payload) in enumerate(
        zip(proposal_bindings, authenticated.payloads, strict=True)
    ):
        if not isinstance(raw_binding, Mapping):
            raise InputEvidenceOriginSnapshotError(
                f"proposal input evidence binding {index} must be an object"
            )
        workstream_id = _strict_text(
            raw_binding.get("workstream_id"),
            f"proposal_input_evidence_bindings[{index}].workstream_id",
        )
        role = _strict_text(
            raw_binding.get("role"), f"proposal_input_evidence_bindings[{index}].role"
        )
        evidence_sha = _sha256_text(
            raw_binding.get("sha256"),
            f"proposal_input_evidence_bindings[{index}].sha256",
        )
        if (
            payload.workstream_id != workstream_id
            or payload.role != role
            or payload.evidence_sha256 != evidence_sha
        ):
            raise InputEvidenceOriginSnapshotError(
                "authenticated request payload identity diverges from proposal input evidence"
            )
        actual_evidence_sha = hashlib.sha256(payload.evidence_bytes).hexdigest()
        if actual_evidence_sha != evidence_sha:
            raise InputEvidenceOriginSnapshotError(
                "captured evidence bytes diverge from proposal input evidence SHA-256"
            )
        try:
            origin = authenticate_evidence_origin_binding(
                evidence_bytes=payload.evidence_bytes,
                origin_declaration_bytes=payload.origin_declaration_bytes,
                origin_verification_decision_bytes=payload.origin_verification_decision_bytes,
            )
        except EvidenceOriginBindingError as exc:
            raise InputEvidenceOriginSnapshotError(
                "captured origin provenance could not be independently reconstructed"
            ) from exc
        origin_class = _strict_text(origin.get("origin_class"), "origin_class")
        all_empirical = all_empirical and origin_class in _EMPIRICAL_ORIGIN_CLASSES

        prefix = _item_prefix(index)
        evidence_path = f"{prefix}/evidence.bin"
        declaration_path = f"{prefix}/origin_declaration.json"
        verification_path = f"{prefix}/origin_verification_decision.json"
        payloads[evidence_path] = payload.evidence_bytes
        payloads[declaration_path] = payload.origin_declaration_bytes
        payloads[verification_path] = payload.origin_verification_decision_bytes
        items.append(
            {
                "program_evidence_binding": {
                    "workstream_id": workstream_id,
                    "role": role,
                    "sha256": evidence_sha,
                },
                "origin_class": origin_class,
                "evidence_artifact": {
                    "path": evidence_path,
                    "sha256": actual_evidence_sha,
                    "size_bytes": len(payload.evidence_bytes),
                },
                "origin_declaration_artifact": {
                    "path": declaration_path,
                    "sha256": hashlib.sha256(
                        payload.origin_declaration_bytes
                    ).hexdigest(),
                    "size_bytes": len(payload.origin_declaration_bytes),
                },
                "origin_verification_decision_artifact": {
                    "path": verification_path,
                    "sha256": hashlib.sha256(
                        payload.origin_verification_decision_bytes
                    ).hexdigest(),
                    "size_bytes": len(payload.origin_verification_decision_bytes),
                },
            }
        )

    manifest = {
        "schema_version": INPUT_EVIDENCE_ORIGIN_SNAPSHOT_SCHEMA_VERSION,
        "transition_id": transition,
        "proposal_sha256": proposal_sha,
        "request_artifact": {
            "path": INPUT_EVIDENCE_ORIGIN_REQUEST_SNAPSHOT_PATH,
            "sha256": request_sha,
            "size_bytes": len(request_bytes),
        },
        "items": items,
        "all_origin_classification_records_authenticated": True,
        "all_inputs_empirical_classified": all_empirical,
        "source_request_path": str(request_source),
        "source_request_path_authoritative": False,
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
    manifest_bytes = _canonical_json_bytes(manifest)
    payloads[INPUT_EVIDENCE_ORIGIN_SNAPSHOT_MANIFEST_PATH] = manifest_bytes
    return {
        "manifest": manifest,
        "manifest_bytes": manifest_bytes,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "payloads": payloads,
        "all_inputs_empirical_classified": all_empirical,
        "authority_boundary": {
            "program_state_provenance_reauthenticated": False,
            "physical_origin_truth_authenticated": False,
            "verifier_identity_or_credential_authenticated": False,
            "scientific_result_validity_authenticated": False,
            "support_independence_established": False,
            "empirical_authority_granted": False,
            "scientific_status_changed": False,
            "execution_authorized": False,
            "positive_closeout_granted": False,
        },
    }


__all__ = [
    "INPUT_EVIDENCE_ORIGIN_REQUEST_SNAPSHOT_PATH",
    "INPUT_EVIDENCE_ORIGIN_SNAPSHOT_MANIFEST_PATH",
    "INPUT_EVIDENCE_ORIGIN_SNAPSHOT_SCHEMA_VERSION",
    "InputEvidenceOriginSnapshotError",
    "prepare_input_evidence_origin_snapshots",
]
