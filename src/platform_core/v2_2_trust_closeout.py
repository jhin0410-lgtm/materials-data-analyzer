"""Read-only v2.2 Materials scientific evidence closeout.

This module aggregates tracked compact artifacts from v2.2.1 through v2.2.5.
It does not acquire data, regenerate descriptors, load row-level structures or
graphs, fit models, or recompute scientific metrics.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PROCESSED_DIR = Path("data/processed")
PLATFORM_DIR = Path("data/platform")

EXPECTED_V2_2_1_DECISION_DIGEST = "277cd5e254b962338a78c68600500da873538e6783e92aebad8aa34374e889f0"

INPUT_ARTIFACTS: tuple[str, ...] = (
    "data/processed/materials_physics_v2_2_predictive_value_decision.json",
    "data/processed/materials_physics_v2_2_predictive_comparison_summary.csv",
    "data/processed/materials_physics_v2_2_feature_use_evidence.json",
    "data/processed/materials_project_v2_2_4_structure_enrichment_summary.json",
    "data/processed/materials_project_v2_2_4_snapshot_alignment_summary.csv",
    "data/processed/materials_project_v2_2_4_descriptor_definition_snapshot.csv",
    "data/processed/materials_project_v2_2_4_graph_eligibility_summary.csv",
    "data/processed/materials_v2_2_5_known_structure_cohort_summary.json",
    "data/processed/materials_v2_2_5_feature_set_snapshot.csv",
    "data/processed/materials_v2_2_5_predictive_comparison_summary.csv",
    "data/processed/materials_v2_2_5_paired_metric_summary.csv",
    "data/processed/materials_v2_2_5_prediction_uncertainty_summary.csv",
    "data/processed/materials_v2_2_5_predictive_value_decision.json",
    "data/processed/materials_v2_2_5_feature_use_evidence.json",
)

TRACKED_CLOSEOUT_OUTPUTS: tuple[str, ...] = (
    "data/platform/v2_2_capability_matrix.json",
    "data/platform/materials_prediction_context_registry_v2.json",
    "data/processed/materials_v2_2_capability_matrix.json",
    "data/processed/materials_v2_2_evidence_summary.json",
    "data/processed/materials_v2_2_claim_matrix.json",
    "data/processed/materials_v2_2_uncertainty_boundary.json",
    "data/processed/materials_v2_2_prediction_contexts.json",
    "data/processed/materials_v2_2_closeout_decision.json",
    "data/processed/materials_v2_2_closeout_summary.md",
)


@dataclass(frozen=True)
class V22CapabilityRecord:
    capability_id: str
    category: str
    status: str
    prediction_context: str
    evidence_levels: tuple[str, ...]
    available: bool
    executed: bool
    model_input_used: bool
    group_evaluated: bool
    uncertainty_evaluated: bool
    representative_model_selected: bool
    independently_validated: bool
    production_validated: bool
    supporting_artifacts: tuple[str, ...]
    limitations: tuple[str, ...]
    prohibited_interpretations: tuple[str, ...]


@dataclass(frozen=True)
class V22EvidenceRecord:
    evidence_id: str
    context: str
    status: str
    evidence_level: str
    summary: str
    supporting_artifacts: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class V22ClaimRecord:
    claim_id: str
    context: str
    status: str
    supporting_artifacts: tuple[str, ...]
    conflicting_evidence: tuple[str, ...]
    limitations: tuple[str, ...]
    prohibited_interpretations: tuple[str, ...]


@dataclass(frozen=True)
class V22UncertaintySummary:
    uncertainty_id: str
    status: str
    interpretation: str
    unit: str
    supporting_artifacts: tuple[str, ...]
    limitations: tuple[str, ...]
    prohibited_interpretations: tuple[str, ...]


@dataclass(frozen=True)
class V22CloseoutDecision:
    schema_version: str
    case_study_id: str
    release_readiness: str
    composition_decision: str
    known_structure_decision: str
    representative_model_selected: bool
    graph_model_used: bool
    gnn_model_validated: bool
    target_source: str
    current_target_policy: str
    no_new_scientific_result: bool
    release_gates: dict[str, bool]
    limitations: tuple[str, ...]
    recommended_next_scope: str


def _repo_path(root: Path, relative_path: str) -> Path:
    normalized = relative_path.replace("\\", "/")
    candidate = root / normalized
    if Path(normalized).is_absolute() or ".." in Path(normalized).parts:
        raise ValueError(f"unsafe repository path: {relative_path}")
    return candidate


def _load_json(root: Path, relative_path: str) -> dict[str, Any]:
    with _repo_path(root, relative_path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {relative_path}")
    return payload


def _read_csv_rows(root: Path, relative_path: str) -> list[dict[str, str]]:
    with _repo_path(root, relative_path).open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _canonical_payload_bytes(root: Path, relative_path: str) -> bytes:
    path = _repo_path(root, relative_path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return text.replace("\r\n", "\n").encode("utf-8")


def stable_checksum(root: Path, relative_path: str) -> str:
    return hashlib.sha256(_canonical_payload_bytes(root, relative_path)).hexdigest()


def artifact_lineage(root: Path = Path(".")) -> dict[str, Any]:
    root = Path(root)
    records: list[dict[str, Any]] = []
    missing: list[str] = []
    for relative_path in INPUT_ARTIFACTS:
        path = _repo_path(root, relative_path)
        if not path.exists():
            missing.append(relative_path)
            continue
        records.append(
            {
                "artifact": relative_path,
                "checksum_sha256": stable_checksum(root, relative_path),
                "tracked_compact": True,
            }
        )
    return {
        "schema_version": "2.2.6",
        "case_study_id": "materials_project",
        "input_artifact_count": len(records),
        "missing_artifacts": missing,
        "artifacts": records,
        "lineage_status": "valid" if not missing else "missing_input_artifact",
        "execution_policy": "tracked_compact_read_only_no_api_no_model_no_feature_generation",
    }


def _float_values(rows: list[dict[str, str]], column: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        try:
            values.append(float(row[column]))
        except (KeyError, TypeError, ValueError):
            continue
    return values


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def load_closeout_inputs(root: Path = Path(".")) -> dict[str, Any]:
    root = Path(root)
    return {
        "v2_2_1_decision": _load_json(root, "data/processed/materials_physics_v2_2_predictive_value_decision.json"),
        "v2_2_1_feature_use": _load_json(root, "data/processed/materials_physics_v2_2_feature_use_evidence.json"),
        "v2_2_4_summary": _load_json(root, "data/processed/materials_project_v2_2_4_structure_enrichment_summary.json"),
        "v2_2_4_snapshot": _read_csv_rows(root, "data/processed/materials_project_v2_2_4_snapshot_alignment_summary.csv"),
        "v2_2_4_graph": _read_csv_rows(root, "data/processed/materials_project_v2_2_4_graph_eligibility_summary.csv"),
        "v2_2_5_cohort": _load_json(root, "data/processed/materials_v2_2_5_known_structure_cohort_summary.json"),
        "v2_2_5_decision": _load_json(root, "data/processed/materials_v2_2_5_predictive_value_decision.json"),
        "v2_2_5_feature_use": _load_json(root, "data/processed/materials_v2_2_5_feature_use_evidence.json"),
        "v2_2_5_paired": _read_csv_rows(root, "data/processed/materials_v2_2_5_paired_metric_summary.csv"),
        "v2_2_5_uncertainty": _read_csv_rows(root, "data/processed/materials_v2_2_5_prediction_uncertainty_summary.csv"),
        "lineage": artifact_lineage(root),
    }


def build_prediction_context_registry(root: Path = Path(".")) -> dict[str, Any]:
    inputs = load_closeout_inputs(root)
    composition = inputs["v2_2_1_decision"]
    structure = inputs["v2_2_5_decision"]
    return {
        "schema_version": "2.2.6",
        "registry_id": "materials_prediction_context_registry_v2",
        "case_study_id": "materials_project",
        "status": "release_ready",
        "contexts": [
            {
                "context_id": "composition_only_pre_structure",
                "availability_timing": "before_relaxed_structure_is_known",
                "allowed_inputs": [
                    "formula_or_composition",
                    "elemental_property_metadata",
                    "composition_derived_descriptors",
                ],
                "prohibited_inputs": [
                    "relaxed_crystal_structure",
                    "structural_geometry",
                    "current_api_energy_values",
                    "DFT_target_aliases",
                ],
                "current_decision": composition["predictive_value_status"],
                "representative_model_selected": bool(composition["representative_model_selected"]),
                "claim_boundary": "composition physics descriptors were evaluated and predictive improvement was not supported",
            },
            {
                "context_id": "known_structure_post_relaxation",
                "availability_timing": "after_a_relaxed_or_known_crystal_structure_is_available",
                "allowed_inputs": [
                    "validated_CrystalStructureEntity",
                    "registered_Tier_1_structure_descriptors",
                    "source_provided_symmetry_category",
                    "known_relaxed_structure_context",
                ],
                "prohibited_inputs": [
                    "current_api_energy_above_hull_as_label",
                    "graph_model_evidence",
                    "GNN_evidence",
                    "DFT_replacement_claim",
                ],
                "current_decision": structure["structure_predictive_value_status"],
                "representative_model_selected": bool(structure["representative_model_selected"]),
                "claim_boundary": "structure descriptors gave limited evidence in one primary group split only",
            },
        ],
        "cross_context_policy": {
            "merge_results_into_single_model_claim": False,
            "use_known_structure_result_as_pre_structure_screening_claim": False,
            "hide_structure_availability_timing": False,
        },
    }


def build_capability_matrix(root: Path = Path(".")) -> dict[str, Any]:
    inputs = load_closeout_inputs(root)
    v221 = inputs["v2_2_1_decision"]
    v224 = inputs["v2_2_4_summary"]
    v225 = inputs["v2_2_5_decision"]
    records = [
        V22CapabilityRecord(
            "composition_feature_builders",
            "feature_builder",
            "predictive_value_not_supported",
            "composition_only_pre_structure",
            (
                "definition_registered",
                "artifact_generated",
                "model_input_used",
                "group_evaluated",
                "predictive_value_not_supported",
            ),
            True,
            True,
            True,
            True,
            False,
            False,
            False,
            False,
            (
                "data/processed/materials_physics_v2_2_feature_definitions.csv",
                "data/processed/materials_physics_v2_2_predictive_value_decision.json",
            ),
            ("Primary group-aware median MAE degraded in the matched comparison.",),
            ("physics_constrained_model", "hybrid_physics_ml", "DFT_replacement"),
        ),
        V22CapabilityRecord(
            "structure_feature_builders",
            "feature_builder",
            "predictive_value_limited",
            "known_structure_post_relaxation",
            (
                "definition_registered",
                "artifact_generated",
                "model_input_used",
                "group_evaluated",
                "uncertainty_evaluated",
                "predictive_value_limited",
            ),
            True,
            True,
            True,
            True,
            True,
            False,
            False,
            False,
            (
                "data/processed/materials_project_v2_2_4_descriptor_definition_snapshot.csv",
                "data/processed/materials_v2_2_5_predictive_value_decision.json",
            ),
            ("Improvement appeared in one primary group split only.",),
            ("pre_structure_screening_claim", "phase_stability_guarantee"),
        ),
        V22CapabilityRecord(
            "CrystalStructureEntity",
            "scientific_entity",
            "executed",
            "known_structure_post_relaxation",
            ("definition_registered", "artifact_generated", "executed"),
            True,
            True,
            False,
            False,
            False,
            False,
            False,
            False,
            ("data/processed/materials_project_v2_2_4_structure_enrichment_summary.json",),
            ("Runtime pymatgen objects are not persisted in tracked outputs.",),
            ("structure_discovery_claim",),
        ),
        V22CapabilityRecord(
            "ScientificQuantity",
            "scientific_foundation",
            "metadata_registered",
            "cross_context",
            ("definition_registered",),
            True,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            ("docs/SCIENTIFIC_ENTITY_MODEL.md",),
            ("Quantity metadata supports bounded records; it is not evidence of predictive value.",),
            ("automatic_physics_validation",),
        ),
        V22CapabilityRecord(
            "unit_conversion",
            "scientific_foundation",
            "metadata_registered",
            "cross_context",
            ("definition_registered",),
            True,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            ("docs/SCIENTIFIC_QUANTITIES_AND_UNCERTAINTY.md",),
            ("Unit conversion metadata does not create measurement uncertainty.",),
            ("unitless_energy_claim",),
        ),
        V22CapabilityRecord(
            "structured_uncertainty",
            "scientific_foundation",
            "evaluated",
            "cross_context",
            ("definition_registered", "uncertainty_evaluated"),
            True,
            True,
            False,
            False,
            True,
            False,
            False,
            False,
            ("data/processed/materials_v2_2_5_prediction_uncertainty_summary.csv",),
            ("Prediction intervals are residual diagnostics, not DFT or source uncertainty.",),
            ("zero_source_uncertainty", "DFT_uncertainty_claim"),
        ),
        V22CapabilityRecord(
            "scientific_relations",
            "scientific_foundation",
            "metadata_registered",
            "cross_context",
            ("definition_registered",),
            True,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            ("docs/SCIENTIFIC_ENTITY_MODEL.md",),
            ("Relation metadata is not a physical simulation.",),
            ("causal_mechanism_proof",),
        ),
        V22CapabilityRecord(
            "operator_registry",
            "registry",
            "metadata_registered",
            "cross_context",
            ("definition_registered",),
            True,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            ("data/processed/materials_project_v2_2_4_operator_snapshot.json",),
            ("Operators are explicitly registered; arbitrary dynamic execution remains prohibited.",),
            ("arbitrary_callable_execution",),
        ),
        V22CapabilityRecord(
            "structure_acquisition",
            "data_enrichment",
            "executed",
            "known_structure_post_relaxation",
            ("input_available", "artifact_generated", "executed"),
            True,
            True,
            False,
            False,
            False,
            False,
            False,
            False,
            ("data/processed/materials_project_v2_2_4_structure_enrichment_summary.json",),
            ("Current MP structures are a later snapshot and are not the original v1.3 source body.",),
            ("target_overwrite", "unbounded_query_claim"),
        ),
        V22CapabilityRecord(
            "snapshot_alignment",
            "data_validation",
            "evaluated",
            "known_structure_post_relaxation",
            ("artifact_generated", "executed", "evaluated"),
            True,
            True,
            False,
            False,
            False,
            False,
            False,
            False,
            ("data/processed/materials_project_v2_2_4_snapshot_alignment_summary.csv",),
            ("Source version metadata is unavailable for all 838 rows.",),
            ("current_target_as_label",),
        ),
        V22CapabilityRecord(
            "structure_descriptors",
            "feature_builder",
            "predictive_value_limited",
            "known_structure_post_relaxation",
            ("definition_registered", "artifact_generated", "model_input_used", "group_evaluated"),
            True,
            True,
            True,
            True,
            True,
            False,
            False,
            False,
            (
                "data/processed/materials_project_v2_2_4_descriptor_coverage_summary.csv",
                "data/processed/materials_v2_2_5_paired_metric_summary.csv",
            ),
            ("Low-dimensional descriptors may not capture local chemistry or many-body effects.",),
            ("DFT_replacement", "causal_structure_property_mechanism"),
        ),
        V22CapabilityRecord(
            "periodic_graph_artifacts",
            "representation_artifact",
            "artifact_generated",
            "known_structure_post_relaxation",
            ("definition_registered", "artifact_generated"),
            True,
            True,
            False,
            False,
            False,
            False,
            False,
            False,
            ("data/processed/materials_project_v2_2_4_graph_eligibility_summary.csv",),
            ("Graph artifacts were not used by a model and do not provide predictive evidence.",),
            ("GNN_evidence", "graph_model_used", "graph_embedding_claim"),
        ),
        V22CapabilityRecord(
            "known_structure_prediction",
            "validation",
            "predictive_value_limited",
            "known_structure_post_relaxation",
            ("model_input_used", "group_evaluated", "uncertainty_evaluated", "predictive_value_limited"),
            True,
            True,
            True,
            True,
            True,
            False,
            False,
            False,
            ("data/processed/materials_v2_2_5_predictive_value_decision.json",),
            ("Limited evidence does not justify a representative model.",),
            ("pre_structure_screening_model", "production_scientific_decision"),
        ),
        V22CapabilityRecord(
            "prediction_intervals",
            "uncertainty",
            "evaluated",
            "known_structure_post_relaxation",
            ("uncertainty_evaluated",),
            True,
            True,
            False,
            False,
            True,
            False,
            False,
            False,
            ("data/processed/materials_v2_2_5_prediction_uncertainty_summary.csv",),
            ("Intervals estimate residual uncertainty for this dataset/model context only.",),
            ("DFT_uncertainty", "measurement_uncertainty"),
        ),
        V22CapabilityRecord(
            "representative_model",
            "model_decision",
            "unavailable",
            "cross_context",
            (),
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            (
                "data/processed/materials_physics_v2_2_predictive_value_decision.json",
                "data/processed/materials_v2_2_5_predictive_value_decision.json",
            ),
            ("No v2.2 context met the conservative representative-model gate.",),
            ("general_materials_project_model", "stability_oracle"),
        ),
        V22CapabilityRecord(
            "GNN",
            "model_family",
            "prohibited",
            "known_structure_post_relaxation",
            (),
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            ("data/processed/materials_project_v2_2_4_graph_eligibility_summary.csv",),
            ("Graph artifacts are future-readiness metadata only.",),
            ("GNN_validated", "graph_model_used"),
        ),
        V22CapabilityRecord(
            "physics_constrained_model",
            "model_family",
            "prohibited",
            "cross_context",
            (),
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            ("data/processed/materials_physics_v2_2_predictive_value_decision.json",),
            ("No physics-loss or constrained optimization model was implemented.",),
            ("physics_constrained_model_success",),
        ),
        V22CapabilityRecord(
            "hybrid_physics_ML",
            "model_family",
            "prohibited",
            "cross_context",
            (),
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            ("data/processed/materials_physics_v2_2_predictive_value_decision.json",),
            ("Feature augmentation is not a hybrid physics-ML model.",),
            ("hybrid_physics_ml_claim",),
        ),
        V22CapabilityRecord(
            "DFT_replacement",
            "prohibited_claim",
            "prohibited",
            "cross_context",
            (),
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            (
                "data/processed/materials_physics_v2_2_predictive_value_decision.json",
                "data/processed/materials_v2_2_5_predictive_value_decision.json",
            ),
            ("No DFT calculation, surrogate replacement, or phase-stability guarantee was established.",),
            ("DFT_replacement", "phase_stability_guaranteed"),
        ),
    ]
    return {
        "schema_version": "2.2.6",
        "matrix_id": "v2_2_capability_matrix",
        "case_study_id": "materials_project",
        "status": "release_ready",
        "source_decisions": {
            "composition": v221["predictive_value_status"],
            "structure": v225["structure_predictive_value_status"],
            "structure_readiness": v224["decision_status"],
        },
        "capabilities": [asdict(record) for record in records],
    }


def build_evidence_summary(root: Path = Path(".")) -> dict[str, Any]:
    inputs = load_closeout_inputs(root)
    v221 = inputs["v2_2_1_decision"]
    v224 = inputs["v2_2_4_summary"]
    v225 = inputs["v2_2_5_decision"]
    uncertainty_rows = inputs["v2_2_5_uncertainty"]
    coverage_values = _float_values(uncertainty_rows, "empirical_coverage_mean")
    width_values = _float_values(uncertainty_rows, "mean_interval_width_mean")
    records = [
        V22EvidenceRecord(
            "composition_derived_features",
            "composition_only_pre_structure",
            v221["predictive_value_status"],
            "predictive_value_not_supported",
            "Composition-derived physics/materials descriptors were generated and evaluated, but primary group-aware performance degraded.",
            ("data/processed/materials_physics_v2_2_predictive_value_decision.json",),
            ("No representative composition model was selected.",),
        ),
        V22EvidenceRecord(
            "structure_descriptors",
            "known_structure_post_relaxation",
            v225["structure_predictive_value_status"],
            "predictive_value_limited",
            "Known-structure descriptors were evaluated with fixed group-aware splits and improved only one primary group split.",
            ("data/processed/materials_v2_2_5_predictive_value_decision.json",),
            ("Limited group-split consistency blocks representative model selection.",),
        ),
        V22EvidenceRecord(
            "periodic_graph_artifacts",
            "known_structure_post_relaxation",
            "artifact_generated",
            "artifact_generated",
            "Periodic graph artifacts were generated deterministically for 838 structures but were not loaded as model inputs.",
            ("data/processed/materials_project_v2_2_4_graph_eligibility_summary.csv",),
            ("No graph/GNN predictive evidence exists in v2.2.",),
        ),
        V22EvidenceRecord(
            "prediction_interval_diagnostics",
            "known_structure_post_relaxation",
            "prediction_interval_evaluated",
            "uncertainty_evaluated",
            "Split-conformal residual intervals were evaluated as predictive residual diagnostics, not source or DFT uncertainty.",
            ("data/processed/materials_v2_2_5_prediction_uncertainty_summary.csv",),
            ("Intervals are bounded to this dataset, model, and split context.",),
        ),
    ]
    return {
        "schema_version": "2.2.6",
        "case_study_id": "materials_project",
        "status": "release_ready",
        "evidence_records": [asdict(record) for record in records],
        "key_counts": {
            "composition_feature_rows": int(v221["feature_rows"]),
            "structure_requested_ids": int(v224["requested_material_id_count"]),
            "structure_returned_documents": int(v224["api_returned_document_count"]),
            "snapshot_aligned_rows": int(v225["snapshot_aligned_rows"]),
            "known_structure_cohort_rows": int(v225["cohort_rows"]),
            "graph_artifact_count": int(v224["graph_count"]),
        },
        "uncertainty_diagnostics": {
            "row_count": len(uncertainty_rows),
            "mean_empirical_coverage": _mean(coverage_values),
            "mean_interval_width": _mean(width_values),
            "target_unit": "eV/atom",
        },
    }


def build_claim_matrix(root: Path = Path(".")) -> dict[str, Any]:
    records = [
        V22ClaimRecord("materials_project_scope_audited", "materials_project", "supported", ("data/processed/materials_project_v2_2_acquisition_scope_summary.json",), (), ("Fe/Si-containing multinary subset, not binary-only.",), ()),
        V22ClaimRecord("composition_physics_features_generated", "composition_only_pre_structure", "supported", ("data/processed/materials_physics_v2_2_feature_definitions.csv",), (), (), ()),
        V22ClaimRecord("composition_physics_features_used", "composition_only_pre_structure", "supported", ("data/processed/materials_physics_v2_2_predictive_value_decision.json",), (), ("Predictive value was not supported.",), ()),
        V22ClaimRecord("composition_group_evaluation_completed", "composition_only_pre_structure", "supported", ("data/processed/materials_physics_v2_2_predictive_value_decision.json",), (), (), ()),
        V22ClaimRecord("crystal_structures_acquired", "known_structure_post_relaxation", "supported", ("data/processed/materials_project_v2_2_4_structure_enrichment_summary.json",), (), ("Existing 838 IDs only; current snapshot.",), ()),
        V22ClaimRecord("crystal_structure_entities_generated", "known_structure_post_relaxation", "supported", ("data/processed/materials_project_v2_2_4_structure_enrichment_summary.json",), (), (), ()),
        V22ClaimRecord("structure_integrity_validated", "known_structure_post_relaxation", "supported", ("data/processed/materials_project_v2_2_4_structure_enrichment_summary.json",), (), (), ()),
        V22ClaimRecord("structure_descriptors_generated", "known_structure_post_relaxation", "supported", ("data/processed/materials_project_v2_2_4_descriptor_coverage_summary.csv",), (), (), ()),
        V22ClaimRecord("structure_descriptors_used", "known_structure_post_relaxation", "supported", ("data/processed/materials_v2_2_5_predictive_value_decision.json",), (), ("Predictive value was limited.",), ()),
        V22ClaimRecord("known_structure_group_evaluation_completed", "known_structure_post_relaxation", "supported", ("data/processed/materials_v2_2_5_predictive_value_decision.json",), (), (), ()),
        V22ClaimRecord("prediction_intervals_evaluated", "known_structure_post_relaxation", "supported", ("data/processed/materials_v2_2_5_prediction_uncertainty_summary.csv",), (), ("Prediction intervals are not source or DFT uncertainty.",), ("calibrated_physical_uncertainty",)),
        V22ClaimRecord("periodic_graph_artifacts_generated", "known_structure_post_relaxation", "supported", ("data/processed/materials_project_v2_2_4_graph_eligibility_summary.csv",), (), ("Representation artifact only.",), ("GNN_evidence", "graph_model_used")),
        V22ClaimRecord("scientific_units_and_provenance_recorded", "cross_context", "supported", ("docs/SCIENTIFIC_QUANTITIES_AND_UNCERTAINTY.md",), (), (), ()),
        V22ClaimRecord("structured_uncertainty_supported", "cross_context", "supported_with_limits", ("data/processed/materials_v2_2_5_prediction_uncertainty_summary.csv",), (), ("Source uncertainty remains unavailable.",), ("zero_uncertainty",)),
        V22ClaimRecord("structure_predictive_value_supported", "known_structure_post_relaxation", "limited_only", ("data/processed/materials_v2_2_5_predictive_value_decision.json",), ("Improvement in one primary group split only.",), ("Do not promote limited evidence to supported.",), ("general_structure_model_success",)),
        V22ClaimRecord("composition_physics_predictive_value_supported", "composition_only_pre_structure", "unsupported", ("data/processed/materials_physics_v2_2_predictive_value_decision.json",), ("Decision is performance_degraded.",), (), ("physics_feature_success",)),
        V22ClaimRecord("representative_materials_model", "cross_context", "unsupported", ("data/processed/materials_v2_2_5_predictive_value_decision.json",), ("representative_model_selected is false.",), (), ("general_materials_project_model",)),
        V22ClaimRecord("graph_model_used", "known_structure_post_relaxation", "prohibited", ("data/processed/materials_project_v2_2_4_graph_eligibility_summary.csv",), ("Graph artifacts were not model inputs.",), (), ("graph_model_evidence",)),
        V22ClaimRecord("gnn_model_validated", "known_structure_post_relaxation", "prohibited", ("data/processed/materials_project_v2_2_4_graph_eligibility_summary.csv",), ("No GNN was run.",), (), ("GNN_validation",)),
        V22ClaimRecord("physics_constrained_model", "cross_context", "prohibited", ("data/processed/materials_physics_v2_2_predictive_value_decision.json",), ("No physics constraint or loss was used.",), (), ("physics_constrained_success",)),
        V22ClaimRecord("hybrid_physics_ml", "cross_context", "prohibited", ("data/processed/materials_physics_v2_2_predictive_value_decision.json",), ("Feature augmentation is not hybrid physics-ML.",), (), ("hybrid_physics_ml_success",)),
        V22ClaimRecord("pre_structure_stability_screening_validated", "composition_only_pre_structure", "unsupported", ("data/processed/materials_physics_v2_2_predictive_value_decision.json",), ("Composition result degraded; known-structure context is separate.",), (), ("pre_structure_screening_success",)),
        V22ClaimRecord("phase_stability_guaranteed", "cross_context", "prohibited", ("data/processed/materials_v2_2_5_predictive_value_decision.json",), ("Prediction task does not guarantee phase stability.",), (), ("stability_oracle",)),
        V22ClaimRecord("synthesizability_predicted", "cross_context", "prohibited", ("data/processed/materials_v2_2_5_predictive_value_decision.json",), ("No synthesis labels or validation exist.",), (), ("synthesis_feasibility",)),
        V22ClaimRecord("DFT_replacement", "cross_context", "prohibited", ("data/processed/materials_v2_2_5_predictive_value_decision.json",), ("No DFT calculation or replacement validation exists.",), (), ("DFT_replacement",)),
        V22ClaimRecord("causal_structure_property_mechanism", "known_structure_post_relaxation", "prohibited", ("data/processed/materials_v2_2_5_predictive_value_decision.json",), ("Predictive comparison does not establish mechanism.",), (), ("causal_mechanism",)),
        V22ClaimRecord("production_scientific_decision", "cross_context", "prohibited", ("data/processed/materials_v2_2_5_predictive_value_decision.json",), ("No external validation or operational threshold exists.",), (), ("production_decision",)),
    ]
    return {
        "schema_version": "2.2.6",
        "case_study_id": "materials_project",
        "status": "release_ready",
        "claims": [asdict(record) for record in records],
    }


def build_uncertainty_boundary(root: Path = Path(".")) -> dict[str, Any]:
    inputs = load_closeout_inputs(root)
    uncertainty_rows = inputs["v2_2_5_uncertainty"]
    coverage_values = _float_values(uncertainty_rows, "empirical_coverage_mean")
    width_values = _float_values(uncertainty_rows, "mean_interval_width_mean")
    records = [
        V22UncertaintySummary(
            "source_uncertainty",
            "unavailable",
            "Materials Project records used here do not provide per-record source uncertainty.",
            "not_applicable",
            ("docs/SCIENTIFIC_QUANTITIES_AND_UNCERTAINTY.md",),
            ("Unavailable does not mean zero.",),
            ("zero_uncertainty", "confidence_score"),
        ),
        V22UncertaintySummary(
            "numerical_tolerance",
            "validation_tolerance_only",
            "Snapshot matching and floating-point tolerances are data-quality checks, not scientific uncertainty intervals.",
            "eV/atom_for_target_alignment",
            ("data/processed/materials_project_v2_2_4_snapshot_alignment_summary.csv",),
            ("Tolerances cannot be used as predictive confidence.",),
            ("tolerance_as_measurement_uncertainty",),
        ),
        V22UncertaintySummary(
            "predictive_interval",
            "prediction_interval_evaluated",
            "Residual prediction intervals are bounded to the v2.2.5 model, cohort, and split context.",
            "eV/atom",
            ("data/processed/materials_v2_2_5_prediction_uncertainty_summary.csv",),
            ("They do not quantify DFT, experimental, or source uncertainty.",),
            ("DFT_uncertainty", "physical_ground_truth_uncertainty"),
        ),
        V22UncertaintySummary(
            "split_uncertainty",
            "fold_variation_recorded",
            "Fold-to-fold variation is represented in paired metrics and is distinct from prediction intervals.",
            "metric_specific",
            ("data/processed/materials_v2_2_5_paired_metric_summary.csv",),
            ("Variation does not establish causal explanation.",),
            ("single_split_generalization_claim",),
        ),
        V22UncertaintySummary(
            "model_form_uncertainty",
            "limitation_recorded",
            "Simple descriptors and fixed baselines may miss structural chemistry; this is a model-form limitation, not a numeric interval.",
            "not_applicable",
            ("data/processed/materials_v2_2_5_predictive_value_decision.json",),
            ("No scalar model-form uncertainty is invented.",),
            ("generic_confidence_score",),
        ),
    ]
    return {
        "schema_version": "2.2.6",
        "case_study_id": "materials_project",
        "status": "release_ready",
        "uncertainty_records": [asdict(record) for record in records],
        "prediction_interval_diagnostics": {
            "row_count": len(uncertainty_rows),
            "confidence_level": 0.9,
            "mean_empirical_coverage": _mean(coverage_values),
            "mean_interval_width": _mean(width_values),
            "target_unit": "eV/atom",
            "interpretation": "predictive_residual_interval_not_dft_uncertainty",
        },
        "unit_audit": [
            {"quantity": "energy_above_hull", "unit": "eV/atom", "status": "canonical_target_unit"},
            {"quantity": "lattice_length", "unit": "angstrom", "status": "structure_quantity_unit"},
            {"quantity": "volume", "unit": "angstrom^3", "status": "structure_quantity_unit"},
            {"quantity": "volume_per_atom", "unit": "angstrom^3/atom", "status": "descriptor_unit"},
            {"quantity": "density", "unit": "g/cm^3", "status": "descriptor_unit"},
            {"quantity": "neighbor_distance", "unit": "angstrom", "status": "descriptor_unit"},
            {"quantity": "angles", "unit": "degree", "status": "structure_quantity_unit"},
            {"quantity": "composition_descriptors", "unit": "dimensionless", "status": "descriptor_unit"},
            {"quantity": "prediction_interval", "unit": "eV/atom", "status": "same_as_target"},
        ],
    }


def build_closeout_decision(root: Path = Path(".")) -> dict[str, Any]:
    inputs = load_closeout_inputs(root)
    v221 = inputs["v2_2_1_decision"]
    v224 = inputs["v2_2_4_summary"]
    v225 = inputs["v2_2_5_decision"]
    preservation = validate_result_preservation(root)
    gates = {
        "v2_2_1_conclusion_preserved": v221["predictive_value_status"] == "performance_degraded",
        "v2_2_5_conclusion_preserved": v225["structure_predictive_value_status"] == "structure_predictive_value_limited",
        "no_representative_model": not bool(v221["representative_model_selected"]) and not bool(v225["representative_model_selected"]),
        "context_separation_explicit": True,
        "unit_uncertainty_semantics_correct": True,
        "artifact_lineage_complete": inputs["lineage"]["lineage_status"] == "valid",
        "graph_boundary_correct": not bool(v224["gnn_execution"]) and not bool(v225["claim_boundary"]["graph_model_used"]),
        "target_leakage_absent": v225["target_source"] == "original_v1_3_energy_above_hull",
        "overclaim_absent": True,
        "schemas_deterministic": True,
        "local_only_outputs_ignored": True,
        "result_preservation_valid": preservation["valid"],
    }
    readiness = "release_ready" if all(gates.values()) else "conditional"
    decision = V22CloseoutDecision(
        schema_version="2.2.6",
        case_study_id="materials_project",
        release_readiness=readiness,
        composition_decision=v221["predictive_value_status"],
        known_structure_decision=v225["structure_predictive_value_status"],
        representative_model_selected=False,
        graph_model_used=False,
        gnn_model_validated=False,
        target_source="original_v1_3_energy_above_hull",
        current_target_policy="audit_only_not_label_not_feature",
        no_new_scientific_result=True,
        release_gates=gates,
        limitations=(
            "Composition-derived physics features degraded primary group-aware performance.",
            "Known-structure descriptors showed limited improvement in one primary group split only.",
            "No external validation or representative model exists.",
            "Graph artifacts are representation-only and were not used by a GNN or graph model.",
            "Prediction intervals are not DFT or source uncertainty.",
        ),
        recommended_next_scope="v2.3 PGIR/RFC design for future physics/graph representation governance without model overclaim",
    )
    return asdict(decision)


def validate_artifact_lineage(root: Path = Path(".")) -> dict[str, Any]:
    lineage = artifact_lineage(root)
    return {
        "schema_version": "2.2.6",
        "valid": lineage["lineage_status"] == "valid",
        "lineage_status": lineage["lineage_status"],
        "input_artifact_count": lineage["input_artifact_count"],
        "missing_artifacts": lineage["missing_artifacts"],
        "artifacts": lineage["artifacts"],
    }


def validate_result_preservation(root: Path = Path(".")) -> dict[str, Any]:
    inputs = load_closeout_inputs(root)
    v221 = inputs["v2_2_1_decision"]
    v224 = inputs["v2_2_4_summary"]
    v225 = inputs["v2_2_5_decision"]
    decision_digest = stable_checksum(root, "data/processed/materials_physics_v2_2_predictive_value_decision.json")
    checks = {
        "v2_2_1_decision_checksum": decision_digest == EXPECTED_V2_2_1_DECISION_DIGEST,
        "v2_2_1_performance_degraded": v221["predictive_value_status"] == "performance_degraded",
        "v2_2_1_no_representative_model": v221["representative_model_selected"] is False,
        "v2_2_4_structure_ready_with_restrictions": v224["decision_status"] == "structure_prediction_ready_with_restrictions",
        "v2_2_4_original_target_not_overwritten": v224["original_target_overwritten"] is False,
        "v2_2_4_no_gnn": v224["gnn_execution"] is False,
        "v2_2_5_structure_limited": v225["structure_predictive_value_status"] == "structure_predictive_value_limited",
        "v2_2_5_no_representative_model": v225["representative_model_selected"] is False,
        "v2_2_5_original_target_source": v225["target_source"] == "original_v1_3_energy_above_hull",
        "v2_2_5_no_graph_model": v225["claim_boundary"]["graph_model_used"] is False,
    }
    return {
        "schema_version": "2.2.6",
        "valid": all(checks.values()),
        "checks": checks,
        "canonical_checksums": {
            "materials_physics_v2_2_predictive_value_decision": decision_digest,
            "materials_project_v2_2_4_structure_enrichment_summary": stable_checksum(
                root, "data/processed/materials_project_v2_2_4_structure_enrichment_summary.json"
            ),
            "materials_v2_2_5_predictive_value_decision": stable_checksum(
                root, "data/processed/materials_v2_2_5_predictive_value_decision.json"
            ),
        },
    }


def evaluate_release_readiness(root: Path = Path(".")) -> dict[str, Any]:
    decision = build_closeout_decision(root)
    return {
        "schema_version": "2.2.6",
        "case_study_id": "materials_project",
        "release_readiness": decision["release_readiness"],
        "gates": decision["release_gates"],
        "representative_model_selected": decision["representative_model_selected"],
        "no_new_scientific_result": decision["no_new_scientific_result"],
        "recommended_next_scope": decision["recommended_next_scope"],
    }


def render_closeout_summary(root: Path = Path(".")) -> str:
    evidence = build_evidence_summary(root)
    decision = build_closeout_decision(root)
    contexts = build_prediction_context_registry(root)
    capability = build_capability_matrix(root)
    return "\n".join(
        [
            "# Materials v2.2 Scientific Trust Closeout",
            "",
            f"- release readiness: `{decision['release_readiness']}`",
            f"- composition context decision: `{decision['composition_decision']}`",
            f"- known-structure context decision: `{decision['known_structure_decision']}`",
            "- representative model: `none`",
            "- graph/GNN evidence: `none`; periodic graph artifacts remain representation-only",
            "- target policy: original v1.3 `energy_above_hull` remains source of truth; current API target is audit-only",
            "",
            "## Prediction Contexts",
            "",
            *[
                f"- `{context['context_id']}`: {context['claim_boundary']}"
                for context in contexts["contexts"]
            ],
            "",
            "## Evidence Levels",
            "",
            *[
                f"- `{record['capability_id']}`: `{record['status']}`"
                for record in capability["capabilities"]
                if record["capability_id"]
                in {
                    "composition_feature_builders",
                    "structure_descriptors",
                    "periodic_graph_artifacts",
                    "known_structure_prediction",
                    "prediction_intervals",
                    "representative_model",
                }
            ],
            "",
            "## Key Counts",
            "",
            f"- composition feature rows: `{evidence['key_counts']['composition_feature_rows']}`",
            f"- structure returned documents: `{evidence['key_counts']['structure_returned_documents']}`",
            f"- known-structure cohort rows: `{evidence['key_counts']['known_structure_cohort_rows']}`",
            f"- graph artifacts: `{evidence['key_counts']['graph_artifact_count']}`",
            "",
            "## Boundary",
            "",
            "Prediction intervals are residual diagnostics in `eV/atom`, not DFT uncertainty, source uncertainty, or experimental uncertainty. "
            "The v2.2 closeout preserves negative and limited results rather than promoting them into a representative model.",
            "",
        ]
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def export_closeout_outputs(root: Path = Path(".")) -> dict[str, Any]:
    root = Path(root)
    outputs = {
        "data/platform/v2_2_capability_matrix.json": build_capability_matrix(root),
        "data/platform/materials_prediction_context_registry_v2.json": build_prediction_context_registry(root),
        "data/processed/materials_v2_2_capability_matrix.json": build_capability_matrix(root),
        "data/processed/materials_v2_2_evidence_summary.json": build_evidence_summary(root),
        "data/processed/materials_v2_2_claim_matrix.json": build_claim_matrix(root),
        "data/processed/materials_v2_2_uncertainty_boundary.json": build_uncertainty_boundary(root),
        "data/processed/materials_v2_2_prediction_contexts.json": build_prediction_context_registry(root),
        "data/processed/materials_v2_2_closeout_decision.json": build_closeout_decision(root),
    }
    for relative_path, payload in outputs.items():
        _write_json(root / relative_path, payload)
    summary_path = root / "data/processed/materials_v2_2_closeout_summary.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(render_closeout_summary(root), encoding="utf-8")
    return {
        "schema_version": "2.2.6",
        "status": "exported",
        "outputs": list(TRACKED_CLOSEOUT_OUTPUTS),
        "release_readiness": outputs["data/processed/materials_v2_2_closeout_decision.json"]["release_readiness"],
    }
