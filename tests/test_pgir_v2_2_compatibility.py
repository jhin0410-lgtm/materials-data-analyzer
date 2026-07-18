from src.platform_core.v2_2_trust_closeout import validate_result_preservation
from src.platform_core.pgir_governance import build_capability_stage_registry


def test_pgir_governance_preserves_v2_2_decisions():
    preservation = validate_result_preservation()
    capabilities = {record.capability_id: record for record in build_capability_stage_registry()}

    assert preservation["valid"] is True
    assert preservation["checks"]["v2_2_1_performance_degraded"] is True
    assert preservation["checks"]["v2_2_5_structure_limited"] is True
    assert capabilities["composition_feature_candidates"].evidence_level == "v2_2_1_performance_degraded"
    assert capabilities["structure_descriptor_candidates"].evidence_level == "v2_2_5_structure_predictive_value_limited"
    assert capabilities["graph_entity_artifact"].scientific_claim_supported == "representation_only"
