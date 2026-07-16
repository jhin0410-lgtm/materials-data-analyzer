import hashlib
import json


def test_materials_v2_2_1_decision_checksum_and_conclusion_unchanged():
    path = "data/processed/materials_physics_v2_2_predictive_value_decision.json"
    payload = json.loads(open(path, encoding="utf-8").read())
    canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    digest = hashlib.sha256(canonical_payload).hexdigest()

    assert digest == "277cd5e254b962338a78c68600500da873538e6783e92aebad8aa34374e889f0"
    assert payload["predictive_value_status"] == "performance_degraded"
    assert payload["representative_model_selected"] is False
    assert payload["claim_boundary"]["physics_constrained_model"] is False
    assert payload["claim_boundary"]["hybrid_physics_ml"] is False
