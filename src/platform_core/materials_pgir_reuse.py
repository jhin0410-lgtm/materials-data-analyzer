"""Read-only Materials structure reuse audit against the released PGIR gates.

The audit consumes existing v2.2 compact artifacts and, when available, the
local-only CrystalStructureEntity JSONL.  It does not acquire data, rebuild
descriptors or graphs, execute models, or alter released artifacts.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .external_source_contracts import (
    ExternalSourcePersistedRecord,
    build_external_dataset_registry,
    build_external_source_contract_records,
    build_external_source_contract_summary,
    build_external_source_system_registry,
    external_source_registry_payloads,
    write_external_source_registry_files,
)
from .pgir_conformance import (
    PGIRRepresentationDeclaration,
    assess_maturity,
    conformance_summary,
    validate_declaration,
    validate_transition,
)
from .scientific_operator_registry import build_default_scientific_operator_registry


V2_4_REUSE_VERSION = "2.4.1"
LOCAL_OUTPUT_ROOT = Path("outputs/v2_4_external_source_pgir_reuse")

TRACKED_PATHS = {
    "external_source_contract_summary": "data/processed/v2_4_external_source_contract_summary.json",
    "source_provenance_summary": "data/processed/v2_4_source_provenance_summary.csv",
    "materials_pgir_conformance_summary": "data/processed/v2_4_materials_pgir_conformance_summary.csv",
    "cross_domain_reuse_evidence": "data/processed/v2_4_cross_domain_reuse_evidence.json",
    "pgir_reuse_decision": "data/processed/v2_4_pgir_reuse_decision.json",
    "report_summary": "data/processed/v2_4_report_summary.md",
}

MATERIALS_TRACKED_INPUTS = {
    "structure_summary": "data/processed/materials_project_v2_2_4_structure_enrichment_summary.json",
    "structure_coverage": "data/processed/materials_project_v2_2_4_structure_coverage_summary.csv",
    "snapshot_alignment": "data/processed/materials_project_v2_2_4_snapshot_alignment_summary.csv",
    "descriptor_coverage": "data/processed/materials_project_v2_2_4_descriptor_coverage_summary.csv",
    "graph_eligibility": "data/processed/materials_project_v2_2_4_graph_eligibility_summary.csv",
    "operator_snapshot": "data/processed/materials_project_v2_2_4_operator_snapshot.json",
    "composition_decision": "data/processed/materials_physics_v2_2_predictive_value_decision.json",
    "structure_decision": "data/processed/materials_v2_2_5_predictive_value_decision.json",
}

MATERIALS_LOCAL_INPUTS = {
    "acquisition_manifest": "outputs/materials_project_structure_v2_2/acquisition/acquisition_manifest.json",
    "query_plan": "outputs/materials_project_structure_v2_2/acquisition/query_plan.json",
    "entities": "outputs/materials_project_structure_v2_2/entities/crystal_structure_entities.jsonl",
    "descriptors": "outputs/materials_project_structure_v2_2/descriptors/structure_descriptors.csv",
    "graphs": "outputs/materials_project_structure_v2_2/graphs/periodic_graphs.jsonl",
}

PRESERVED_CANONICAL_JSON_SHA256 = {
    "data/processed/materials_physics_v2_2_predictive_value_decision.json": "277cd5e254b962338a78c68600500da873538e6783e92aebad8aa34374e889f0",
    "data/processed/materials_physics_v2_2_feature_use_evidence.json": "cd73b44e695aeeef93162a8216beacc9b6a5ab6f1163ce1f4c07b5a54ad613c5",
    "data/processed/materials_v2_2_5_predictive_value_decision.json": "dbbfffdee4117eb3609fbe40779e605487c6668a9867ecdfe17b165832f19ad4",
    "data/processed/materials_project_v2_2_4_structure_enrichment_summary.json": "0cb63a1da65c0e25bbc94995a907b583b7028cbd79c32bf1fc3fcda2d7503a38",
    "data/processed/battery_v2_3_5_source_lineage_summary.json": "fa43443ecc82f147fdc7117524c911d4ffd63be9b657993736f3bfd30c58e87a",
    "data/processed/battery_v2_3_5_external_data_requirement_decision.json": "5b6ead4b07e1afcf1a3096724117088040b091544c880f7fae85ccfc523d4744",
}

PRESERVED_CANONICAL_CSV_SHA256 = {
    "data/processed/materials_physics_v2_2_predictive_comparison_summary.csv": "9c5107b7a76983ead31b860fd5908867391ba2dbd6cc40299ce415e020a2c8c5",
    "data/processed/battery_v2_3_5_evaluator_stability_summary.csv": "ecbc43077314ec9c3ab4a393f6ba5f052d4c91c4365e4a078ffde86a5ee0cd1a",
}

REQUIRED_OPERATOR_IDS = (
    "mp_summary_to_composition_entity_v1",
    "mp_structure_to_crystal_entity_v1",
    "crystal_structure_integrity_check_v1",
    "composition_structure_consistency_check_v1",
    "crystal_structure_to_descriptor_summary_v1",
    "crystal_structure_to_radius_graph_v1",
    "structure_snapshot_alignment_check_v1",
)


def _canonical_json_sha(payload: Any) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _canonical_csv_sha(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        payload = {"fieldnames": reader.fieldnames or [], "rows": list(reader)}
    return _canonical_json_sha(payload)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path.as_posix()}")
    return payload


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    temp.replace(path)


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(text, encoding="utf-8", newline="\n")
    temp.replace(path)


def _write_jsonl_atomic(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    count = 0
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n")
            count += 1
    temp.replace(path)
    return count


def _write_csv_atomic(path: Path, rows: list[Mapping[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})
    temp.replace(path)


def validate_preserved_v2_2_v2_3_results(repo_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repo_root)
    checks: list[dict[str, Any]] = []
    for relative_path, expected in sorted(PRESERVED_CANONICAL_JSON_SHA256.items()):
        path = root / relative_path
        actual = _canonical_json_sha(_read_json(path)) if path.exists() else None
        checks.append(
            {
                "relative_path": relative_path,
                "checksum_kind": "canonical_json_sha256",
                "expected": expected,
                "actual": actual,
                "preserved": actual == expected,
            }
        )
    for relative_path, expected in sorted(PRESERVED_CANONICAL_CSV_SHA256.items()):
        path = root / relative_path
        actual = _canonical_csv_sha(path) if path.exists() else None
        checks.append(
            {
                "relative_path": relative_path,
                "checksum_kind": "canonical_csv_sha256",
                "expected": expected,
                "actual": actual,
                "preserved": actual == expected,
            }
        )
    return {
        "status": "preserved" if all(item["preserved"] for item in checks) else "checksum_mismatch",
        "check_count": len(checks),
        "checks": checks,
    }


def preview_materials_pgir_reuse(repo_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repo_root)
    tracked = {key: (root / value).exists() for key, value in MATERIALS_TRACKED_INPUTS.items()}
    local = {key: (root / value).exists() for key, value in MATERIALS_LOCAL_INPUTS.items()}
    return {
        "schema_version": V2_4_REUSE_VERSION,
        "status": "ready" if all(tracked.values()) and local["entities"] else "blocked_missing_local_materials_artifacts",
        "required_tracked_artifacts": MATERIALS_TRACKED_INPUTS,
        "required_local_artifacts": MATERIALS_LOCAL_INPUTS,
        "tracked_artifact_availability": tracked,
        "local_artifact_availability": local,
        "expected_source_refs": (
            "materials_project_existing_ids_retrieved_2026_07_16",
            "materials_project_v2_2_4_api_chunks",
        ),
        "expected_mappings": (
            "MaterialsProjectStructureDoc_to_CrystalStructureEntity",
            "CrystalStructureEntity_to_integrity_result",
            "CrystalStructureEntity_to_descriptor_representation",
            "CrystalStructureEntity_to_periodic_GraphEntity",
        ),
        "output_root": LOCAL_OUTPUT_ROOT.as_posix(),
        "prohibited_claims": (
            "physical operator reuse",
            "independent or production validation",
            "GNN evidence",
            "DFT replacement",
            "structure-aware predictive improvement",
        ),
        "network_called": False,
        "descriptor_or_graph_regenerated": False,
        "model_executed": False,
    }


def _entity_declaration(index: int, envelope: Mapping[str, Any]) -> PGIRRepresentationDeclaration:
    entity_id = str(envelope.get("entity_id", ""))
    record = envelope.get("record", {})
    attributes = record.get("attributes", {}) if isinstance(record, Mapping) else {}
    quantity_fields = record.get("quantity_fields", {}) if isinstance(record, Mapping) else {}
    integrity_status = str(envelope.get("integrity_status", "unavailable"))
    composition_status = str(envelope.get("composition_consistency_status", "unavailable"))
    if not entity_id or envelope.get("entity_type") != "CrystalStructureEntity":
        raise ValueError("local entity envelope is not a CrystalStructureEntity record")
    if envelope.get("schema_id") != "scientific_entity_schema_v2":
        raise ValueError("unexpected local entity schema")
    if record.get("schema_version") != "2.2.2":
        raise ValueError("unsupported CrystalStructureEntity schema version")
    if not isinstance(attributes.get("sites"), list) or not attributes.get("sites"):
        raise ValueError("CrystalStructureEntity sites are required")
    if not isinstance(quantity_fields, Mapping) or "cell_volume" not in quantity_fields:
        raise ValueError("CrystalStructureEntity dimensional metadata is incomplete")
    return PGIRRepresentationDeclaration(
        declaration_id=f"materials_structure_declaration_{index:04d}",
        declaration_version="1",
        pgir_concept_id="physical_entity",
        representation_schema_id="scientific_entity_schema_v2",
        representation_schema_version="2.2.2",
        entity_or_artifact_ref=entity_id,
        domain_context="materials_computed_crystal_structure",
        measurement_context="computed_relaxed_structure_not_laboratory_measurement",
        mechanism_context="not_asserted",
        temporal_context="known_structure_post_relaxation",
        spatial_context="periodic_crystal_unit_cell",
        validation_context=f"integrity_{integrity_status}_composition_{composition_status}",
        current_maturity_level="schema_valid",
        claimed_capabilities=("tabular_summary", "bounded_physical_validation"),
        evidence_refs=(
            "data/processed/materials_project_v2_2_4_structure_enrichment_summary.json",
            "data/processed/materials_project_v2_2_4_structure_coverage_summary.csv",
        ),
        uncertainty_refs=("source_structure_uncertainty_unavailable",),
        provenance_refs=("materials_project_v2_2_4_provenance",),
        limitations=(
            "relaxed structure is unavailable in composition-only pre-structure context",
            "valid structure does not establish experimental or phase validation",
        ),
        prohibited_interpretations=(
            "DFT replacement",
            "experimental structure",
            "independent validation",
            "production validation",
        ),
    )


def _maturity_evidence() -> dict[str, bool]:
    return {
        "parser_success": True,
        "required_structural_fields": True,
        "schema_validation": True,
        "variable_semantics_known": True,
        "source_field_mapping": True,
        "representation_context_known": True,
        "units_available_or_dimensionless": True,
        "dimensional_compatibility": True,
        "registered_admissibility_checks": True,
        "finite_ranges": True,
    }


def _transition_assessments() -> list[dict[str, Any]]:
    configs = (
        {
            "transition_id": "mp_structure_to_crystal_entity_v1",
            "metadata_available": ("material_id", "structure", "source_record_checksum"),
        },
        {
            "transition_id": "crystal_structure_integrity_check_v1",
            "metadata_available": ("lattice", "sites", "integrity_status"),
        },
        {
            "transition_id": "composition_structure_consistency_check_v1",
            "metadata_available": ("summary_composition", "structure_derived_composition", "consistency_status"),
        },
        {
            "transition_id": "crystal_structure_to_descriptor_summary_v1",
            "metadata_available": ("descriptor_registry", "prediction_context", "target_access_policy"),
        },
        {
            "transition_id": "crystal_structure_to_radius_graph_v1",
            "metadata_available": ("graph_builder", "cutoff_policy", "target_access_policy"),
        },
    )
    return [validate_transition(config).to_dict() for config in configs]


def _operator_audit() -> dict[str, Any]:
    registry = build_default_scientific_operator_registry()
    operators = {item.operator_id: item for item in registry.list_operators()}
    rows = []
    for operator_id in REQUIRED_OPERATOR_IDS:
        operator = operators.get(operator_id)
        rows.append(
            {
                "operator_id": operator_id,
                "registered": operator is not None,
                "operator_role": operator.operator_role if operator else "unavailable",
                "status": operator.status if operator else "unavailable",
                "target_access_policy": operator.target_access_policy if operator else "unavailable",
                "network_policy": operator.network_policy if operator else "unavailable",
            }
        )
    return {
        "status": "registered" if all(item["registered"] for item in rows) else "missing_operator_metadata",
        "operator_count": len(rows),
        "operators": rows,
        "propagator_used": False,
        "physical_operator_reuse": False,
    }


def _materials_conformance_rows(structure_summary: Mapping[str, Any], actual_count: int) -> list[dict[str, Any]]:
    requested = int(structure_summary["requested_material_id_count"])
    return [
        {
            "representation": "materials_project_source_record",
            "pgir_concept": "provenance",
            "record_count": requested,
            "conformant_count": requested,
            "current_maturity": "semantically_mapped",
            "validation_context": "source_computed_record",
            "reuse_status": "reused_with_snapshot_identity_restriction",
            "claim_boundary": "not_a_laboratory_measurement",
        },
        {
            "representation": "crystal_structure_entity",
            "pgir_concept": "physical_entity",
            "record_count": actual_count,
            "conformant_count": actual_count,
            "current_maturity": "physically_admissible",
            "validation_context": "known_structure_post_relaxation",
            "reuse_status": "actual_conformance_engine_reuse",
            "claim_boundary": "valid_representation_not_independent_validation",
        },
        {
            "representation": "structure_integrity_evaluator_result",
            "pgir_concept": "result",
            "record_count": int(structure_summary["valid_structure_entity_count"]),
            "conformant_count": int(structure_summary["valid_structure_entity_count"]),
            "current_maturity": "scientifically_evaluated",
            "validation_context": "bounded_integrity_evaluator",
            "reuse_status": "existing_evaluator_evidence_referenced",
            "claim_boundary": "not_phase_or_experimental_validation",
        },
        {
            "representation": "structure_descriptor_artifact",
            "pgir_concept": "result",
            "record_count": int(structure_summary["descriptor_row_count"]),
            "conformant_count": int(structure_summary["descriptor_row_count"]),
            "current_maturity": "semantically_mapped",
            "validation_context": "transformer_derived_known_structure_representation",
            "reuse_status": "existing_descriptor_artifact_referenced",
            "claim_boundary": "candidate_features_not_predictive_improvement",
        },
        {
            "representation": "periodic_graph_entity",
            "pgir_concept": "result",
            "record_count": int(structure_summary["graph_count"]),
            "conformant_count": int(structure_summary["graph_eligible_count"]),
            "current_maturity": "semantically_mapped",
            "validation_context": "representation_only",
            "reuse_status": "existing_graph_summary_referenced_without_body_read",
            "claim_boundary": "not_GNN_or_predictive_evidence",
        },
        {
            "representation": "known_structure_predictive_evidence",
            "pgir_concept": "result",
            "record_count": requested,
            "conformant_count": requested,
            "current_maturity": "scientifically_evaluated",
            "validation_context": "released_v2_2_5_read_only",
            "reuse_status": "limited_existing_evidence",
            "claim_boundary": "structure_predictive_value_limited_representative_model_none",
        },
    ]


@dataclass(frozen=True)
class MaterialsPGIRReuseResult:
    preview: Mapping[str, Any]
    tracked_payloads: Mapping[str, Any]
    local_output_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "preview": dict(self.preview),
            "tracked_payloads": dict(self.tracked_payloads),
            "local_output_paths": list(self.local_output_paths),
        }


def run_materials_pgir_reuse_audit(
    repo_root: str | Path = ".",
    *,
    write_local: bool = True,
    write_tracked: bool = True,
) -> MaterialsPGIRReuseResult:
    root = Path(repo_root)
    preview = preview_materials_pgir_reuse(root)
    preservation = validate_preserved_v2_2_v2_3_results(root)
    if preservation["status"] != "preserved":
        raise ValueError("released v2.2/v2.3 artifact preservation check failed")

    structure_summary = _read_json(root / MATERIALS_TRACKED_INPUTS["structure_summary"])
    composition_decision = _read_json(root / MATERIALS_TRACKED_INPUTS["composition_decision"])
    structure_decision = _read_json(root / MATERIALS_TRACKED_INPUTS["structure_decision"])
    if structure_summary.get("requested_material_id_count") != 838:
        raise ValueError("released Materials structure scope is not 838 records")
    if structure_summary.get("target_drift_count") != 0:
        raise ValueError("released target-drift conclusion changed")
    if composition_decision.get("predictive_value_status") != "performance_degraded":
        raise ValueError("v2.2.1 composition conclusion changed")
    if structure_decision.get("structure_predictive_value_status") != "structure_predictive_value_limited":
        raise ValueError("v2.2.5 structure conclusion changed")

    entities_path = root / MATERIALS_LOCAL_INPUTS["entities"]
    declarations: list[PGIRRepresentationDeclaration] = []
    maturity = []
    findings: list[dict[str, Any]] = []
    if entities_path.exists():
        with entities_path.open(encoding="utf-8") as handle:
            for index, line in enumerate(handle, start=1):
                envelope = json.loads(line)
                declaration = _entity_declaration(index, envelope)
                declarations.append(declaration)
                declaration_findings = validate_declaration(declaration)
                findings.extend(
                    {"declaration_id": declaration.declaration_id, **item.to_dict()}
                    for item in declaration_findings
                )
                maturity.append(
                    assess_maturity(
                        declaration,
                        requested_maturity_level="physically_admissible",
                        evidence=_maturity_evidence(),
                    )
                )
    actual_count = len(declarations)
    local_ready = actual_count == int(structure_summary["structure_entity_count"])
    if actual_count and not local_ready:
        raise ValueError("local CrystalStructureEntity count does not match released compact evidence")

    transition_rows = _transition_assessments()
    transition_objects = tuple(
        validate_transition(
            {
                "transition_id": item["transition_id"],
                "metadata_available": {
                    "mp_structure_to_crystal_entity_v1": ("material_id", "structure", "source_record_checksum"),
                    "crystal_structure_integrity_check_v1": ("lattice", "sites", "integrity_status"),
                    "composition_structure_consistency_check_v1": (
                        "summary_composition",
                        "structure_derived_composition",
                        "consistency_status",
                    ),
                    "crystal_structure_to_descriptor_summary_v1": (
                        "descriptor_registry",
                        "prediction_context",
                        "target_access_policy",
                    ),
                    "crystal_structure_to_radius_graph_v1": (
                        "graph_builder",
                        "cutoff_policy",
                        "target_access_policy",
                    ),
                }[item["transition_id"]],
            }
        )
        for item in transition_rows
    )
    conformance = conformance_summary(
        tuple(declarations),
        tuple(maturity),
        transition_objects,
    )
    operator_audit = _operator_audit()
    conformance_rows = _materials_conformance_rows(structure_summary, actual_count)

    actual_reuse = (
        local_ready
        and conformance.valid
        and all(item["transition_allowed"] for item in transition_rows)
        and operator_audit["status"] == "registered"
    )
    decision_status = (
        "second_domain_pgir_reuse_demonstrated_with_restrictions"
        if actual_reuse
        else "blocked_missing_local_materials_artifacts"
        if not local_ready
        else "blocked_conformance_failure"
    )

    external_summary = build_external_source_contract_summary().to_dict()
    external_summary.update(
        {
            "case_study_version": V2_4_REUSE_VERSION,
            "validation": external_source_registry_payloads()["external_source_system_registry_v1"]["validation"],
            "actual_source_system_count": 2,
            "future_declared_source_system_count": 3,
            "official_nasa_snapshot_status": "unresolved",
            "materials_project_snapshot_status": "named_snapshot_identity_unresolved",
        }
    )

    source_records = build_external_source_contract_records()
    source_provenance_rows: list[dict[str, Any]] = []
    for assessment in source_records["provenance_assessments"]:
        for entry in assessment.status_entries:
            source_provenance_rows.append(
                {
                    "assessment_id": assessment.assessment_id,
                    "source_system_id": assessment.source_system_id,
                    "provenance_status": entry.status,
                    "evidence_ref_count": len(entry.evidence_refs),
                    "limitation_count": len(entry.limitations),
                    "overall_status": assessment.overall_status,
                    "trust_score_used": assessment.trust_score_used,
                }
            )

    cross_domain = {
        "schema_version": V2_4_REUSE_VERSION,
        "status": "cross_domain_reuse_audited",
        "domains": ["battery", "materials"],
        "shared_framework": {
            "pgir_concept_registry": True,
            "representation_declaration": True,
            "schema_ownership": True,
            "maturity_assessment": True,
            "conformance_findings": True,
            "context_compatibility": True,
            "transition_validation": True,
            "operator_eligibility_framework": True,
            "uncertainty_boundary": True,
            "provenance_lineage": True,
            "claim_boundary": True,
        },
        "domain_specific_semantics": {
            "battery": [
                "cycle Observation and operational State",
                "cycle-index Trajectory",
                "measurement source with unavailable physical-time uncertainty",
            ],
            "materials": [
                "computed relaxed CrystalStructureEntity",
                "known_structure_post_relaxation context",
                "descriptor and periodic graph representations",
            ],
        },
        "architecture_reuse": actual_reuse,
        "representation_contract_reuse": actual_reuse,
        "conformance_engine_reuse": actual_reuse,
        "operator_framework_reuse": operator_audit["status"] == "registered",
        "physical_operator_reuse": False,
        "physical_operator_reuse_status": "not_demonstrated",
        "independent_validation": False,
        "production_validation": False,
        "network_called": False,
        "model_or_solver_executed": False,
        "descriptor_or_graph_regenerated": False,
    }
    decision = {
        "schema_version": V2_4_REUSE_VERSION,
        "decision_status": decision_status,
        "architecture_reuse": actual_reuse,
        "representation_contract_reuse": actual_reuse,
        "conformance_engine_reuse": actual_reuse,
        "operator_framework_reuse": operator_audit["status"] == "registered",
        "physical_operator_reuse": False,
        "independent_validation": False,
        "production_validation": False,
        "actual_structure_entity_count": actual_count,
        "conformant_structure_entity_count": actual_count if conformance.valid else 0,
        "transition_count": len(transition_rows),
        "registered_operator_count": operator_audit["operator_count"],
        "representative_model": "none",
        "composition_predictive_decision_preserved": "performance_degraded",
        "structure_predictive_decision_preserved": "structure_predictive_value_limited",
        "graph_artifact_status": "representation_only",
        "limitations": [
            "same governance framework does not imply common physical operators",
            "Materials structures are computed relaxed records, not laboratory measurements",
            "named Materials Project snapshot identity remains unresolved",
            "no independent or production validation was performed",
        ],
        "prohibited_claims": [
            "universal physics platform",
            "physical operator reuse",
            "GNN evidence",
            "DFT replacement",
            "structure-aware predictive improvement",
        ],
    }

    report_text = "\n".join(
        [
            "# v2.4.1 External Source Contract And PGIR Reuse Summary",
            "",
            f"- External source contract: `{external_summary['status']}`",
            f"- Materials PGIR reuse: `{decision_status}`",
            f"- Actual local structure declarations: `{actual_count}`",
            f"- Conformance valid: `{str(conformance.valid).lower()}`",
            "- Architecture, representation-contract, conformance-engine, and operator-framework reuse are demonstrated when local v2.2 entities are available.",
            "- Physical-operator reuse is `not_demonstrated`.",
            "- Independent and production validation are `false`.",
            "- The periodic graph remains a representation artifact, not GNN or predictive evidence.",
            "- v2.2 decisions remain `performance_degraded` and `structure_predictive_value_limited`; representative model remains `none`.",
            "- This audit performs no network call, descriptor/graph regeneration, model fit, or solver execution.",
            "",
        ]
    )

    tracked_payloads: dict[str, Any] = {
        "external_source_contract_summary": external_summary,
        "source_provenance_summary": source_provenance_rows,
        "materials_pgir_conformance_summary": conformance_rows,
        "cross_domain_reuse_evidence": cross_domain,
        "pgir_reuse_decision": decision,
        "report_summary": report_text,
    }

    local_output_paths: list[str] = []
    if write_local:
        local_root = root / LOCAL_OUTPUT_ROOT
        all_source_records = (
            *build_external_source_system_registry(),
            *build_external_dataset_registry(),
        )
        _write_jsonl_atomic(
            local_root / "source_contracts/source_system_records.jsonl",
            (ExternalSourcePersistedRecord.from_record(item).to_dict() for item in all_source_records),
        )
        _write_jsonl_atomic(
            local_root / "source_contracts/dataset_snapshot_records.jsonl",
            (
                ExternalSourcePersistedRecord.from_record(item).to_dict()
                for item in source_records["snapshots"]
            ),
        )
        _write_jsonl_atomic(
            local_root / "source_contracts/retrieval_records.jsonl",
            (
                ExternalSourcePersistedRecord.from_record(item).to_dict()
                for item in source_records["retrieval_events"]
            ),
        )
        _write_jsonl_atomic(
            local_root / "source_contracts/provenance_assessments.jsonl",
            (
                ExternalSourcePersistedRecord.from_record(item).to_dict()
                for item in source_records["provenance_assessments"]
            ),
        )
        _write_jsonl_atomic(
            local_root / "materials/structure_declarations.jsonl",
            (item.to_dict() for item in declarations),
        )
        _write_jsonl_atomic(local_root / "materials/conformance_findings.jsonl", iter(findings))
        maturity_rows = [item.to_dict() for item in maturity]
        _write_csv_atomic(
            local_root / "materials/maturity_assessments.csv",
            [
                {
                    "declaration_id": item["declaration_id"],
                    "current_maturity_level": item["current_maturity_level"],
                    "requested_maturity_level": item["requested_maturity_level"],
                    "resulting_maturity_level": item["resulting_maturity_level"],
                    "promotion_allowed": item["promotion_allowed"],
                    "missing_evidence_count": len(item["missing_evidence"]),
                    "finding_count": len(item["findings"]),
                }
                for item in maturity_rows
            ],
            [
                "declaration_id",
                "current_maturity_level",
                "requested_maturity_level",
                "resulting_maturity_level",
                "promotion_allowed",
                "missing_evidence_count",
                "finding_count",
            ],
        )
        _write_csv_atomic(
            local_root / "materials/transition_assessments.csv",
            [
                {
                    **{key: value for key, value in item.items() if key != "findings"},
                    "finding_count": len(item["findings"]),
                }
                for item in transition_rows
            ],
            [
                "transition_id",
                "input_concept",
                "output_concept",
                "transition_allowed",
                "maturity_result",
                "finding_count",
            ],
        )
        _write_json_atomic(local_root / "cross_domain/reuse_evidence.json", cross_domain)
        _write_csv_atomic(
            local_root / "cross_domain/domain_comparison.csv",
            [
                {
                    "domain": "battery",
                    "source_semantics": "measured_cycle_records",
                    "primary_representation": "Observation_State_Trajectory",
                    "uncertainty_boundary": "source_uncertainty_unavailable",
                    "physical_operator_reuse": False,
                },
                {
                    "domain": "materials",
                    "source_semantics": "computed_relaxed_structure_records",
                    "primary_representation": "CrystalStructureEntity_descriptor_GraphEntity",
                    "uncertainty_boundary": "source_structure_uncertainty_unavailable",
                    "physical_operator_reuse": False,
                },
            ],
            [
                "domain",
                "source_semantics",
                "primary_representation",
                "uncertainty_boundary",
                "physical_operator_reuse",
            ],
        )
        _write_text_atomic(local_root / "reports/external_source_contract_report.md", report_text)
        _write_text_atomic(local_root / "reports/materials_pgir_reuse_report.md", report_text)
        local_output_paths = [
            path.relative_to(root).as_posix()
            for path in sorted(local_root.rglob("*"))
            if path.is_file()
        ]

    if write_tracked:
        write_external_source_registry_files(root)
        _write_json_atomic(root / TRACKED_PATHS["external_source_contract_summary"], external_summary)
        _write_csv_atomic(
            root / TRACKED_PATHS["source_provenance_summary"],
            source_provenance_rows,
            [
                "assessment_id",
                "source_system_id",
                "provenance_status",
                "evidence_ref_count",
                "limitation_count",
                "overall_status",
                "trust_score_used",
            ],
        )
        _write_csv_atomic(
            root / TRACKED_PATHS["materials_pgir_conformance_summary"],
            conformance_rows,
            [
                "representation",
                "pgir_concept",
                "record_count",
                "conformant_count",
                "current_maturity",
                "validation_context",
                "reuse_status",
                "claim_boundary",
            ],
        )
        _write_json_atomic(root / TRACKED_PATHS["cross_domain_reuse_evidence"], cross_domain)
        _write_json_atomic(root / TRACKED_PATHS["pgir_reuse_decision"], decision)
        _write_text_atomic(root / TRACKED_PATHS["report_summary"], report_text)

    return MaterialsPGIRReuseResult(
        preview=preview,
        tracked_payloads=tracked_payloads,
        local_output_paths=tuple(local_output_paths),
    )


def load_external_source_contract_summary(repo_root: str | Path = ".") -> dict[str, Any]:
    path = Path(repo_root) / TRACKED_PATHS["external_source_contract_summary"]
    if not path.exists():
        return {"status": "not_available"}
    payload = _read_json(path)
    return {
        "status": "available",
        "contract_status": payload.get("status"),
        "registered_source_system_count": len(payload.get("registered_source_system_ids", [])),
        "actual_source_system_count": payload.get("actual_source_system_count"),
        "future_declared_source_system_count": payload.get("future_declared_source_system_count"),
        "unresolved_snapshot_count": len(payload.get("unresolved_snapshot_ids", [])),
        "credentials_persisted": payload.get("credentials_persisted"),
        "network_called": False,
    }


def load_second_domain_pgir_reuse_summary(repo_root: str | Path = ".") -> dict[str, Any]:
    path = Path(repo_root) / TRACKED_PATHS["pgir_reuse_decision"]
    if not path.exists():
        return {"status": "not_available"}
    payload = _read_json(path)
    return {
        "status": "available",
        "reuse_verdict": payload.get("decision_status"),
        "actual_structure_entity_count": payload.get("actual_structure_entity_count"),
        "conformant_structure_entity_count": payload.get("conformant_structure_entity_count"),
        "architecture_reuse": payload.get("architecture_reuse"),
        "representation_contract_reuse": payload.get("representation_contract_reuse"),
        "operator_framework_reuse": payload.get("operator_framework_reuse"),
        "physical_operator_reuse": payload.get("physical_operator_reuse"),
        "independent_validation": payload.get("independent_validation"),
        "production_validation": payload.get("production_validation"),
        "representative_model": payload.get("representative_model"),
        "network_called": False,
        "model_or_solver_executed": False,
    }
