from src.platform_core.v2_2_trust_closeout import build_capability_matrix


def test_v2_2_capability_matrix_preserves_evidence_levels():
    matrix = build_capability_matrix()
    records = {record["capability_id"]: record for record in matrix["capabilities"]}

    assert matrix["status"] == "release_ready"
    assert records["composition_feature_builders"]["status"] == "predictive_value_not_supported"
    assert "model_input_used" in records["composition_feature_builders"]["evidence_levels"]
    assert records["structure_descriptors"]["status"] == "predictive_value_limited"
    assert records["structure_descriptors"]["uncertainty_evaluated"] is True
    assert records["periodic_graph_artifacts"]["status"] == "artifact_generated"
    assert records["periodic_graph_artifacts"]["model_input_used"] is False
    assert records["representative_model"]["status"] == "unavailable"
    assert records["DFT_replacement"]["status"] == "prohibited"


def test_v2_2_capability_matrix_is_deterministic():
    assert build_capability_matrix() == build_capability_matrix()


def test_v2_2_capability_matrix_records_use_list_fields():
    matrix = build_capability_matrix()

    for record in matrix["capabilities"]:
        assert isinstance(record["evidence_levels"], tuple)
        assert isinstance(record["supporting_artifacts"], tuple)
        assert isinstance(record["limitations"], tuple)
        assert isinstance(record["prohibited_interpretations"], tuple)
