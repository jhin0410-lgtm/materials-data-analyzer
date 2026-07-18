import json
from pathlib import Path


def test_platform_schema_json_files_parse():
    for path in [
        Path("data/platform/pipeline_config_schema_v2.json"),
        Path("data/platform/run_manifest_schema_v2.json"),
        Path("data/platform/case_study_onboarding_schema_v2.json"),
        Path("data/platform/platform_report_schema_v2.json"),
        Path("data/platform/report_manifest_schema_v2.json"),
        Path("data/platform/scientific_constraint_schema_v2.json"),
        Path("data/platform/domain_knowledge_pack_schema_v2.json"),
        Path("data/platform/scientific_execution_request_schema_v2.json"),
        Path("data/platform/scientific_execution_result_schema_v2.json"),
        Path("data/platform/scientific_feature_candidate_schema_v2.json"),
        Path("data/platform/scientific_trust_evaluation_schema_v2.json"),
        Path("data/platform/scientific_entity_schema_v2.json"),
        Path("data/platform/scientific_quantity_schema_v2.json"),
        Path("data/platform/scientific_uncertainty_schema_v2.json"),
        Path("data/platform/scientific_relation_schema_v2.json"),
        Path("data/platform/graph_entity_schema_v2.json"),
        Path("data/platform/trajectory_entity_schema_v2.json"),
        Path("data/platform/materials_project_query_plan_schema_v2.json"),
        Path("data/platform/materials_project_acquisition_manifest_schema_v2.json"),
        Path("data/platform/materials_project_structure_summary_schema_v2.json"),
        Path("data/platform/scientific_operator_registry_schema_v2.json"),
        Path("data/platform/materials_structure_descriptor_schema_v2.json"),
        Path("data/platform/crystal_graph_artifact_schema_v2.json"),
        Path("data/platform/materials_snapshot_alignment_schema_v2.json"),
        Path("data/platform/materials_structure_readiness_schema_v2.json"),
        Path("data/platform/materials_known_structure_prediction_schema_v2.json"),
        Path("data/platform/materials_structure_predictive_decision_schema_v2.json"),
        Path("data/platform/materials_prediction_interval_schema_v2.json"),
        Path("data/platform/pgir_concept_registry_v1.json"),
        Path("data/platform/pgir_current_mapping_matrix_v1.json"),
        Path("data/platform/pgir_representation_governance_v1.json"),
        Path("data/platform/pgir_schema_ownership_registry_v1.json"),
        Path("data/platform/pgir_capability_stage_registry_v1.json"),
        Path("data/platform/pgir_representation_declaration_schema_v1.json"),
        Path("data/platform/pgir_conformance_result_schema_v1.json"),
        Path("data/platform/battery_cycle_observation_schema_v1.json"),
        Path("data/platform/battery_operational_state_schema_v1.json"),
        Path("data/platform/battery_trajectory_summary_schema_v1.json"),
        Path("data/platform/battery_mechanism_readiness_schema_v1.json"),
        Path("data/platform/mechanism_candidate_schema_v1.json"),
        Path("data/platform/mechanism_requirement_schema_v1.json"),
        Path("data/platform/mechanism_evidence_binding_schema_v1.json"),
        Path("data/platform/mechanism_identifiability_schema_v1.json"),
        Path("data/platform/mechanism_selection_decision_schema_v1.json"),
        Path("data/platform/mechanism_evidence_gap_schema_v1.json"),
        Path("data/platform/battery_mechanism_candidate_registry_v1.json"),
        Path("data/platform/battery_mechanism_evidence_gap_registry_v1.json"),
    ]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema_version"] in {"2.0", "2.1", "2.1.5", "2.2.2", "2.2.3", "2.2.4", "2.2.5", "2.3.1", "2.3.2", "2.3.3"}
        assert payload["status"] in {"scaffold_stage", "release_ready", "accepted_for_v2_3"}
    registry_schema = json.loads(Path("data/platform/platform_registry_schema_v2.json").read_text(encoding="utf-8"))
    assert registry_schema["schema_version"] == "2.1"
    assert registry_schema["status"] == "release_ready"
    report_schema = json.loads(Path("data/platform/platform_report_schema_v2.json").read_text(encoding="utf-8"))
    assert "scientific_trust_summary" in report_schema["required_fields"]
    assert "pgir_governance_summary" in report_schema["required_fields"]
    assert "pgir_conformance_summary" in report_schema["required_fields"]
    assert "battery_pgir_summary" in report_schema["required_fields"]
    assert "battery_mechanism_audit_summary" in report_schema["required_fields"]


def test_example_configs_have_no_credentials_or_absolute_paths():
    for path in Path("configs/examples").glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert ("C:" + "/") not in text
        assert ("C:" + "\\") not in text
        assert ("pass" + "word=") not in text.lower()
        assert ("sec" + "ret=") not in text.lower()
        assert ("tok" + "en=") not in text.lower()
        payload = json.loads(text)
        assert payload["credential_policy"]["store_credentials"] is False
        if "artifact_definitions" in payload:
            assert payload["schema_version"] == "2.0"
            assert payload.get("execution_candidate") is not True
        elif payload.get("report_id"):
            assert payload["schema_version"] == "2.0"
            assert payload["output_dir"].startswith("outputs/platform_reports/")
            assert payload["credential_policy"]["store_credentials"] is False
        elif payload.get("execution_mode"):
            assert payload["execution_mode"] in {"verify", "isolated_run"}
        elif payload.get("constraint_ids") and payload.get("inputs"):
            assert payload["schema_version"] == "2.1"
            assert payload["output_policy"]["write_outputs"] is False
        elif payload.get("case_study_id") == "materials_project" and payload["schema_version"] == "2.2.1":
            assert payload["stage"] in {"feature_build", "validation"}
            assert payload["credential_policy"]["network_access_required"] is False
        elif payload.get("schema_version") == "2.2.2" or payload.get("operator_id", "").endswith("_v2_2"):
            assert payload["credential_policy"]["network_access_required"] is False
            assert payload["dry_run"] is True
        elif payload.get("schema_version") == "2.2.3":
            assert payload["credential_policy"]["store_credentials"] is False
            assert payload["dry_run"] is True
        elif payload.get("schema_version") == "2.2.4":
            assert payload["credential_policy"]["store_credentials"] is False
            assert payload["dry_run"] is True
        elif payload.get("schema_version") == "2.2.5":
            assert payload["credential_policy"]["store_credentials"] is False
            assert payload["credential_policy"]["network_access_required"] is False
        elif payload.get("schema_version") == "2.3.2":
            assert payload["credential_policy"]["store_credentials"] is False
            assert payload["credential_policy"]["network_access_required"] is False
            assert payload["dry_run"] is True
        elif payload.get("schema_version") == "2.3.3":
            assert payload["credential_policy"]["store_credentials"] is False
            assert payload["credential_policy"]["network_access_required"] is False
            assert payload["dry_run"] is True
            assert payload["execution_policy"]["fitting_enabled"] is False
            assert payload["execution_policy"]["solver_enabled"] is False
        else:
            assert payload["dry_run"] is True


def test_platform_docs_are_scaffold_stage_not_completed_pipeline():
    text = Path("docs/PLATFORM_V2_PLAN.md").read_text(encoding="utf-8")

    assert "Status: `development_stage`" in text
    assert "does not execute actual acquisition" in text
    assert "Actual `run` execution is intentionally deferred" in text
