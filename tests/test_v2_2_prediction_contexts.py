from src.platform_core.v2_2_trust_closeout import build_prediction_context_registry


def test_v2_2_prediction_contexts_are_separate_and_bounded():
    registry = build_prediction_context_registry()
    contexts = {context["context_id"]: context for context in registry["contexts"]}

    pre_structure = contexts["composition_only_pre_structure"]
    known_structure = contexts["known_structure_post_relaxation"]
    assert "relaxed_crystal_structure" in pre_structure["prohibited_inputs"]
    assert pre_structure["current_decision"] == "performance_degraded"
    assert pre_structure["representative_model_selected"] is False
    assert "validated_CrystalStructureEntity" in known_structure["allowed_inputs"]
    assert known_structure["current_decision"] == "structure_predictive_value_limited"
    assert known_structure["representative_model_selected"] is False
    assert registry["cross_context_policy"]["merge_results_into_single_model_claim"] is False
    assert registry["cross_context_policy"]["use_known_structure_result_as_pre_structure_screening_claim"] is False
