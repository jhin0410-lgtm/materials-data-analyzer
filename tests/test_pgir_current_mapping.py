import json
from pathlib import Path

from src.platform_core.pgir_governance import (
    build_capability_stage_registry,
    build_current_mapping_matrix,
    validate_capability_stages,
    validate_mapping_matrix,
)


def test_current_mapping_references_existing_supported_implementation_records():
    validation = validate_mapping_matrix()
    records = build_current_mapping_matrix()

    assert validation["valid"] is True
    assert validation["mapping_count"] == len(records)
    refs = {record.implementation_ref for record in records}
    assert "src.platform_core.scientific_entities.ScientificEntity" in refs
    assert "src.platform_core.scientific_entities.GraphEntity" in refs
    assert "src.platform_core.scientific_operator_registry.ScientificOperatorMetadata" in refs


def test_mapping_preserves_graph_representation_only_and_runtime_persistence_boundary():
    records = {record.implementation_ref: record for record in build_current_mapping_matrix()}

    graph = records["src.platform_core.scientific_entities.GraphEntity"]
    assert graph.mapping_status == "partial"
    assert "not GNN evidence" in graph.current_limitations
    assert "graph neural network claim" in graph.prohibited_promotions
    assert "artifact-backed" in graph.persisted_representation

    entity_record = records["src.platform_core.scientific_entities.EntityRecord"]
    assert "runtime object persistence" in entity_record.prohibited_promotions


def test_capability_stage_registry_limits_propagator_to_bounded_execution():
    validation = validate_capability_stages()
    capabilities = {record.capability_id: record for record in build_capability_stage_registry()}

    assert validation["valid"] is True
    assert capabilities["propagator_operator_role"].capability_stage == "operator_executed"
    assert capabilities["propagator_operator_role"].future_only is False
    assert capabilities["propagator_operator_role"].model_execution_performed is True
    assert capabilities["propagator_operator_role"].scientific_claim_supported == "bounded_synthetic_scalar_diffusion_evidence_only"
    assert capabilities["graph_entity_artifact"].scientific_claim_supported == "representation_only"
    assert capabilities["composition_feature_candidates"].evidence_level == "v2_2_1_performance_degraded"
    assert capabilities["structure_descriptor_candidates"].evidence_level == "v2_2_5_structure_predictive_value_limited"
    assert capabilities["battery_capacity_trajectory_evaluator"].capability_stage == "scientifically_evaluated"
    assert capabilities["battery_capacity_trajectory_evaluator"].model_execution_performed is False
    assert capabilities["battery_mechanism_identifiability_audit"].capability_stage == "adapter_available"


def test_mapping_and_capability_compact_artifacts_parse_and_match_code():
    mapping_payload = json.loads(Path("data/platform/pgir_current_mapping_matrix_v1.json").read_text(encoding="utf-8"))
    capability_payload = json.loads(Path("data/platform/pgir_capability_stage_registry_v1.json").read_text(encoding="utf-8"))

    assert mapping_payload["validation"]["valid"] is True
    assert capability_payload["validation"]["valid"] is True
    assert len(mapping_payload["mappings"]) == len(build_current_mapping_matrix())
    assert len(capability_payload["capabilities"]) == len(build_capability_stage_registry())
