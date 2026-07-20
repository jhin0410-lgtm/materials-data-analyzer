import csv
import json
from pathlib import Path

from src.platform_core.materials_pgir_reuse import (
    load_second_domain_pgir_reuse_summary,
    preview_materials_pgir_reuse,
    run_materials_pgir_reuse_audit,
)
from src.platform_core.pgir_conformance import validate_transition


def test_materials_transitions_are_registered_metadata_only():
    cases = {
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
        "crystal_structure_to_radius_graph_v1": ("graph_builder", "cutoff_policy", "target_access_policy"),
    }
    for transition_id, metadata in cases.items():
        result = validate_transition({"transition_id": transition_id, "metadata_available": metadata})
        assert result.transition_allowed is True


def test_tracked_materials_pgir_summary_preserves_restricted_reuse_boundary():
    decision = json.loads(Path("data/processed/v2_4_pgir_reuse_decision.json").read_text(encoding="utf-8"))

    assert decision["decision_status"] == "second_domain_pgir_reuse_demonstrated_with_restrictions"
    assert decision["actual_structure_entity_count"] == 838
    assert decision["conformant_structure_entity_count"] == 838
    assert decision["architecture_reuse"] is True
    assert decision["representation_contract_reuse"] is True
    assert decision["conformance_engine_reuse"] is True
    assert decision["operator_framework_reuse"] is True
    assert decision["physical_operator_reuse"] is False
    assert decision["independent_validation"] is False
    assert decision["production_validation"] is False
    assert decision["representative_model"] == "none"
    assert decision["graph_artifact_status"] == "representation_only"


def test_materials_conformance_aggregate_has_no_row_level_identifiers():
    path = Path("data/processed/v2_4_materials_pgir_conformance_summary.csv")
    text = path.read_text(encoding="utf-8")
    rows = list(csv.DictReader(text.splitlines()))

    assert len(rows) == 6
    assert sum(int(row["record_count"]) for row in rows if row["representation"] == "crystal_structure_entity") == 838
    assert "material_id" not in rows[0]
    assert "mp-" not in text


def test_cross_domain_reuse_preserves_distinct_semantics_and_nonclaims():
    payload = json.loads(Path("data/processed/v2_4_cross_domain_reuse_evidence.json").read_text(encoding="utf-8"))

    assert payload["domains"] == ["battery", "materials"]
    assert "cycle Observation and operational State" in payload["domain_specific_semantics"]["battery"]
    assert "computed relaxed CrystalStructureEntity" in payload["domain_specific_semantics"]["materials"]
    assert payload["physical_operator_reuse"] is False
    assert payload["model_or_solver_executed"] is False
    assert payload["descriptor_or_graph_regenerated"] is False


def test_preview_is_side_effect_free_and_clean_snapshot_safe(tmp_path):
    before = list(tmp_path.rglob("*"))
    payload = preview_materials_pgir_reuse(tmp_path)
    after = list(tmp_path.rglob("*"))

    assert payload["status"] == "blocked_missing_local_materials_artifacts"
    assert payload["network_called"] is False
    assert payload["model_executed"] is False
    assert before == after == []


def test_read_only_audit_reports_blocked_without_local_entities(tmp_path):
    for relative in (
        "data/processed/materials_project_v2_2_4_structure_enrichment_summary.json",
        "data/processed/materials_project_v2_2_4_structure_coverage_summary.csv",
        "data/processed/materials_project_v2_2_4_snapshot_alignment_summary.csv",
        "data/processed/materials_project_v2_2_4_descriptor_coverage_summary.csv",
        "data/processed/materials_project_v2_2_4_graph_eligibility_summary.csv",
        "data/processed/materials_project_v2_2_4_operator_snapshot.json",
        "data/processed/materials_physics_v2_2_predictive_value_decision.json",
        "data/processed/materials_v2_2_5_predictive_value_decision.json",
        "data/processed/materials_physics_v2_2_feature_use_evidence.json",
        "data/processed/materials_physics_v2_2_predictive_comparison_summary.csv",
        "data/processed/battery_v2_3_5_source_lineage_summary.json",
        "data/processed/battery_v2_3_5_external_data_requirement_decision.json",
        "data/processed/battery_v2_3_5_evaluator_stability_summary.csv",
    ):
        source = Path(relative)
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())

    result = run_materials_pgir_reuse_audit(tmp_path, write_local=False, write_tracked=False)
    assert result.tracked_payloads["pgir_reuse_decision"]["decision_status"] == "blocked_missing_local_materials_artifacts"
    assert not (tmp_path / "outputs").exists()


def test_report_loader_reads_compact_decision_only():
    payload = load_second_domain_pgir_reuse_summary()
    assert payload["status"] == "available"
    assert payload["actual_structure_entity_count"] == 838
    assert payload["physical_operator_reuse"] is False
    assert payload["model_or_solver_executed"] is False
