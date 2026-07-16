from src.platform_core.v2_2_trust_closeout import validate_result_preservation


def test_v2_2_result_preservation_keeps_prior_decisions():
    preservation = validate_result_preservation()

    assert preservation["valid"] is True
    checks = preservation["checks"]
    assert checks["v2_2_1_performance_degraded"] is True
    assert checks["v2_2_4_structure_ready_with_restrictions"] is True
    assert checks["v2_2_4_original_target_not_overwritten"] is True
    assert checks["v2_2_5_structure_limited"] is True
    assert checks["v2_2_5_original_target_source"] is True
    assert checks["v2_2_5_no_graph_model"] is True
    assert preservation["canonical_checksums"]["materials_physics_v2_2_predictive_value_decision"] == (
        "277cd5e254b962338a78c68600500da873538e6783e92aebad8aa34374e889f0"
    )
