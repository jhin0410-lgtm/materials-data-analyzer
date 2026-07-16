import json
import shutil
from pathlib import Path

from src.platform_core.materials_project_acquisition import audit_current_materials_scope


def test_scope_audit_reconstructs_838_row_fe_si_containing_subset():
    summary = audit_current_materials_scope(".")

    assert summary["lineage_verdict"] == "exact_query_reconstructed"
    assert summary["row_count"] == 838
    assert summary["analysis_ready_row_count"] == 838
    assert summary["unique_material_id_count"] == 838
    assert summary["missing_material_id_count"] == 0
    assert summary["duplicated_material_id_count"] == 0
    assert summary["fe_si_binary_only"] is False
    assert summary["scope_distribution"] == {"binary": 13, "ternary": 299, "quaternary_plus": 526}
    assert summary["element_frequency"]["Fe"] == 838
    assert summary["element_frequency"]["Si"] == 838
    assert summary["unique_element_count"] == 67
    assert summary["target"]["column"] == "energy_above_hull"
    assert summary["target"]["unit"] == "eV/atom"
    assert summary["actual_structure_enrichment_status"] == "unavailable_no_local_api_data"
    serialized = json.dumps(summary).lower()
    assert "redacted-secret-sentinel" not in serialized
    assert "token" not in serialized


def test_scope_audit_preserves_v2_2_1_negative_result():
    summary = audit_current_materials_scope(".")
    decision = summary["predictive_value_preservation"]

    assert decision["predictive_value_status"] == "performance_degraded"
    assert decision["representative_model_selected"] is False
    assert decision["claim_boundary"]["physics_constrained_model"] is False
    assert decision["claim_boundary"]["hybrid_physics_ml"] is False


def test_scope_audit_uses_tracked_compact_summary_without_local_full_tables(tmp_path):
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    shutil.copyfile(
        Path("data/processed/materials_project_v2_2_acquisition_scope_summary.json"),
        processed / "materials_project_v2_2_acquisition_scope_summary.json",
    )

    summary = audit_current_materials_scope(tmp_path)

    assert summary["row_count"] == 838
    assert summary["actual_structure_enrichment_status"] == "unavailable_no_local_api_data"
