"""Compile an exact reviewed XLSX sheet into strict normalized evidence.

This adapter reuses the generic proposal and reviewed-resolution contracts while keeping
Excel-specific representation hazards fail closed.  Formula cells are never evaluated,
styles/number formats are never interpreted, and only a visible, unmerged, formula-free
sheet that produced the exact reviewed generic projection may reach normalization.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

from .experimental_lineage import ObservationLineage, effective_independent_unit
from .kernel import ResearchLoopError
from .reviewed_resolution_compiler import (
    ReviewedResolutionCompilerError,
    verify_reviewed_resolution_contract,
)
from .scientific_evidence_normalization import (
    MaterialIdentity,
    NormalizedMeasurement,
    ProvenanceLocator,
    ScientificEvidenceNormalizationError,
)
from .scientific_review_release import ScientificReviewReleaseError, verify_review_release
from .xlsx_bounded_row_intake import XlsxBoundedRowIntakeError, inspect_xlsx_sheet_rows

REVIEWED_XLSX_RESOLUTION_COMPILER_SCHEMA_VERSION = "1.0"


class ReviewedXlsxResolutionCompilerError(ResearchLoopError):
    """Raised when reviewed XLSX evidence cannot be normalized safely."""


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
        raise ReviewedXlsxResolutionCompilerError(
            "XLSX normalized manifest must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(body).hexdigest()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ReviewedXlsxResolutionCompilerError(f"{field} must be non-empty trimmed text")
    return value


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _numeric(value: str, field: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise ReviewedXlsxResolutionCompilerError(f"{field} must be a finite numeric cell") from exc
    if not math.isfinite(result):
        raise ReviewedXlsxResolutionCompilerError(f"{field} must be finite")
    return result


def _resolution_parts(resolution_contract: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    semantic_contract = resolution_contract.get("semantic_resolution_contract")
    lineage_contract = resolution_contract.get("lineage_resolution_contract")
    if not isinstance(semantic_contract, Mapping) or not isinstance(lineage_contract, Mapping):
        raise ReviewedXlsxResolutionCompilerError("reviewed resolution contracts are malformed")
    semantic = semantic_contract.get("resolution")
    lineage = lineage_contract.get("resolution")
    if not isinstance(semantic, Mapping) or not isinstance(lineage, Mapping):
        raise ReviewedXlsxResolutionCompilerError("reviewed resolution payloads are malformed")
    return semantic, lineage


def _cell_map(row: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    cells = row.get("cells")
    if not isinstance(cells, list):
        raise ReviewedXlsxResolutionCompilerError("XLSX row cells are malformed")
    result: dict[int, Mapping[str, Any]] = {}
    for cell in cells:
        if not isinstance(cell, Mapping):
            raise ReviewedXlsxResolutionCompilerError("XLSX cell record is malformed")
        index = cell.get("column_index")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ReviewedXlsxResolutionCompilerError("XLSX cell column index is invalid")
        if index in result:
            raise ReviewedXlsxResolutionCompilerError("XLSX row repeats a source column")
        if cell.get("formula_text") is not None or str(cell.get("representation", "")).startswith("formula_"):
            raise ReviewedXlsxResolutionCompilerError("formula cell cannot enter raw XLSX normalization")
        result[index] = cell
    return result


def _cell_text(cells: Mapping[int, Mapping[str, Any]], index: int, field: str) -> tuple[str, str]:
    cell = cells.get(index)
    if cell is None:
        raise ReviewedXlsxResolutionCompilerError(f"{field} source cell is missing")
    value = cell.get("display_text_structural_only")
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ReviewedXlsxResolutionCompilerError(f"{field} source cell must be non-empty trimmed text")
    coordinate = _text(cell.get("coordinate"), f"{field}.coordinate")
    return value, coordinate


def _optional_cell_text(
    cells: Mapping[int, Mapping[str, Any]],
    index: int | None,
    field: str,
) -> str | None:
    if index is None:
        return None
    value, _ = _cell_text(cells, index, field)
    return value


def _uncertainty(
    semantic: Mapping[str, Any],
    cells: Mapping[int, Mapping[str, Any]],
) -> float | None:
    policy = semantic.get("standard_uncertainty")
    if not isinstance(policy, Mapping):
        raise ReviewedXlsxResolutionCompilerError("standard uncertainty policy is malformed")
    mode = policy.get("mode")
    if mode == "none":
        return None
    if mode == "constant":
        value = policy.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ReviewedXlsxResolutionCompilerError("constant uncertainty is invalid")
        result = float(value)
    elif mode == "column":
        index = policy.get("column_index")
        if isinstance(index, bool) or not isinstance(index, int):
            raise ReviewedXlsxResolutionCompilerError("uncertainty source column is invalid")
        text, _ = _cell_text(cells, index, "standard_uncertainty")
        result = _numeric(text, "standard_uncertainty")
    else:
        raise ReviewedXlsxResolutionCompilerError("unsupported uncertainty policy")
    if result < 0:
        raise ReviewedXlsxResolutionCompilerError("standard uncertainty must be non-negative")
    return result


def _optional_index(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReviewedXlsxResolutionCompilerError(f"{field} must be a source column index or null")
    return value


def compile_reviewed_xlsx_resolution(
    *,
    workbook_bytes: bytes,
    xlsx_row_report: Mapping[str, Any],
    proposal: Mapping[str, Any],
    resolution_contract: Mapping[str, Any],
    review_decision: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile a formula-free reviewed XLSX sheet without interpreting Excel semantics."""
    if not isinstance(workbook_bytes, bytes) or not workbook_bytes:
        raise ReviewedXlsxResolutionCompilerError("workbook_bytes must be non-empty exact bytes")
    sheet_name = _text(xlsx_row_report.get("sheet_name"), "xlsx_row_report.sheet_name")
    try:
        fresh_report = inspect_xlsx_sheet_rows(workbook_bytes, sheet_name=sheet_name)
    except XlsxBoundedRowIntakeError as exc:
        raise ReviewedXlsxResolutionCompilerError("exact XLSX row intake failed") from exc
    if dict(xlsx_row_report) != fresh_report:
        raise ReviewedXlsxResolutionCompilerError("workbook or selected-sheet bytes differ from reviewed XLSX row report")
    if fresh_report.get("generic_table_projection_available") is not True:
        raise ReviewedXlsxResolutionCompilerError("selected XLSX sheet is unsafe for generic reviewed normalization")
    if fresh_report.get("formula_cell_count") != 0:
        raise ReviewedXlsxResolutionCompilerError("formula-bearing XLSX sheet cannot enter raw normalization")
    if fresh_report.get("merged_cell_ranges") != [] or fresh_report.get("hidden_row_numbers") != []:
        raise ReviewedXlsxResolutionCompilerError("merged or hidden XLSX structure cannot enter naive row normalization")
    if fresh_report.get("sheet_state") != "visible":
        raise ReviewedXlsxResolutionCompilerError("hidden XLSX sheet cannot enter naive row normalization")

    structure = fresh_report.get("generic_table_projection")
    if not isinstance(structure, Mapping):
        raise ReviewedXlsxResolutionCompilerError("XLSX generic table projection is missing")
    workbook_sha = hashlib.sha256(workbook_bytes).hexdigest()
    if structure.get("artifact_sha256") != workbook_sha or fresh_report.get("workbook_sha256") != workbook_sha:
        raise ReviewedXlsxResolutionCompilerError("XLSX artifact SHA binding failed")

    try:
        verified_resolution = verify_reviewed_resolution_contract(
            structure=structure,
            proposal=proposal,
            resolution_contract=resolution_contract,
        )
    except ReviewedResolutionCompilerError as exc:
        raise ReviewedXlsxResolutionCompilerError("reviewed XLSX resolution verification failed") from exc

    request = resolution_contract.get("resolution_review_request")
    if not isinstance(request, Mapping):
        raise ReviewedXlsxResolutionCompilerError("resolved XLSX review request is malformed")
    try:
        release = verify_review_release(
            request=request,
            decision=review_decision,
            candidate_id=_text(resolution_contract.get("candidate_id"), "candidate_id"),
            evidence_artifact_sha256=workbook_sha,
            semantic_contract_sha256=_text(
                resolution_contract.get("semantic_resolution_sha256"),
                "semantic_resolution_sha256",
            ),
            lineage_sha256=_text(
                resolution_contract.get("lineage_resolution_sha256"),
                "lineage_resolution_sha256",
            ),
            intake_artifact_sha256=_text(
                resolution_contract.get("structural_intake_sha256"),
                "structural_intake_sha256",
            ),
            downstream_use="scientific_intake",
        )
    except ScientificReviewReleaseError as exc:
        raise ReviewedXlsxResolutionCompilerError(
            "resolved XLSX scientific-intake review release verification failed"
        ) from exc
    if release.get("human_review_blocker_released") is not True:
        raise ReviewedXlsxResolutionCompilerError("resolved XLSX review does not release scientific_intake")

    semantic, lineage = _resolution_parts(resolution_contract)
    material_value = semantic.get("material")
    if not isinstance(material_value, Mapping):
        raise ReviewedXlsxResolutionCompilerError("resolved material identity is malformed")
    try:
        material = MaterialIdentity(
            material_name=_text(material_value.get("material_name"), "material_name"),
            declared_identifier=_text(
                material_value.get("declared_identifier"), "declared_identifier"
            ),
            identity_basis=_text(material_value.get("identity_basis"), "identity_basis"),
        )
    except ScientificEvidenceNormalizationError as exc:
        raise ReviewedXlsxResolutionCompilerError("resolved material identity is invalid") from exc

    sample_index = semantic.get("sample_id_column")
    value_index = semantic.get("value_column")
    specimen_index = lineage.get("specimen_id_column")
    acquisition_index = lineage.get("acquisition_id_column")
    for value, field in (
        (sample_index, "sample_id_column"),
        (value_index, "value_column"),
        (specimen_index, "specimen_id_column"),
        (acquisition_index, "acquisition_id_column"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ReviewedXlsxResolutionCompilerError(f"{field} is invalid")

    rows = fresh_report.get("rows")
    if not isinstance(rows, list) or len(rows) < 2:
        raise ReviewedXlsxResolutionCompilerError("selected XLSX sheet has no data rows")
    records: list[dict[str, Any]] = []
    lineages: list[ObservationLineage] = []
    rejected_rows: list[dict[str, Any]] = []
    for source_row in rows[1:]:
        if not isinstance(source_row, Mapping):
            raise ReviewedXlsxResolutionCompilerError("XLSX source row is malformed")
        row_number = source_row.get("row_number")
        if isinstance(row_number, bool) or not isinstance(row_number, int) or row_number <= 0:
            raise ReviewedXlsxResolutionCompilerError("XLSX source row number is invalid")
        try:
            cells = _cell_map(source_row)
            sample_id, sample_coordinate = _cell_text(cells, sample_index, "sample_id")
            specimen_id, _ = _cell_text(cells, specimen_index, "specimen_id")
            acquisition_id, _ = _cell_text(cells, acquisition_index, "acquisition_id")
            value_text, value_coordinate = _cell_text(cells, value_index, "value")
            measured_value = _numeric(value_text, "value")
            record_locator = (
                f"xlsx:sheet={sheet_name};row={row_number};"
                f"sample_cell={sample_coordinate};value_cell={value_coordinate}"
            )
            provenance = ProvenanceLocator(
                source_id=_text(semantic.get("source_id"), "source_id"),
                artifact_sha256=workbook_sha,
                record_locator=record_locator,
            )
            measurement = NormalizedMeasurement(
                material=material,
                sample_id=sample_id,
                property_name=_text(semantic.get("property_name"), "property_name"),
                value=measured_value,
                unit=_text(semantic.get("unit"), "unit"),
                method=_text(semantic.get("method"), "method"),
                instrument_model=_text(semantic.get("instrument_model"), "instrument_model"),
                calibration_id=_optional_text(semantic.get("calibration_id"), "calibration_id"),
                process_signature=_optional_text(
                    semantic.get("process_signature"), "process_signature"
                ),
                standard_uncertainty=_uncertainty(semantic, cells),
                provenance=provenance,
            )
            observation_lineage = ObservationLineage(
                source_id=measurement.provenance.source_id,
                lab_id=_optional_cell_text(
                    cells, _optional_index(lineage.get("lab_id_column"), "lab_id_column"), "lab_id"
                ),
                material_lot_id=_optional_cell_text(
                    cells,
                    _optional_index(lineage.get("material_lot_id_column"), "material_lot_id_column"),
                    "material_lot_id",
                ),
                build_or_synthesis_id=_optional_cell_text(
                    cells,
                    _optional_index(
                        lineage.get("build_or_synthesis_id_column"),
                        "build_or_synthesis_id_column",
                    ),
                    "build_or_synthesis_id",
                ),
                specimen_id=specimen_id,
                process_run_id=_optional_cell_text(
                    cells,
                    _optional_index(lineage.get("process_run_id_column"), "process_run_id_column"),
                    "process_run_id",
                ),
                acquisition_id=acquisition_id,
                measurement_id=measurement.measurement_id,
            )
        except (
            ReviewedXlsxResolutionCompilerError,
            ScientificEvidenceNormalizationError,
        ) as exc:
            rejected_rows.append(
                {
                    "row_number": row_number,
                    "record_locator": f"xlsx:sheet={sheet_name};row={row_number}",
                    "reason": str(exc),
                }
            )
            continue
        lineages.append(observation_lineage)
        records.append(
            {
                "record_locator": record_locator,
                "measurement": measurement.metadata(),
                "lineage": observation_lineage.record(),
                "source_row_number_is_physical_identity": False,
                "formula_value_used": False,
                "number_format_semantics_used": False,
            }
        )

    independent = effective_independent_unit(lineages) if lineages else None
    manifest: dict[str, Any] = {
        "schema_version": REVIEWED_XLSX_RESOLUTION_COMPILER_SCHEMA_VERSION,
        "candidate_id": resolution_contract.get("candidate_id"),
        "workbook_sha256": workbook_sha,
        "xlsx_row_intake_report_sha256": fresh_report.get("row_intake_report_sha256"),
        "sheet_name": sheet_name,
        "worksheet_member": fresh_report.get("worksheet_member"),
        "resolution_packet_sha256": resolution_contract.get("resolution_packet_sha256"),
        "exact_resolution_binding_verified": verified_resolution.get(
            "exact_resolution_binding_verified"
        ),
        "review_release_id": release.get("review_release_id"),
        "human_review_blocker_released": True,
        "normalized_record_count": len(records),
        "rejected_row_count": len(rejected_rows),
        "all_source_rows_normalized": len(rejected_rows) == 0 and len(records) == len(rows) - 1,
        "records": records,
        "rejected_rows": rejected_rows,
        "effective_independent_unit": independent,
        "formula_cells_admitted": False,
        "cached_formula_values_admitted": False,
        "number_formats_interpreted": False,
        "styles_used_as_scientific_semantics": False,
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
    "REVIEWED_XLSX_RESOLUTION_COMPILER_SCHEMA_VERSION",
    "ReviewedXlsxResolutionCompilerError",
    "compile_reviewed_xlsx_resolution",
]
