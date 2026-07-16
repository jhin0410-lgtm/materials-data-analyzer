import hashlib
import json


def test_materials_v2_2_1_decision_checksum_and_conclusion_unchanged():
    path = "data/processed/materials_physics_v2_2_predictive_value_decision.json"
    payload = json.loads(open(path, encoding="utf-8").read())
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()

    assert digest == "13b10d743e650efc4ce26b49938fd25e2bc46b47bf26efca7def5ea014ec3827"
    assert payload["predictive_value_status"] == "performance_degraded"
    assert payload["representative_model_selected"] is False
    assert payload["claim_boundary"]["physics_constrained_model"] is False
    assert payload["claim_boundary"]["hybrid_physics_ml"] is False
