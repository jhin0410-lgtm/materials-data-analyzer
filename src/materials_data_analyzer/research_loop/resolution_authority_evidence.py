"""Exact authority-evidence gate for reviewed generic scientific resolutions.

A reviewed mapping is not itself proof that the source declared the mapped semantics.
This module binds each positive semantic/physical-lineage claim to an exact byte-range
witness in an exact authority artifact.  Authority review is a second release gate: it
cannot replace the existing resolved-mapping review and neither review establishes
scientific support.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .kernel import ResearchLoopError
from .reviewed_resolution_compiler import compile_reviewed_resolution
from .reviewed_xlsx_resolution_compiler import compile_reviewed_xlsx_resolution

RESOLUTION_AUTHORITY_SCHEMA_VERSION = "1.0"
_AUTHORITY_POLICY_VERSION = "1.0"
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_CLAIMS = {
    "material_identity",
    "sample_identity",
    "property_semantics",
    "unit",
    "method",
    "instrument_model",
    "calibration",
    "process_signature",
    "standard_uncertainty",
    "specimen_identity",
    "acquisition_identity",
    "lab_identity",
    "material_lot_identity",
    "build_or_synthesis_identity",
    "process_run_identity",
}


class ResolutionAuthorityEvidenceError(ResearchLoopError):
    """Raised when source authority cannot be authenticated exactly."""


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
        raise ResolutionAuthorityEvidenceError(
            "authority content must be canonical-JSON serializable"
        ) from exc


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ResolutionAuthorityEvidenceError(f"{field} must be non-empty trimmed text")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field).lower()
    if not _SHA_RE.fullmatch(text):
        raise ResolutionAuthorityEvidenceError(f"{field} must be lowercase SHA-256")
    return text


def _resolution_parts(resolution_contract: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    semantic_contract = resolution_contract.get("semantic_resolution_contract")
    lineage_contract = resolution_contract.get("lineage_resolution_contract")
    if not isinstance(semantic_contract, Mapping) or not isinstance(lineage_contract, Mapping):
        raise ResolutionAuthorityEvidenceError("resolution contract is malformed")
    semantic = semantic_contract.get("resolution")
    lineage = lineage_contract.get("resolution")
    if not isinstance(semantic, Mapping) or not isinstance(lineage, Mapping):
        raise ResolutionAuthorityEvidenceError("resolution payload is malformed")
    return semantic, lineage


def _required_claim_values(resolution_contract: Mapping[str, Any]) -> dict[str, Any]:
    semantic, lineage = _resolution_parts(resolution_contract)
    material = semantic.get("material")
    if not isinstance(material, Mapping):
        raise ResolutionAuthorityEvidenceError("material resolution is malformed")
    uncertainty = semantic.get("standard_uncertainty")
    if not isinstance(uncertainty, Mapping):
        raise ResolutionAuthorityEvidenceError("uncertainty resolution is malformed")
    required: dict[str, Any] = {
        "material_identity": dict(material),
        "sample_identity": {"column_index": semantic.get("sample_id_column")},
        "property_semantics": {
            "property_name": semantic.get("property_name"),
            "value_column": semantic.get("value_column"),
        },
        "unit": semantic.get("unit"),
        "method": semantic.get("method"),
        "instrument_model": semantic.get("instrument_model"),
        "specimen_identity": {"column_index": lineage.get("specimen_id_column")},
        "acquisition_identity": {"column_index": lineage.get("acquisition_id_column")},
    }
    if semantic.get("calibration_status") == "explicit_identifier":
        required["calibration"] = {
            "status": "explicit_identifier",
            "calibration_id": semantic.get("calibration_id"),
        }
    if semantic.get("process_signature") is not None:
        required["process_signature"] = semantic.get("process_signature")
    if uncertainty.get("mode") != "none":
        required["standard_uncertainty"] = dict(uncertainty)
    optional_lineage = {
        "lab_identity": "lab_id_column",
        "material_lot_identity": "material_lot_id_column",
        "build_or_synthesis_identity": "build_or_synthesis_id_column",
        "process_run_identity": "process_run_id_column",
    }
    for claim, field in optional_lineage.items():
        if lineage.get(field) is not None:
            required[claim] = {"column_index": lineage.get(field)}
    return required


def _normalize_authority_record(
    value: object,
    *,
    authority_artifacts: Mapping[str, bytes],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ResolutionAuthorityEvidenceError("authority record must be an object")
    expected_keys = {
        "claim_kind",
        "authorized_value",
        "authority_artifact_sha256",
        "byte_start",
        "byte_end",
        "witness_text",
    }
    if set(value) != expected_keys:
        raise ResolutionAuthorityEvidenceError("authority record keys do not match schema")
    claim = _text(value.get("claim_kind"), "claim_kind")
    if claim not in _ALLOWED_CLAIMS:
        raise ResolutionAuthorityEvidenceError(f"unsupported authority claim: {claim}")
    artifact_sha = _sha(value.get("authority_artifact_sha256"), "authority_artifact_sha256")
    artifact = authority_artifacts.get(artifact_sha)
    if not isinstance(artifact, bytes) or not artifact:
        raise ResolutionAuthorityEvidenceError(
            "authority artifact bytes are missing for declared SHA-256"
        )
    if hashlib.sha256(artifact).hexdigest() != artifact_sha:
        raise ResolutionAuthorityEvidenceError("authority artifact bytes do not match declared SHA-256")
    start = value.get("byte_start")
    end = value.get("byte_end")
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
        or start < 0
        or end <= start
        or end > len(artifact)
    ):
        raise ResolutionAuthorityEvidenceError("authority byte range is invalid")
    witness = _text(value.get("witness_text"), "witness_text")
    witness_bytes = witness.encode("utf-8")
    if artifact[start:end] != witness_bytes:
        raise ResolutionAuthorityEvidenceError(
            "authority witness text does not match exact artifact byte range"
        )
    authorized_value = value.get("authorized_value")
    value_sha = _canonical_sha(authorized_value)
    record: dict[str, Any] = {
        "claim_kind": claim,
        "authorized_value": authorized_value,
        "authorized_value_sha256": value_sha,
        "authority_artifact_sha256": artifact_sha,
        "record_locator": f"bytes:{start}-{end}",
        "byte_start": start,
        "byte_end": end,
        "witness_sha256": hashlib.sha256(witness_bytes).hexdigest(),
        "witness_text": witness,
        "witness_is_exact_artifact_slice": True,
        "semantic_inference_performed": False,
    }
    record["authority_record_sha256"] = _canonical_sha(record)
    return record


def build_resolution_authority_packet(
    *,
    resolution_contract: Mapping[str, Any],
    authority_records: Sequence[Mapping[str, Any]],
    authority_artifacts: Mapping[str, bytes],
) -> dict[str, Any]:
    """Require exact source witnesses for every positive reviewed-resolution claim."""
    required = _required_claim_values(resolution_contract)
    if not authority_records:
        raise ResolutionAuthorityEvidenceError("authority_records must not be empty")
    normalized = [
        _normalize_authority_record(item, authority_artifacts=authority_artifacts)
        for item in authority_records
    ]
    by_claim: dict[str, list[dict[str, Any]]] = {}
    for item in normalized:
        by_claim.setdefault(item["claim_kind"], []).append(item)

    missing: list[str] = []
    conflicts: list[str] = []
    expected_hashes = {claim: _canonical_sha(value) for claim, value in required.items()}
    for claim, expected_sha in expected_hashes.items():
        records = by_claim.get(claim, [])
        if not records:
            missing.append(claim)
            continue
        observed = {item["authorized_value_sha256"] for item in records}
        if observed != {expected_sha}:
            conflicts.append(claim)
    unexpected = sorted(set(by_claim) - set(required))
    if missing:
        raise ResolutionAuthorityEvidenceError(
            "required resolution authority is missing: " + ", ".join(sorted(missing))
        )
    if conflicts:
        raise ResolutionAuthorityEvidenceError(
            "authority evidence conflicts with reviewed resolution: "
            + ", ".join(sorted(conflicts))
        )
    if unexpected:
        raise ResolutionAuthorityEvidenceError(
            "authority records claim unresolved/non-required fields: " + ", ".join(unexpected)
        )

    packet: dict[str, Any] = {
        "schema_version": RESOLUTION_AUTHORITY_SCHEMA_VERSION,
        "policy_version": _AUTHORITY_POLICY_VERSION,
        "candidate_id": resolution_contract.get("candidate_id"),
        "evidence_artifact_sha256": resolution_contract.get("evidence_artifact_sha256"),
        "semantic_resolution_sha256": resolution_contract.get("semantic_resolution_sha256"),
        "lineage_resolution_sha256": resolution_contract.get("lineage_resolution_sha256"),
        "resolution_packet_sha256": resolution_contract.get("resolution_packet_sha256"),
        "required_claim_value_sha256": expected_hashes,
        "authority_records": sorted(
            normalized,
            key=lambda item: (
                item["claim_kind"],
                item["authority_artifact_sha256"],
                item["byte_start"],
            ),
        ),
        "missing_required_authority": [],
        "authority_conflicts": [],
        "all_positive_resolution_claims_source_authorized": True,
        "human_review_decision_created": False,
        "authority_review_released": False,
        "authority_review_is_scientific_support": False,
        "scientific_support_established": False,
        "scientific_status_changed": False,
    }
    packet["authority_packet_sha256"] = _canonical_sha(packet)
    return packet


def verify_resolution_authority_packet(
    *,
    resolution_contract: Mapping[str, Any],
    authority_packet: Mapping[str, Any],
    authority_artifacts: Mapping[str, bytes],
) -> dict[str, Any]:
    if not isinstance(authority_packet, Mapping):
        raise ResolutionAuthorityEvidenceError("authority_packet must be an object")
    records = authority_packet.get("authority_records")
    if not isinstance(records, list):
        raise ResolutionAuthorityEvidenceError("authority_packet records are malformed")
    reconstructed_inputs = [
        {
            "claim_kind": item.get("claim_kind"),
            "authorized_value": item.get("authorized_value"),
            "authority_artifact_sha256": item.get("authority_artifact_sha256"),
            "byte_start": item.get("byte_start"),
            "byte_end": item.get("byte_end"),
            "witness_text": item.get("witness_text"),
        }
        for item in records
        if isinstance(item, Mapping)
    ]
    if len(reconstructed_inputs) != len(records):
        raise ResolutionAuthorityEvidenceError("authority_packet contains malformed record")
    rebuilt = build_resolution_authority_packet(
        resolution_contract=resolution_contract,
        authority_records=reconstructed_inputs,
        authority_artifacts=authority_artifacts,
    )
    if dict(authority_packet) != rebuilt:
        raise ResolutionAuthorityEvidenceError("authority packet bytes differ from exact reconstruction")
    result = dict(rebuilt)
    result["exact_authority_binding_verified"] = True
    return result


def build_authority_review_request(
    *,
    resolution_contract: Mapping[str, Any],
    authority_packet: Mapping[str, Any],
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "schema_version": RESOLUTION_AUTHORITY_SCHEMA_VERSION,
        "policy_version": _AUTHORITY_POLICY_VERSION,
        "candidate_id": _text(resolution_contract.get("candidate_id"), "candidate_id"),
        "evidence_artifact_sha256": _sha(
            resolution_contract.get("evidence_artifact_sha256"),
            "evidence_artifact_sha256",
        ),
        "semantic_resolution_sha256": _sha(
            resolution_contract.get("semantic_resolution_sha256"),
            "semantic_resolution_sha256",
        ),
        "lineage_resolution_sha256": _sha(
            resolution_contract.get("lineage_resolution_sha256"),
            "lineage_resolution_sha256",
        ),
        "authority_packet_sha256": _sha(
            authority_packet.get("authority_packet_sha256"),
            "authority_packet_sha256",
        ),
        "requested_use": "scientific_intake_authority_gate",
        "scientific_status_changed": False,
    }
    request["authority_review_request_id"] = (
        "authority-review-request:" + _canonical_sha(request)[:24]
    )
    return request


def build_authority_review_decision(
    request: Mapping[str, Any],
    *,
    reviewer_id: str,
    decision: str,
    review_notes: str,
) -> dict[str, Any]:
    decision_text = _text(decision, "decision")
    if decision_text not in {"approved", "rejected"}:
        raise ResolutionAuthorityEvidenceError("authority review decision is unsupported")
    validated = dict(request)
    expected_request = build_authority_review_request(
        resolution_contract={
            "candidate_id": request.get("candidate_id"),
            "evidence_artifact_sha256": request.get("evidence_artifact_sha256"),
            "semantic_resolution_sha256": request.get("semantic_resolution_sha256"),
            "lineage_resolution_sha256": request.get("lineage_resolution_sha256"),
        },
        authority_packet={"authority_packet_sha256": request.get("authority_packet_sha256")},
    )
    if validated != expected_request:
        raise ResolutionAuthorityEvidenceError("authority review request is not canonical")
    record: dict[str, Any] = {
        "schema_version": RESOLUTION_AUTHORITY_SCHEMA_VERSION,
        "policy_version": _AUTHORITY_POLICY_VERSION,
        "authority_review_request_id": request["authority_review_request_id"],
        "authority_review_request_sha256": _canonical_sha(request),
        "reviewer_id": _text(reviewer_id, "reviewer_id"),
        "decision": decision_text,
        "review_notes": _text(review_notes, "review_notes"),
        "approval_is_not_scientific_support": True,
        "scientific_status_changed": False,
    }
    record["authority_review_release_id"] = (
        "authority-review-release:" + _canonical_sha(record)[:24]
    )
    return record


def verify_authority_review_release(
    *,
    resolution_contract: Mapping[str, Any],
    authority_packet: Mapping[str, Any],
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    expected_request = build_authority_review_request(
        resolution_contract=resolution_contract,
        authority_packet=authority_packet,
    )
    if not isinstance(decision, Mapping):
        raise ResolutionAuthorityEvidenceError("authority review decision must be an object")
    without_id = {key: value for key, value in decision.items() if key != "authority_review_release_id"}
    expected_release_id = "authority-review-release:" + _canonical_sha(without_id)[:24]
    if decision.get("authority_review_release_id") != expected_release_id:
        raise ResolutionAuthorityEvidenceError("authority review release ID does not match exact decision")
    if decision.get("authority_review_request_id") != expected_request["authority_review_request_id"]:
        raise ResolutionAuthorityEvidenceError("authority review decision is bound to another request")
    if decision.get("authority_review_request_sha256") != _canonical_sha(expected_request):
        raise ResolutionAuthorityEvidenceError("authority review request SHA mismatch")
    if decision.get("approval_is_not_scientific_support") is not True:
        raise ResolutionAuthorityEvidenceError("authority review must preserve scientific boundary")
    if decision.get("scientific_status_changed") is not False:
        raise ResolutionAuthorityEvidenceError("authority review cannot change scientific status")
    released = decision.get("decision") == "approved"
    return {
        "authority_review_release_id": expected_release_id,
        "reviewer_id": decision.get("reviewer_id"),
        "authority_review_released": released,
        "authority_review_is_scientific_support": False,
        "scientific_support_established": False,
        "scientific_status_changed": False,
        "reason": (
            "exact_authority_review_release_verified"
            if released
            else "authority_review_rejected"
        ),
    }


def _authority_gate(
    *,
    resolution_contract: Mapping[str, Any],
    authority_packet: Mapping[str, Any],
    authority_artifacts: Mapping[str, bytes],
    authority_review_decision: Mapping[str, Any],
) -> dict[str, Any]:
    verified = verify_resolution_authority_packet(
        resolution_contract=resolution_contract,
        authority_packet=authority_packet,
        authority_artifacts=authority_artifacts,
    )
    release = verify_authority_review_release(
        resolution_contract=resolution_contract,
        authority_packet=verified,
        decision=authority_review_decision,
    )
    if release["authority_review_released"] is not True:
        raise ResolutionAuthorityEvidenceError("authority review does not release normalization")
    return release


def compile_authority_bound_delimited_resolution(
    *,
    artifact_bytes: bytes,
    structure: Mapping[str, Any],
    proposal: Mapping[str, Any],
    resolution_contract: Mapping[str, Any],
    resolution_review_decision: Mapping[str, Any],
    authority_packet: Mapping[str, Any],
    authority_artifacts: Mapping[str, bytes],
    authority_review_decision: Mapping[str, Any],
) -> dict[str, Any]:
    release = _authority_gate(
        resolution_contract=resolution_contract,
        authority_packet=authority_packet,
        authority_artifacts=authority_artifacts,
        authority_review_decision=authority_review_decision,
    )
    manifest = compile_reviewed_resolution(
        artifact_bytes=artifact_bytes,
        structure=structure,
        proposal=proposal,
        resolution_contract=resolution_contract,
        review_decision=resolution_review_decision,
    )
    manifest["authority_packet_sha256"] = authority_packet["authority_packet_sha256"]
    manifest["authority_review_release_id"] = release["authority_review_release_id"]
    manifest["all_positive_resolution_claims_source_authorized"] = True
    manifest["authority_review_is_scientific_support"] = False
    manifest["scientific_support_established"] = False
    manifest["scientific_status_changed"] = False
    manifest["normalized_evidence_manifest_sha256"] = _canonical_sha(
        {key: value for key, value in manifest.items() if key != "normalized_evidence_manifest_sha256"}
    )
    return manifest


def compile_authority_bound_xlsx_resolution(
    *,
    workbook_bytes: bytes,
    xlsx_row_report: Mapping[str, Any],
    proposal: Mapping[str, Any],
    resolution_contract: Mapping[str, Any],
    resolution_review_decision: Mapping[str, Any],
    authority_packet: Mapping[str, Any],
    authority_artifacts: Mapping[str, bytes],
    authority_review_decision: Mapping[str, Any],
) -> dict[str, Any]:
    release = _authority_gate(
        resolution_contract=resolution_contract,
        authority_packet=authority_packet,
        authority_artifacts=authority_artifacts,
        authority_review_decision=authority_review_decision,
    )
    manifest = compile_reviewed_xlsx_resolution(
        workbook_bytes=workbook_bytes,
        xlsx_row_report=xlsx_row_report,
        proposal=proposal,
        resolution_contract=resolution_contract,
        review_decision=resolution_review_decision,
    )
    manifest["authority_packet_sha256"] = authority_packet["authority_packet_sha256"]
    manifest["authority_review_release_id"] = release["authority_review_release_id"]
    manifest["all_positive_resolution_claims_source_authorized"] = True
    manifest["authority_review_is_scientific_support"] = False
    manifest["scientific_support_established"] = False
    manifest["scientific_status_changed"] = False
    manifest["normalized_evidence_manifest_sha256"] = _canonical_sha(
        {key: value for key, value in manifest.items() if key != "normalized_evidence_manifest_sha256"}
    )
    return manifest


__all__ = [
    "RESOLUTION_AUTHORITY_SCHEMA_VERSION",
    "ResolutionAuthorityEvidenceError",
    "build_authority_review_decision",
    "build_authority_review_request",
    "build_resolution_authority_packet",
    "compile_authority_bound_delimited_resolution",
    "compile_authority_bound_xlsx_resolution",
    "verify_authority_review_release",
    "verify_resolution_authority_packet",
]
