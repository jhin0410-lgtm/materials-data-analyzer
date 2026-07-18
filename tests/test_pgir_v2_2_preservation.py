import json
from pathlib import Path

from src.platform_core.pgir_governance import evaluate_pgir_readiness


def test_v2_2_predictive_value_decision_remains_negative_and_bounded():
    decision = json.loads(
        Path("data/processed/materials_physics_v2_2_predictive_value_decision.json").read_text(
            encoding="utf-8"
        )
    )

    assert decision["predictive_value_status"] == "performance_degraded"
    assert decision["representative_model_selected"] is False
    assert decision["claim_boundary"]["physics_constrained_model"] is False
    assert decision["claim_boundary"]["hybrid_physics_ml"] is False
    assert "SHAP or feature importance explanation" in decision["prohibited_claims"]


def test_v2_3_1_pgir_governance_readiness_is_preserved():
    readiness = evaluate_pgir_readiness().to_dict()

    assert readiness["valid"] is True
    assert readiness["status"] == "pgir_governance_ready"
    assert readiness["errors"] == []
    assert readiness["gates"]["current_mapping_complete"] is True
    assert readiness["gates"]["schema_owners_unique"] is True
