"""Conservative post-acquisition re-diagnosis for the verified IN625 external source.

This source-specific diagnosis intentionally does not force the real tensile workbook into the
heat-model scalar discrepancy critic.  It verifies that network acquisition, typed source
registration, and reviewed row-level tensile intake all refer to the same exact archive, then
updates only the evidence-availability state.

Real row-level measurements may therefore resolve the *source/row availability* blocker while
leaving physical condition comparability, replicate independence, empirical model validation,
and hypothesis truth unresolved.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .kernel import ResearchLoopError

SCHEMA_VERSION = "1.0"
POLICY_VERSION = "1.0"
EXPECTED_SOURCE_ID = "zenodo-20503603-in625-lpbf-publication-supplement"
EXPECTED_ARCHIVE_SHA256 = "389602211b440cab5142c4071cb3c697702431d9b3aad2dfe2e6500de0a72907"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class In625PostAcquisitionRediagnosisError(ResearchLoopError):
    """Raised when the post-acquisition evidence chain cannot be reconstructed exactly."""


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise In625PostAcquisitionRediagnosisError(f"{field} must be an object")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise In625PostAcquisitionRediagnosisError(f"{field} must be non-empty trimmed text")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if _SHA256_RE.fullmatch(text) is None:
        raise In625PostAcquisitionRediagnosisError(f"{field} must be canonical lowercase SHA-256")
    return text


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise In625PostAcquisitionRediagnosisError(f"{field} must be a positive integer")
    return value


def _canonical_sha(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise In625PostAcquisitionRediagnosisError(
            "post-acquisition diagnosis must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _verified_document(value: Mapping[str, Any], *, field: str, digest_field: str) -> dict[str, Any]:
    document = dict(_mapping(value, field))
    embedded = _sha(document.pop(digest_field, None), f"{field}.{digest_field}")
    actual = _canonical_sha(document)
    if actual != embedded:
        raise In625PostAcquisitionRediagnosisError(
            f"{field} canonical SHA-256 does not match its content"
        )
    document[digest_field] = embedded
    return document


def _load_json(path: str | Path, *, field: str) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = Path(path).expanduser().resolve(strict=True)
    raw = resolved.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise In625PostAcquisitionRediagnosisError(f"{field} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise In625PostAcquisitionRediagnosisError(f"{field} root must be an object")
    return value, {
        "path": str(resolved),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _validate_acquisition_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    value = _verified_document(
        receipt,
        field="network_acquisition_receipt",
        digest_field="receipt_sha256",
    )
    if value.get("source_id") != EXPECTED_SOURCE_ID:
        raise In625PostAcquisitionRediagnosisError("network receipt source identity drifted")
    archive = _mapping(value.get("archive"), "network_acquisition_receipt.archive")
    if (
        archive.get("sha256") != EXPECTED_ARCHIVE_SHA256
        or value.get("network_execution_authorized") is not True
        or value.get("network_access_performed") is not True
        or value.get("exact_host_restriction_enforced") is not True
        or value.get("byte_count_verified") is not True
        or value.get("provider_checksum_verified") is not True
        or value.get("project_sha256_verified") is not True
    ):
        raise In625PostAcquisitionRediagnosisError(
            "network receipt does not establish the exact authorized archive acquisition"
        )
    boundary = _mapping(value.get("scientific_boundary"), "network receipt scientific boundary")
    for key in (
        "sample_identity_established",
        "measurement_semantics_interpreted",
        "replicate_independence_established",
        "direct_nist_condition_comparability_established",
        "empirical_model_validation_established",
        "hypothesis_truth_established",
        "positive_scientific_closeout_established",
        "automatic_scientific_promotion",
    ):
        if boundary.get(key) is not False:
            raise In625PostAcquisitionRediagnosisError(
                f"network receipt improperly widens scientific authority: {key}"
            )
    return value


def _validate_typed_registration(value: Mapping[str, Any]) -> dict[str, Any]:
    registration = dict(_mapping(value, "typed_execution_result"))
    report = _mapping(registration.get("verified_report"), "typed_execution_result.verified_report")
    if (
        report.get("registered_outcome") != "verified_external_source_archive_registered"
        or report.get("archive_sha256") != EXPECTED_ARCHIVE_SHA256
        or report.get("source_provenance_verified") is not True
        or report.get("direct_condition_comparability_established") is not False
        or report.get("empirical_model_validation_established") is not False
        or report.get("scientific_status_changed") is not False
    ):
        raise In625PostAcquisitionRediagnosisError(
            "typed execution result does not preserve the provenance-only registration boundary"
        )
    return registration


def _validate_tensile_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    manifest = _verified_document(
        value,
        field="reviewed_tensile_manifest",
        digest_field="manifest_sha256",
    )
    if (
        manifest.get("source_id") != EXPECTED_SOURCE_ID
        or manifest.get("source_archive_sha256") != EXPECTED_ARCHIVE_SHA256
        or _positive_int(manifest.get("measurement_row_count"), "measurement_row_count") <= 0
        or _positive_int(manifest.get("parallel_test_block_count"), "parallel_test_block_count") <= 0
    ):
        raise In625PostAcquisitionRediagnosisError("reviewed tensile manifest source/row identity drifted")
    semantics = _mapping(manifest.get("reviewed_semantics"), "reviewed_tensile_manifest.reviewed_semantics")
    if (
        semantics.get("sheet_condition_semantics_from_source_readme") is not True
        or semantics.get("measurement_columns_from_exact_workbook_header") is not True
        or semantics.get("parallel_test_independence_established") is not False
    ):
        raise In625PostAcquisitionRediagnosisError(
            "reviewed tensile semantic authority is missing or over-claimed"
        )
    boundaries = _mapping(manifest.get("scientific_boundaries"), "reviewed tensile scientific boundaries")
    if boundaries.get("real_row_level_external_measurements_observed") is not True:
        raise In625PostAcquisitionRediagnosisError("reviewed tensile manifest lacks row-level evidence")
    for key in (
        "direct_nist_condition_comparability_established",
        "empirical_model_validation_established",
        "hypothesis_truth_established",
        "positive_scientific_closeout_established",
        "automatic_scientific_promotion",
    ):
        if boundaries.get(key) is not False:
            raise In625PostAcquisitionRediagnosisError(
                f"reviewed tensile manifest improperly widens scientific authority: {key}"
            )
    return manifest


def build_in625_post_acquisition_rediagnosis(
    *,
    network_authorization: Mapping[str, Any],
    network_receipt: Mapping[str, Any],
    typed_execution_result: Mapping[str, Any],
    reviewed_tensile_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Re-diagnose the next blocker after exact external acquisition and row-level intake."""
    authorization = dict(_mapping(network_authorization, "network_authorization"))
    embedded_authorization_sha = _sha(
        authorization.pop("authorization_sha256", None),
        "network_authorization.authorization_sha256",
    )
    if _canonical_sha(authorization) != embedded_authorization_sha:
        raise In625PostAcquisitionRediagnosisError("network authorization SHA-256 does not match")
    authorization["authorization_sha256"] = embedded_authorization_sha
    if (
        authorization.get("source_id") != EXPECTED_SOURCE_ID
        or authorization.get("authorization_status") != "authorized_exact_archive_download"
        or authorization.get("network_execution_authorized") is not True
        or authorization.get("network_access_performed") is not False
    ):
        raise In625PostAcquisitionRediagnosisError("network authorization semantics drifted")

    receipt = _validate_acquisition_receipt(network_receipt)
    if receipt.get("authorization_sha256") != embedded_authorization_sha:
        raise In625PostAcquisitionRediagnosisError(
            "network receipt is not bound to the supplied authorization certificate"
        )
    registration = _validate_typed_registration(typed_execution_result)
    tensile = _validate_tensile_manifest(reviewed_tensile_manifest)

    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "source_id": EXPECTED_SOURCE_ID,
        "archive_sha256": EXPECTED_ARCHIVE_SHA256,
        "evidence_chain": {
            "network_authorization_sha256": embedded_authorization_sha,
            "network_receipt_sha256": receipt["receipt_sha256"],
            "typed_registration_request_sha256": registration.get("request_sha256"),
            "typed_registration_archive_sha256": registration["verified_report"]["archive_sha256"],
            "reviewed_tensile_manifest_sha256": tensile["manifest_sha256"],
        },
        "resolved_blockers": [
            {
                "code": "empirical_evidence_not_acquired",
                "resolution_scope": "external_source_and_row_level_measurement_availability",
                "resolved": True,
                "basis": (
                    "The exact Zenodo archive was authorized before network access, checksum-bound after download, "
                    "registered in the typed research ledger, and one exact tensile workbook was reviewed into real row-level measurements."
                ),
            }
        ],
        "current_blocker": {
            "code": "cross_source_physical_comparability_not_established",
            "kind": "scientific_comparability",
            "summary": (
                "Real external IN625 tensile rows now exist, but sample/process/protocol equivalence to the target evidence "
                "and replicate independence have not been established."
            ),
        },
        "next_action": {
            "action_class": "reviewed_physical_comparability_assessment",
            "execution_mode": "plan_only_until_exact_comparison_contract_exists",
            "description": (
                "Build a source-to-target process/protocol/sample/response comparability matrix over the reviewed tensile evidence before any residual or model-validation claim."
            ),
            "required_evidence": [
                "Exact target material/process-condition identity",
                "Exact external tensile specimen/process-condition identity",
                "Protocol and response-variable mapping with units",
                "Replicate grouping/independence evidence",
                "Any calibration or uncertainty metadata required by the comparison",
            ],
            "automatic_execution_authorized": False,
        },
        "evidence_state": {
            "real_external_source_acquired": True,
            "real_row_level_measurements_observed": True,
            "measurement_semantics_partially_reviewed": True,
            "replicate_independence_established": False,
            "direct_nist_condition_comparability_established": False,
            "empirical_model_validation_established": False,
            "hypothesis_truth_established": False,
        },
        "stop_state": {
            "status": "continue",
            "reason": (
                "A meaningful new evidence state was reached, but the next scientific bottleneck is physical comparability rather than evidence acquisition."
            ),
            "positive_scientific_closeout": False,
        },
        "scientific_status_changed": False,
    }
    result["rediagnosis_sha256"] = _canonical_sha(result)
    return result


def build_in625_post_acquisition_rediagnosis_from_files(
    *,
    network_authorization_path: str | Path,
    network_receipt_path: str | Path,
    typed_execution_result_path: str | Path,
    reviewed_tensile_manifest_path: str | Path,
) -> dict[str, Any]:
    authorization, _ = _load_json(network_authorization_path, field="network authorization")
    receipt, _ = _load_json(network_receipt_path, field="network acquisition receipt")
    execution, _ = _load_json(typed_execution_result_path, field="typed execution result")
    tensile, _ = _load_json(reviewed_tensile_manifest_path, field="reviewed tensile manifest")
    return build_in625_post_acquisition_rediagnosis(
        network_authorization=authorization,
        network_receipt=receipt,
        typed_execution_result=execution,
        reviewed_tensile_manifest=tensile,
    )


__all__ = [
    "In625PostAcquisitionRediagnosisError",
    "build_in625_post_acquisition_rediagnosis",
    "build_in625_post_acquisition_rediagnosis_from_files",
]
