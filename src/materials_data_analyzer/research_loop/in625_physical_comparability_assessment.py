"""Deterministic cross-source physical-comparability gate for the IN625 production loop.

The gate answers a narrow question: may the reviewed Zenodo 20503603 tensile evidence be
used as direct numerical validation of the tracked NIST AM-Bench 2018-02 AMMT melt-pool
geometry case?  It binds exact repository evidence and current runtime quality/re-diagnosis
state, classifies comparison axes without fitting a model, and selects the next
response-compatible evidence lead.  It never performs network access or upgrades scientific
status.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .kernel import ResearchLoopError

SCHEMA_VERSION = "1.0"
POLICY_VERSION = "1.0"
ACTION_CLASS = "reviewed_physical_comparability_assessment"
NEXT_ACTION_CLASS = "nist_mds2_2923_geometry_evidence_acquisition"
EXPECTED_SOURCE_ID = "zenodo-20503603-in625-lpbf-publication-supplement"
EXPECTED_ARCHIVE_SHA256 = "389602211b440cab5142c4071cb3c697702431d9b3aad2dfe2e6500de0a72907"
EXPECTED_FRONTIER_CANDIDATE = "nist-mds2-2923-cross-sectional-micrographs"
_ALLOWED_AXIS_STATUS = {"comparable", "non_comparable", "unknown"}


class In625PhysicalComparabilityAssessmentError(ResearchLoopError):
    """Raised when a reviewed comparability decision cannot remain evidence-bound."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise In625PhysicalComparabilityAssessmentError(message)


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
        raise In625PhysicalComparabilityAssessmentError(
            "comparability evidence must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise In625PhysicalComparabilityAssessmentError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _repo_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise In625PhysicalComparabilityAssessmentError(
            f"comparability evidence escapes repository root: {relative}"
        ) from exc
    if not path.is_file():
        raise In625PhysicalComparabilityAssessmentError(
            f"comparability evidence is not a file: {relative}"
        )
    return path


def _binding(root: Path, path: Path, raw: bytes) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(root)),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _load_json(root: Path, relative: str, field: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = _repo_path(root, relative)
    raw = path.read_bytes()
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise In625PhysicalComparabilityAssessmentError(
            f"{field} must be valid duplicate-free UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise In625PhysicalComparabilityAssessmentError(f"{field} root must be an object")
    return value, _binding(root, path, raw)


def _load_text(root: Path, relative: str, field: str) -> tuple[str, dict[str, Any]]:
    path = _repo_path(root, relative)
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise In625PhysicalComparabilityAssessmentError(f"{field} must be UTF-8 text") from exc
    return text, _binding(root, path, raw)


def _load_csv(
    root: Path,
    relative: str,
    field: str,
    expected_header: tuple[str, ...],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    text, binding = _load_text(root, relative, field)
    reader = csv.DictReader(io.StringIO(text))
    if tuple(reader.fieldnames or ()) != expected_header:
        raise In625PhysicalComparabilityAssessmentError(f"{field} header drifted")
    rows = list(reader)
    if any(set(row) != set(expected_header) for row in rows):
        raise In625PhysicalComparabilityAssessmentError(f"{field} row field set drifted")
    return rows, binding


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise In625PhysicalComparabilityAssessmentError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise In625PhysicalComparabilityAssessmentError(f"{field} must be a sequence")
    return value


def _verified_runtime_document(
    value: Mapping[str, Any],
    *,
    digest_field: str,
    field: str,
) -> tuple[dict[str, Any], str]:
    document = dict(_mapping(value, field))
    digest = document.pop(digest_field, None)
    if not isinstance(digest, str) or len(digest) != 64:
        raise In625PhysicalComparabilityAssessmentError(
            f"{field}.{digest_field} must be canonical SHA-256"
        )
    if _canonical_sha(document) != digest:
        raise In625PhysicalComparabilityAssessmentError(
            f"{field} canonical content differs from embedded SHA-256"
        )
    document[digest_field] = digest
    return document, digest


def _axis(
    name: str,
    status: str,
    *,
    target: object,
    external: object,
    basis: str,
) -> dict[str, Any]:
    if status not in _ALLOWED_AXIS_STATUS:
        raise In625PhysicalComparabilityAssessmentError(
            f"invalid comparability status for {name}: {status}"
        )
    return {
        "axis": name,
        "status": status,
        "target": target,
        "external": external,
        "evidence_basis": basis,
    }


def _validate_target_evidence(
    readiness: Mapping[str, Any],
    process_rows: Sequence[Mapping[str, str]],
    measurement_rows: Sequence[Mapping[str, str]],
    readme: str,
) -> None:
    tracked = _mapping(readiness.get("tracked_case"), "NIST readiness tracked_case")
    scope = _mapping(readiness.get("current_scope"), "NIST readiness current_scope")
    _require(readiness.get("schema_version") == "1.0", "NIST readiness schema drifted")
    _require(tracked.get("material") == "IN625", "NIST target material drifted")
    _require(tracked.get("system") == "AMMT", "NIST target system drifted")
    _require(tracked.get("trace_count") == 10, "NIST target trace count drifted")
    _require(
        tracked.get("unique_process_condition_count") == 3,
        "NIST target process-condition count drifted",
    )
    _require(scope.get("maximum_allowed_use") == "descriptive", "NIST use boundary drifted")
    _require(scope.get("predictive_use_authorized") is False, "NIST predictive boundary widened")
    _require(len(process_rows) == 10 and len(measurement_rows) == 10, "NIST row counts drifted")

    process_ids: set[str] = set()
    conditions: set[tuple[float, float]] = set()
    for row in process_rows:
        sample_id = row["sample_id"]
        _require(sample_id and sample_id not in process_ids, "NIST process sample IDs are invalid")
        process_ids.add(sample_id)
        _require(row["system"] == "AMMT" and row["material"] == "IN625", "NIST row identity drifted")
        try:
            conditions.add((float(row["actual_laser_power_w"]), float(row["scan_speed_mm_s"])))
        except ValueError as exc:
            raise In625PhysicalComparabilityAssessmentError(
                "NIST process values must remain numeric"
            ) from exc
    _require(
        conditions == {(137.9, 400.0), (179.2, 800.0), (179.2, 1200.0)},
        "NIST exact process-condition set drifted",
    )
    measurement_ids = {row["sample_id"] for row in measurement_rows}
    _require(measurement_ids == process_ids, "NIST process/measurement sample mapping drifted")
    for row in measurement_rows:
        for name in (
            "melt_pool_width_mean_um",
            "melt_pool_width_std_dev_um",
            "melt_pool_depth_mean_um",
            "melt_pool_depth_std_dev_um",
        ):
            try:
                float(row[name])
            except ValueError as exc:
                raise In625PhysicalComparabilityAssessmentError(
                    f"NIST measurement field is non-numeric: {name}"
                ) from exc

    for exact_phrase in (
        "Geometry: individual laser scan tracks on a bare substrate without powder.",
        "Characterization: polished transverse cross sections measured using the",
        "Reported individual-measurement uncertainty: approximately 0.5 µm.",
    ):
        _require(exact_phrase in readme, "NIST experimental-context evidence drifted")


def _validate_external_evidence(
    tensile: Mapping[str, Any],
    source: Mapping[str, Any],
    quality: Mapping[str, Any],
    rediagnosis: Mapping[str, Any],
) -> None:
    reviewed = _mapping(tensile.get("reviewed_scope"), "tensile reviewed_scope")
    _require(tensile.get("schema_version") == "1.0", "tensile contract schema drifted")
    _require(tensile.get("source_id") == EXPECTED_SOURCE_ID, "tensile source identity drifted")
    _require(
        tensile.get("source_archive_sha256") == EXPECTED_ARCHIVE_SHA256,
        "tensile archive identity drifted",
    )
    _require(reviewed.get("material") == "IN625", "external reviewed material drifted")
    _require(
        reviewed.get("experiment") == "room_temperature_uniaxial_tensile_test",
        "external experiment semantics drifted",
    )
    _require(reviewed.get("standard_reference_text") == "DIN50125 (Type E)", "tensile standard drifted")
    _require(reviewed.get("row_independence_established") is False, "external independence over-claimed")
    _require(reviewed.get("cross_source_comparability_established") is False, "external comparability over-claimed")
    headers = _sequence(tensile.get("measurement_header"), "tensile measurement_header")
    _require("Tensile stress MPa" in headers and "Strain 1 %" in headers and "Load N" in headers, "tensile response semantics drifted")
    _require(not any("melt_pool" in str(item).lower() for item in headers), "tensile contract unexpectedly contains melt-pool response")

    zenodo = _mapping(source.get("zenodo"), "verified source zenodo")
    _require(source.get("source_id") == EXPECTED_SOURCE_ID, "verified source ID drifted")
    _require(zenodo.get("record_id") == 20503603, "verified Zenodo record drifted")
    archive_name = zenodo.get("archive_file")
    files = _mapping(zenodo.get("files"), "verified source files")
    archive = _mapping(files.get(archive_name), "verified source archive")
    _require(archive.get("verified_sha256") == EXPECTED_ARCHIVE_SHA256, "verified archive SHA drifted")

    _require(quality.get("quality_status") == "verified_observed_source_quality", "quality status drifted")
    _require(quality.get("source_id") == EXPECTED_SOURCE_ID, "quality source identity drifted")
    _require(quality.get("measurement_row_count") == 200289, "quality row count drifted")
    _require(quality.get("complete_numeric_measurement_row_count") == 200288, "complete row count drifted")
    _require(quality.get("incomplete_numeric_measurement_row_count") == 1, "incomplete row count drifted")
    _require(quality.get("missing_value_imputation_authorized") is False, "quality improperly permits imputation")
    _require(quality.get("row_exclusion_authorized") is False, "quality improperly permits row exclusion")
    _require(quality.get("direct_nist_condition_comparability_established") is False, "quality over-claimed comparability")
    _require(
        quality.get("known_incomplete_rows")
        == [
            {
                "sheet_name": "AM-AB-H",
                "block_index": 1,
                "excel_row_number": 79,
                "missing_reviewed_numeric_fields": ["load_n"],
                "non_numeric_reviewed_fields": [],
                "raw_anomalous_cell_text": {"load_n": ""},
            }
        ],
        "known external missingness identity drifted",
    )

    blocker = _mapping(rediagnosis.get("current_blocker"), "post-acquisition current_blocker")
    next_action = _mapping(rediagnosis.get("next_action"), "post-acquisition next_action")
    constraint = _mapping(next_action.get("source_quality_constraint"), "post-acquisition source quality constraint")
    _require(
        blocker.get("code") == "cross_source_physical_comparability_not_established",
        "post-acquisition blocker drifted",
    )
    _require(next_action.get("action_class") == ACTION_CLASS, "post-acquisition next action drifted")
    _require(constraint.get("affected_field") == "load_n" and constraint.get("affected_row_count") == 1, "source quality constraint drifted")
    for key in (
        "missing_value_imputation_authorized",
        "inverse_reconstruction_authorized",
        "row_exclusion_authorized",
    ):
        _require(constraint.get(key) is False, f"post-acquisition constraint widened authority: {key}")


def _select_geometry_candidate(frontier: Mapping[str, Any]) -> Mapping[str, Any]:
    candidates = _sequence(frontier.get("candidates"), "physical source frontier candidates")
    matches = [
        item
        for item in candidates
        if isinstance(item, Mapping) and item.get("candidate_id") == EXPECTED_FRONTIER_CANDIDATE
    ]
    _require(len(matches) == 1, "NIST mds2-2923 frontier candidate identity drifted")
    candidate = matches[0]
    _require(candidate.get("authority") == "NIST Public Data Repository / AM-Bench", "geometry candidate authority drifted")
    _require(candidate.get("identifier") == "10.18434/mds2-2923", "geometry candidate identifier drifted")
    _require(candidate.get("physical_origin") == "physical", "geometry candidate physical origin drifted")
    _require(candidate.get("issue_76_eligible") is False, "geometry candidate improperly claims exact issue-76 eligibility")
    _require("IN625" in str(candidate.get("material")), "geometry candidate lost IN625 scope")
    _require("bare_plate_single_track" in _sequence(candidate.get("material_states"), "candidate material states"), "geometry candidate state drifted")
    responses = set(_sequence(candidate.get("responses"), "candidate responses"))
    _require({"melt_pool_width", "melt_pool_depth"}.issubset(responses), "geometry candidate response support drifted")
    plan = _mapping(candidate.get("automatic_acquisition_plan"), "candidate acquisition plan")
    _require(plan.get("adapter") == "nist_pdr" and plan.get("product_id") == "mds2-2923", "geometry acquisition route drifted")
    _require(
        list(_sequence(plan.get("filepaths"), "candidate acquisition filepaths"))
        == ["2923_README.txt", "Master_TrackList_Measurements.xlsx"],
        "geometry acquisition file set drifted",
    )
    return candidate


def build_in625_physical_comparability_assessment(
    *,
    repository_root: str | Path,
    post_acquisition_rediagnosis: Mapping[str, Any],
    observed_quality_verification: Mapping[str, Any],
) -> dict[str, Any]:
    """Assess direct target/source comparability and select the next evidence class."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    rediagnosis, rediagnosis_sha = _verified_runtime_document(
        post_acquisition_rediagnosis,
        digest_field="rediagnosis_sha256",
        field="post_acquisition_rediagnosis",
    )
    quality, quality_sha = _verified_runtime_document(
        observed_quality_verification,
        digest_field="verification_sha256",
        field="observed_quality_verification",
    )

    readiness, readiness_binding = _load_json(
        root,
        "configs/research/nist_ambench_2018_02_planning_readiness.v1.json",
        "NIST planning readiness",
    )
    process_rows, process_binding = _load_csv(
        root,
        "data/case_studies/nist_ambench_2018_02/source_process_conditions.csv",
        "NIST process table",
        (
            "sample_id",
            "case_id",
            "trace_number",
            "actual_laser_power_w",
            "scan_speed_mm_s",
            "system",
            "material",
        ),
    )
    measurement_rows, measurement_binding = _load_csv(
        root,
        "data/case_studies/nist_ambench_2018_02/source_melt_pool_measurements.csv",
        "NIST measurement table",
        (
            "sample_id",
            "case_id",
            "trace_number",
            "melt_pool_width_mean_um",
            "melt_pool_width_std_dev_um",
            "melt_pool_depth_mean_um",
            "melt_pool_depth_std_dev_um",
        ),
    )
    target_readme, target_readme_binding = _load_text(
        root,
        "data/case_studies/nist_ambench_2018_02/README.md",
        "NIST case README",
    )
    tensile, tensile_binding = _load_json(
        root,
        "configs/research/in625_tensile_reviewed_intake.v1.json",
        "reviewed tensile contract",
    )
    source, source_binding = _load_json(
        root,
        "configs/research/in625_zenodo_20503603_verified_source.v1.json",
        "verified Zenodo source",
    )
    quality_contract, quality_contract_binding = _load_json(
        root,
        "configs/research/in625_tensile_observed_quality.v1.json",
        "observed tensile quality contract",
    )
    frontier, frontier_binding = _load_json(
        root,
        "configs/research/in625_external_physical_source_frontier.v1.json",
        "IN625 physical source frontier",
    )

    _validate_target_evidence(readiness, process_rows, measurement_rows, target_readme)
    _validate_external_evidence(tensile, source, quality, rediagnosis)
    _require(quality_contract.get("measurement_row_count") == 200289, "tracked quality contract row count drifted")
    candidate = _select_geometry_candidate(frontier)

    matrix = [
        _axis(
            "material_identity",
            "comparable",
            target="IN625",
            external="IN625",
            basis="Both exact reviewed target and external contracts identify IN625.",
        ),
        _axis(
            "machine_system_identity",
            "unknown",
            target="NIST AMMT",
            external="exact tensile-machine identity not established in reviewed tensile contract",
            basis="The NIST target binds AMMT; the reviewed tensile contract does not bind an equivalent machine identity.",
        ),
        _axis(
            "specimen_and_material_state",
            "non_comparable",
            target="individual laser scan track on bare substrate without powder",
            external="DIN50125 Type E room-temperature tensile specimen from manufactured material",
            basis="The target README and tensile standard describe physically different specimen/use states.",
        ),
        _axis(
            "process_condition_mapping",
            "unknown",
            target={
                "actual_laser_power_w_scan_speed_mm_s": [
                    [137.9, 400.0],
                    [179.2, 800.0],
                    [179.2, 1200.0],
                ]
            },
            external="laser power / scan-speed mapping not bound by reviewed tensile contract",
            basis="No reviewed one-to-one process-condition mapping exists for the tensile sheets.",
        ),
        _axis(
            "response_semantics",
            "non_comparable",
            target=["melt_pool_width_um", "melt_pool_depth_um"],
            external=["strain_percent", "load_n", "tensile_stress_mpa", "extension_mm"],
            basis="Cross-sectional melt-pool geometry and tensile mechanical responses are different physical observables.",
        ),
        _axis(
            "measurement_protocol_metrology",
            "non_comparable",
            target="polished transverse cross-section optical metrology",
            external="room-temperature uniaxial tensile test; DIN50125 Type E",
            basis="The measurement procedures do not observe the same response class.",
        ),
        _axis(
            "response_units",
            "non_comparable",
            target="micrometre-scale width/depth geometry",
            external="percent, newton, megapascal, millimetre tensile quantities",
            basis="Units belong to different response dimensions; unit conversion cannot create response equivalence.",
        ),
        _axis(
            "replicate_independence",
            "unknown",
            target="predictive independence/split grouping not established",
            external="parallel-test / row independence not established",
            basis="Neither evidence contract authorizes an independence inference for predictive validation.",
        ),
        _axis(
            "uncertainty_and_calibration_mapping",
            "unknown",
            target="approximately 0.5 µm individual optical-measurement uncertainty",
            external="cross-response uncertainty/calibration mapping not reviewed",
            basis="No uncertainty mapping connects target optical geometry to tensile responses.",
        ),
    ]
    _require(all(item["status"] in _ALLOWED_AXIS_STATUS for item in matrix), "comparability matrix status drifted")

    decision = {
        "decision_code": "direct_nist_numerical_validation_blocked_by_response_and_protocol_incompatibility",
        "material_identity_established": True,
        "response_compatibility_established": False,
        "protocol_compatibility_established": False,
        "direct_nist_condition_comparability_established": False,
        "numerical_cross_source_validation_authorized": False,
        "scalar_residual_comparison_authorized": False,
        "empirical_model_validation_established": False,
        "hypothesis_truth_established": False,
        "source_globally_unusable_claimed": False,
        "source_remains_usable_for_mechanical_property_questions": True,
        "scientific_status_changed": False,
    }

    next_action = {
        "action_class": NEXT_ACTION_CLASS,
        "candidate_id": candidate["candidate_id"],
        "authority": candidate["authority"],
        "identifier": candidate["identifier"],
        "reason": (
            "Acquire and review response-compatible bare-plate single-track IN625 melt-pool geometry evidence before any direct NIST validation attempt."
        ),
        "required_authoritative_files": [
            "2923_README.txt",
            "Master_TrackList_Measurements.xlsx",
        ],
        "required_response_support": ["melt_pool_width", "melt_pool_depth"],
        "required_machine_stratification": True,
        "direct_comparability_preestablished": False,
        "network_access_performed": False,
        "automatic_execution_authorized": False,
    }

    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "action_class": ACTION_CLASS,
        "assessment_status": "reviewed_comparability_assessed_direct_validation_blocked",
        "predecessor_rediagnosis_sha256": rediagnosis_sha,
        "observed_quality_verification_sha256": quality_sha,
        "evidence_bindings": {
            "nist_planning_readiness": readiness_binding,
            "nist_process_conditions": process_binding,
            "nist_melt_pool_measurements": measurement_binding,
            "nist_case_readme": target_readme_binding,
            "zenodo_reviewed_tensile_contract": tensile_binding,
            "zenodo_verified_source": source_binding,
            "zenodo_observed_quality_contract": quality_contract_binding,
            "in625_physical_source_frontier": frontier_binding,
        },
        "comparability_matrix": matrix,
        "gate_decision": decision,
        "source_quality_constraint": {
            "known_incomplete_row_count": 1,
            "known_incomplete_rows": quality["known_incomplete_rows"],
            "missing_value_imputation_authorized": False,
            "inverse_reconstruction_authorized": False,
            "row_exclusion_authorized": False,
            "missingness_mechanism_established": False,
        },
        "next_action": next_action,
        "scientific_boundary": {
            "network_access_performed": False,
            "arbitrary_command_execution_performed": False,
            "numerical_cross_source_comparison_performed": False,
            "model_fit_performed": False,
            "empirical_model_validation_established": False,
            "hypothesis_truth_established": False,
            "positive_scientific_closeout_established": False,
            "global_evidence_unavailability_claimed": False,
            "automatic_scientific_promotion": False,
            "scientific_status_changed": False,
        },
    }
    result["assessment_sha256"] = _canonical_sha(result)
    return result


__all__ = [
    "ACTION_CLASS",
    "NEXT_ACTION_CLASS",
    "In625PhysicalComparabilityAssessmentError",
    "build_in625_physical_comparability_assessment",
]
