from src.platform_core.v2_2_trust_closeout import build_claim_matrix


def test_v2_2_claim_matrix_separates_supported_limited_and_prohibited_claims():
    matrix = build_claim_matrix()
    claims = {claim["claim_id"]: claim for claim in matrix["claims"]}

    assert claims["structure_predictive_value_supported"]["status"] == "limited_only"
    assert claims["composition_physics_predictive_value_supported"]["status"] == "unsupported"
    assert claims["representative_materials_model"]["status"] == "unsupported"
    assert claims["graph_model_used"]["status"] == "prohibited"
    assert claims["gnn_model_validated"]["status"] == "prohibited"
    assert claims["DFT_replacement"]["status"] == "prohibited"
    assert claims["production_scientific_decision"]["status"] == "prohibited"


def test_v2_2_claim_matrix_is_deterministic():
    assert build_claim_matrix() == build_claim_matrix()
