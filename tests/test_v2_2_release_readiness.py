from src.platform_core.v2_2_trust_closeout import build_closeout_decision, evaluate_release_readiness


def test_v2_2_release_readiness_is_release_ready_without_promoting_model():
    readiness = evaluate_release_readiness()
    decision = build_closeout_decision()

    assert readiness["release_readiness"] == "release_ready"
    assert decision["release_readiness"] == "release_ready"
    assert decision["composition_decision"] == "performance_degraded"
    assert decision["known_structure_decision"] == "structure_predictive_value_limited"
    assert decision["representative_model_selected"] is False
    assert decision["graph_model_used"] is False
    assert decision["gnn_model_validated"] is False
    assert decision["no_new_scientific_result"] is True
    assert all(decision["release_gates"].values())
