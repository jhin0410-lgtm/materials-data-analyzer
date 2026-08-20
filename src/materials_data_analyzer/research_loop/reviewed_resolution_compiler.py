"""Compile explicitly resolved and reviewed generic tabular evidence into strict records.

This module is an acceptance/compiler layer, not a semantic inference layer.  A generic
proposal cannot be compiled directly.  Scientific fields and physical identity columns
must be supplied explicitly in a resolution contract, that exact resolution receives a
new scientific-intake review request, and only an exact approved release for that request
can unlock normalization.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from collections.abc import Mapping
from typing import Any

from .delimited_structural_intake import inspect_delimited_structure
from .experimental_lineage import ObservationLineage, effective_independent_unit
from .generic_semantic_lineage_proposal import (
    GenericSemanticLineageProposalError,
    verify_generic_semantic_lineage_proposal,
)
from .kernel import ResearchLoopError
from .scientific_evidence_normalization import (
    MaterialIdentity,
    NormalizedMeasurement,
    ProvenanceLocator,
    ScientificEvidenceNormalizationError,
)
from .scientific_review_release import (
    ScientificReviewReleaseError,
    build_review_request,
    verify_review_release,
)

REVIEWED_RESOLUTION_COMPILER_SCHEMA_VERSION = "1.0"
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_IDENTITY_AUTHORITY = "authoritative_source_column"
_CALIBRATION_STATUSES = {"explicit_identifier", "not_reported_no_claim"}
_UNCERTAINTY_MODES = {"none", "constant", "column"}


class ReviewedResolutionCompilerError(ResearchLoopError):
    """Raised when explicit reviewed resolution cannot be compiled safely."""


def _canonical_sha(value: object) -> str:
    try:
        body = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReviewedResolutionCompilerError(
            "resolution content must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(body).hexdigest()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ReviewedResolutionCompilerError(
            f"{field} must be non-empty trimmed text"
        )
    return value


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if not _SHA_RE.fullmatch(text):
        raise ReviewedResolutionCompilerError(f"{field} must be lowercase SHA-256")
    return text


def _column(value: object, field: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < maximum:
        raise ReviewedResolutionCompilerError(
            f"{field} must be a valid zero-based source column index"
        )
    return value


def _optional_column(value: object, field: str, *, maximum: int) -> int | None:
    if value is None:
        return None
    return _column(value, field, maximum=maximum)


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReviewedResolutionCompilerError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ReviewedResolutionCompilerError(f"{field} must be finite")
    return result


def _exact_keys(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    if set(value) != expected:
        raise ReviewedResolutionCompilerError(f"{field} keys do not match schema")


def _structure_width(structure: Mapping[str, Any]) -> int:
    width = structure.get("maximum_column_count")
    if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
        raise ReviewedResolutionCompilerError("structure maximum_column_count is invalid")
    if structure.get("rectangular") is not True:
        raise ReviewedResolutionCompilerError(
            "resolved normalization requires a rectangular generic structure"
        )
    return width


def _normalize_material(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ReviewedResolutionCompilerError("semantic_resolution.material must be an object")
    _exact_keys(
        value,
        {"kind", "material_name", "declared_identifier", "identity_basis"},
        "semantic_resolution.material",
    )
    if value.get("kind") != "identity":
        raise ReviewedResolutionCompilerError(
            "generic resolution currently accepts only explicit MaterialIdentity"
        )
    material = MaterialIdentity(
        material_name=_text(value.get("material_name"), "material.material_name"),
        declared_identifier=_text(
            value.get("declared_identifier"),
            "material.declared_identifier",
        ),
        identity_basis=_text(value.get("identity_basis"), "material.identity_basis"),
    )
    return {
        "kind": "identity",
        "material_name": material.material_name,
        "declared_identifier": material.declared_identifier,
        "identity_basis": material.identity_basis,
    }


def _normalize_uncertainty(value: object, *, maximum: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ReviewedResolutionCompilerError(
            "semantic_resolution.standard_uncertainty must be an object"
        )
    mode = _text(value.get("mode"), "standard_uncertainty.mode")
    if mode not in _UNCERTAINTY_MODES:
        raise ReviewedResolutionCompilerError("unsupported standard_uncertainty mode")
    if mode == "none":
        _exact_keys(value, {"mode"}, "standard_uncertainty")
        return {"mode": "none"}
    if mode == "constant":
        _exact_keys(value, {"mode", "value"}, "standard_uncertainty")
        number = _finite(value.get("value"), "standard_uncertainty.value")
        if number < 0:
            raise ReviewedResolutionCompilerError(
                "standard_uncertainty constant must be non-negative"
            )
        return {"mode": "constant", "value": number}
    _exact_keys(value, {"mode", "column_index"}, "standard_uncertainty")
    return {
        "mode": "column",
        "column_index": _column(
            value.get("column_index"),
            "standard_uncertainty.column_index",
            maximum=maximum,
        ),
    }


def _normalize_semantic_resolution(
    value: object,
    *,
    maximum: int,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ReviewedResolutionCompilerError("semantic_resolution must be an object")
    expected = {
        "source_id",
        "material",
        "sample_id_column",
        "sample_identity_authority",
        "property_name",
        "value_column",
        "unit",
        "method",
        "instrument_model",
        "calibration_status",
        "calibration_id",
        "process_signature",
        "standard_uncertainty",
    }
    _exact_keys(value, expected, "semantic_resolution")
    if value.get("sample_identity_authority") != _IDENTITY_AUTHORITY:
        raise ReviewedResolutionCompilerError(
            "sample identity requires explicit authoritative_source_column authority"
        )
    calibration_status = _text(
        value.get("calibration_status"),
        "semantic_resolution.calibration_status",
    )
    if calibration_status not in _CALIBRATION_STATUSES:
        raise ReviewedResolutionCompilerError("unsupported calibration_status")
    calibration_id = _optional_text(
        value.get("calibration_id"),
        "semantic_resolution.calibration_id",
    )
    if calibration_status == "explicit_identifier" and calibration_id is None:
        raise ReviewedResolutionCompilerError(
            "explicit_identifier calibration_status requires calibration_id"
        )
    if calibration_status == "not_reported_no_claim" and calibration_id is not None:
        raise ReviewedResolutionCompilerError(
            "not_reported_no_claim calibration_status requires calibration_id=null"
        )
    return {
        "source_id": _text(value.get("source_id"), "semantic_resolution.source_id"),
        "material": _normalize_material(value.get("material")),
        "sample_id_column": _column(
            value.get("sample_id_column"),
            "semantic_resolution.sample_id_column",
            maximum=maximum,
        ),
        "sample_identity_authority": _IDENTITY_AUTHORITY,
        "property_name": _text(
            value.get("property_name"),
            "semantic_resolution.property_name",
        ),
        "value_column": _column(
            value.get("value_column"),
            "semantic_resolution.value_column",
            maximum=maximum,
        ),
        "unit": _text(value.get("unit"), "semantic_resolution.unit"),
        "method": _text(value.get("method"), "semantic_resolution.method"),
        "instrument_model": _text(
            value.get("instrument_model"),
            "semantic_resolution.instrument_model",
        ),
        "calibration_status": calibration_status,
        "calibration_id": calibration_id,
        "process_signature": _optional_text(
            value.get("process_signature"),
            "semantic_resolution.process_signature",
        ),
        "standard_uncertainty": _normalize_uncertainty(
            value.get("standard_uncertainty"),
            maximum=maximum,
        ),
    }


def _normalize_lineage_resolution(
    value: object,
    *,
    maximum: int,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ReviewedResolutionCompilerError("lineage_resolution must be an object")
    expected = {
        "specimen_id_column",
        "specimen_identity_authority",
        "acquisition_id_column",
        "acquisition_identity_authority",
        "lab_id_column",
        "material_lot_id_column",
        "build_or_synthesis_id_column",
        "process_run_id_column",
    }
    _exact_keys(value, expected, "lineage_resolution")
    if value.get("specimen_identity_authority") != _IDENTITY_AUTHORITY:
        raise ReviewedResolutionCompilerError(
            "specimen identity requires explicit authoritative_source_column authority"
        )
    if value.get("acquisition_identity_authority") != _IDENTITY_AUTHORITY:
        raise ReviewedResolutionCompilerError(
            "acquisition identity requires explicit authoritative_source_column authority"
        )
    return {
        "specimen_id_column": _column(
            value.get("specimen_id_column"),
            "lineage_resolution.specimen_id_column",
            maximum=maximum,
        ),
        "specimen_identity_authority": _IDENTITY_AUTHORITY,
        "acquisition_id_column": _column(
            value.get("acquisition_id_column"),
            "lineage_resolution.acquisition_id_column",
            maximum=maximum,
        ),
        "acquisition_identity_authority": _IDENTITY_AUTHORITY,
        "lab_id_column": _optional_column(
            value.get("lab_id_column"),
            "lineage_resolution.lab_id_column",
            maximum=maximum,
        ),
        "material_lot_id_column": _optional_column(
            value.get("material_lot_id_column"),
            "lineage_resolution.material_lot_id_column",
            maximum=maximum,
        ),
        "build_or_synthesis_id_column": _optional_column(
            value.get("build_or_synthesis_id_column"),
            "lineage_resolution.build_or_synthesis_id_column",
            maximum=maximum,
        ),
        "process_run_id_column": _optional_column(
            value.get("process_run_id_column"),
            "lineage_resolution.process_run_id_column",
            maximum=maximum,
        ),
    }


def build_reviewed_resolution_contract(
    *,
    structure: Mapping[str, Any],
    proposal: Mapping[str, Any],
    semantic_resolution: Mapping[str, Any],
    lineage_resolution: Mapping[str, Any],
) -> dict[str, Any]:
    """Build an exact explicit resolution and a *new* review request for it."""
    try:
        verified_proposal = verify_generic_semantic_lineage_proposal(
            structure=structure,
            proposal=proposal,
        )
    except GenericSemanticLineageProposalError as exc:
        raise ReviewedResolutionCompilerError(
            "generic proposal is not exact or proposal-only"
        ) from exc
    maximum = _structure_width(structure)
    semantic = _normalize_semantic_resolution(
        semantic_resolution,
        maximum=maximum,
    )
    lineage = _normalize_lineage_resolution(
        lineage_resolution,
        maximum=maximum,
    )
    candidate_id = _text(proposal.get("candidate_id"), "proposal.candidate_id")
    evidence_sha = _sha(
        proposal.get("evidence_artifact_sha256"),
        "proposal.evidence_artifact_sha256",
    )
    intake_sha = _sha(
        proposal.get("structural_intake_sha256"),
        "proposal.structural_intake_sha256",
    )
    proposal_packet_sha = _sha(
        proposal.get("proposal_packet_sha256"),
        "proposal.proposal_packet_sha256",
    )
    if proposal_packet_sha != verified_proposal["proposal_packet_sha256"]:
        raise ReviewedResolutionCompilerError("proposal packet SHA binding failed")

    semantic_contract = {
        "schema_version": REVIEWED_RESOLUTION_COMPILER_SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "evidence_artifact_sha256": evidence_sha,
        "structural_intake_sha256": intake_sha,
        "proposal_packet_sha256": proposal_packet_sha,
        "resolution": semantic,
        "semantic_values_inferred": False,
        "candidate_id_used_as_sample_identity": False,
        "filename_or_row_number_used_as_sample_identity": False,
        "scientific_status_changed": False,
    }
    semantic_sha = _canonical_sha(semantic_contract)
    lineage_contract = {
        "schema_version": REVIEWED_RESOLUTION_COMPILER_SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "evidence_artifact_sha256": evidence_sha,
        "structural_intake_sha256": intake_sha,
        "proposal_packet_sha256": proposal_packet_sha,
        "semantic_resolution_sha256": semantic_sha,
        "resolution": lineage,
        "physical_identity_inferred": False,
        "candidate_id_used_as_specimen_identity": False,
        "filename_or_row_number_used_as_specimen_identity": False,
        "naive_row_count_is_independent_n": False,
        "scientific_status_changed": False,
    }
    lineage_sha = _canonical_sha(lineage_contract)
    review_request = build_review_request(
        candidate_id=candidate_id,
        evidence_artifact_sha256=evidence_sha,
        semantic_contract_sha256=semantic_sha,
        lineage_sha256=lineage_sha,
        intake_artifact_sha256=intake_sha,
        requested_uses=["scientific_intake"],
    )
    packet: dict[str, Any] = {
        "schema_version": REVIEWED_RESOLUTION_COMPILER_SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "evidence_artifact_sha256": evidence_sha,
        "structural_intake_sha256": intake_sha,
        "proposal_packet_sha256": proposal_packet_sha,
        "semantic_resolution_contract": semantic_contract,
        "semantic_resolution_sha256": semantic_sha,
        "lineage_resolution_contract": lineage_contract,
        "lineage_resolution_sha256": lineage_sha,
        "resolution_review_request": review_request,
        "resolution_review_request_created": True,
        "prior_unresolved_proposal_review_is_sufficient": False,
        "human_review_decision_created": False,
        "accepted_for_analysis": False,
        "scientific_support_established": False,
        "scientific_status_changed": False,
    }
    packet["resolution_packet_sha256"] = _canonical_sha(packet)
    return packet


def verify_reviewed_resolution_contract(
    *,
    structure: Mapping[str, Any],
    proposal: Mapping[str, Any],
    resolution_contract: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(resolution_contract, Mapping):
        raise ReviewedResolutionCompilerError("resolution_contract must be an object")
    semantic_contract = resolution_contract.get("semantic_resolution_contract")
    lineage_contract = resolution_contract.get("lineage_resolution_contract")
    if not isinstance(semantic_contract, Mapping) or not isinstance(lineage_contract, Mapping):
        raise ReviewedResolutionCompilerError("resolution contracts are malformed")
    semantic = semantic_contract.get("resolution")
    lineage = lineage_contract.get("resolution")
    if not isinstance(semantic, Mapping) or not isinstance(lineage, Mapping):
        raise ReviewedResolutionCompilerError("embedded resolution is malformed")
    expected = build_reviewed_resolution_contract(
        structure=structure,
        proposal=proposal,
        semantic_resolution=semantic,
        lineage_resolution=lineage,
    )
    if dict(resolution_contract) != expected:
        raise ReviewedResolutionCompilerError(
            "resolution bytes differ from exact proposal-bound canonical resolution"
        )
    return {
        "resolution_packet_sha256": expected["resolution_packet_sha256"],
        "resolution_review_request_id": expected["resolution_review_request"][
            "review_request_id"
        ],
        "exact_resolution_binding_verified": True,
        "scientific_support_established": False,
        "scientific_status_changed": False,
    }


def _identity_cell(row: list[str], index: int, field: str) -> str:
    if index >= len(row):
        raise ReviewedResolutionCompilerError(f"{field} column is absent from row")
    value = row[index]
    if not value or not value.strip() or value != value.strip():
        raise ReviewedResolutionCompilerError(
            f"{field} source cell must be non-empty trimmed text"
        )
    return value


def _optional_identity_cell(row: list[str], index: int | None, field: str) -> str | None:
    if index is None:
        return None
    return _identity_cell(row, index, field)


def _numeric_cell(row: list[str], index: int, field: str) -> float:
    if index >= len(row):
        raise ReviewedResolutionCompilerError(f"{field} column is absent from row")
    try:
        number = float(row[index].strip())
    except ValueError as exc:
        raise ReviewedResolutionCompilerError(f"{field} source cell is not numeric") from exc
    if not math.isfinite(number):
        raise ReviewedResolutionCompilerError(f"{field} source cell is not finite")
    return number


def _row_uncertainty(row: list[str], spec: Mapping[str, Any]) -> float | None:
    mode = spec["mode"]
    if mode == "none":
        return None
    if mode == "constant":
        return float(spec["value"])
    result = _numeric_cell(row, int(spec["column_index"]), "standard_uncertainty")
    if result < 0:
        raise ReviewedResolutionCompilerError(
            "standard_uncertainty source cell must be non-negative"
        )
    return result


def compile_reviewed_resolution(
    *,
    artifact_bytes: bytes,
    structure: Mapping[str, Any],
    proposal: Mapping[str, Any],
    resolution_contract: Mapping[str, Any],
    review_decision: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile rows only after the exact resolved contract has an approved review release."""
    if not isinstance(artifact_bytes, bytes) or not artifact_bytes:
        raise ReviewedResolutionCompilerError("artifact_bytes must be non-empty exact bytes")
    observed_sha = hashlib.sha256(artifact_bytes).hexdigest()
    expected_sha = _sha(
        proposal.get("evidence_artifact_sha256"),
        "proposal.evidence_artifact_sha256",
    )
    if observed_sha != expected_sha:
        raise ReviewedResolutionCompilerError("artifact bytes differ from proposal evidence SHA")
    delimiter = structure.get("delimiter")
    if not isinstance(delimiter, str):
        raise ReviewedResolutionCompilerError("structure delimiter is invalid")
    observed_structure = inspect_delimited_structure(
        artifact_bytes,
        delimiter_hint=delimiter,
    )
    if dict(observed_structure) != dict(structure):
        raise ReviewedResolutionCompilerError(
            "artifact bytes no longer reproduce the reviewed generic structure"
        )
    verify_generic_semantic_lineage_proposal(structure=structure, proposal=proposal)
    verify_reviewed_resolution_contract(
        structure=structure,
        proposal=proposal,
        resolution_contract=resolution_contract,
    )

    semantic_sha = _sha(
        resolution_contract.get("semantic_resolution_sha256"),
        "resolution.semantic_resolution_sha256",
    )
    lineage_sha = _sha(
        resolution_contract.get("lineage_resolution_sha256"),
        "resolution.lineage_resolution_sha256",
    )
    intake_sha = _sha(
        resolution_contract.get("structural_intake_sha256"),
        "resolution.structural_intake_sha256",
    )
    candidate_id = _text(
        resolution_contract.get("candidate_id"),
        "resolution.candidate_id",
    )
    request = resolution_contract.get("resolution_review_request")
    if not isinstance(request, Mapping):
        raise ReviewedResolutionCompilerError("resolution review request is malformed")
    try:
        release = verify_review_release(
            request=request,
            decision=review_decision,
            candidate_id=candidate_id,
            evidence_artifact_sha256=observed_sha,
            semantic_contract_sha256=semantic_sha,
            lineage_sha256=lineage_sha,
            intake_artifact_sha256=intake_sha,
            downstream_use="scientific_intake",
        )
    except ScientificReviewReleaseError as exc:
        raise ReviewedResolutionCompilerError(
            "exact resolved scientific-intake review release verification failed"
        ) from exc
    if release["human_review_blocker_released"] is not True:
        raise ReviewedResolutionCompilerError(
            "resolved scientific-intake review did not release normalization"
        )

    semantic_contract = resolution_contract["semantic_resolution_contract"]
    lineage_contract = resolution_contract["lineage_resolution_contract"]
    semantic = semantic_contract["resolution"]
    lineage = lineage_contract["resolution"]
    if not isinstance(semantic, Mapping) or not isinstance(lineage, Mapping):
        raise ReviewedResolutionCompilerError("resolved contracts are malformed")

    material_spec = semantic["material"]
    material = MaterialIdentity(
        material_name=str(material_spec["material_name"]),
        declared_identifier=str(material_spec["declared_identifier"]),
        identity_basis=str(material_spec["identity_basis"]),
    )
    text = artifact_bytes.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True))
    if len(rows) < 2:
        raise ReviewedResolutionCompilerError("resolved artifact contains no data rows")

    normalized_records: list[dict[str, Any]] = []
    lineages: list[ObservationLineage] = []
    rejected_rows: list[dict[str, Any]] = []
    for data_ordinal, row in enumerate(rows[1:], start=1):
        record_locator = f"data_row:{data_ordinal}"
        try:
            sample_id = _identity_cell(
                row,
                int(semantic["sample_id_column"]),
                "sample_id",
            )
            value = _numeric_cell(row, int(semantic["value_column"]), "value")
            provenance = ProvenanceLocator(
                source_id=str(semantic["source_id"]),
                artifact_sha256=observed_sha,
                record_locator=record_locator,
            )
            measurement = NormalizedMeasurement(
                material=material,
                sample_id=sample_id,
                property_name=str(semantic["property_name"]),
                value=value,
                unit=str(semantic["unit"]),
                method=str(semantic["method"]),
                instrument_model=str(semantic["instrument_model"]),
                calibration_id=semantic["calibration_id"],
                process_signature=semantic["process_signature"],
                standard_uncertainty=_row_uncertainty(
                    row,
                    semantic["standard_uncertainty"],
                ),
                provenance=provenance,
            )
            observation = ObservationLineage(
                source_id=str(semantic["source_id"]),
                lab_id=_optional_identity_cell(
                    row,
                    lineage["lab_id_column"],
                    "lab_id",
                ),
                material_lot_id=_optional_identity_cell(
                    row,
                    lineage["material_lot_id_column"],
                    "material_lot_id",
                ),
                build_or_synthesis_id=_optional_identity_cell(
                    row,
                    lineage["build_or_synthesis_id_column"],
                    "build_or_synthesis_id",
                ),
                specimen_id=_identity_cell(
                    row,
                    int(lineage["specimen_id_column"]),
                    "specimen_id",
                ),
                process_run_id=_optional_identity_cell(
                    row,
                    lineage["process_run_id_column"],
                    "process_run_id",
                ),
                acquisition_id=_identity_cell(
                    row,
                    int(lineage["acquisition_id_column"]),
                    "acquisition_id",
                ),
                measurement_id=measurement.measurement_id,
            )
        except (
            ReviewedResolutionCompilerError,
            ScientificEvidenceNormalizationError,
        ) as exc:
            rejected_rows.append(
                {
                    "record_locator": record_locator,
                    "reason": str(exc),
                }
            )
            continue
        lineages.append(observation)
        normalized_records.append(
            {
                "record_locator": record_locator,
                "measurement": measurement.metadata(),
                "lineage": observation.record(),
            }
        )

    if not normalized_records:
        raise ReviewedResolutionCompilerError("no source rows could be strictly normalized")
    independent = effective_independent_unit(lineages)
    manifest: dict[str, Any] = {
        "schema_version": REVIEWED_RESOLUTION_COMPILER_SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "evidence_artifact_sha256": observed_sha,
        "structural_intake_sha256": intake_sha,
        "proposal_packet_sha256": resolution_contract["proposal_packet_sha256"],
        "resolution_packet_sha256": resolution_contract["resolution_packet_sha256"],
        "review_release_id": release["review_release_id"],
        "human_review_blocker_released": True,
        "normalized_record_count": len(normalized_records),
        "rejected_row_count": len(rejected_rows),
        "all_source_rows_normalized": len(rejected_rows) == 0,
        "records": normalized_records,
        "rejected_rows": rejected_rows,
        "effective_independent_unit": independent,
        "record_locator_is_physical_identity": False,
        "measurement_id_is_physical_independence_proof": False,
        "candidate_id_used_as_sample_or_specimen_identity": False,
        "review_approval_is_scientific_support": False,
        "accepted_for_analysis": False,
        "scientific_support_established": False,
        "cross_source_comparability_established": False,
        "external_validation_established": False,
        "model_training_eligible": False,
        "hypothesis_support_established": False,
        "scientific_status_changed": False,
    }
    manifest["normalized_evidence_manifest_sha256"] = _canonical_sha(manifest)
    return manifest


__all__ = [
    "REVIEWED_RESOLUTION_COMPILER_SCHEMA_VERSION",
    "ReviewedResolutionCompilerError",
    "build_reviewed_resolution_contract",
    "compile_reviewed_resolution",
    "verify_reviewed_resolution_contract",
]
