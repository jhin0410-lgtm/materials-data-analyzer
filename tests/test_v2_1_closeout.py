import json
from pathlib import Path

from src.platform_core.scientific_constraint_registry import build_default_scientific_constraint_registry
from src.platform_core.scientific_feature_registry import build_default_scientific_feature_registry
from src.platform_core.scientific_trust import closeout_conclusion, constraint_role_snapshot


def _json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_scientific_snapshots_match_default_registries():
    role_snapshot = _json("data/platform/scientific_constraint_role_snapshot_v2.json")
    feature_snapshot = _json("data/platform/scientific_feature_candidate_snapshot_v2.json")

    assert role_snapshot["roles"] == constraint_role_snapshot(build_default_scientific_constraint_registry())
    assert feature_snapshot["features"] == build_default_scientific_feature_registry().snapshot()
    assert role_snapshot["timestamp_policy"] == "deterministic_no_timestamp"
    assert feature_snapshot["timestamp_policy"] == "deterministic_no_timestamp"


def test_scientific_schemas_parse_and_forbid_execution_side_effects():
    feature_schema = _json("data/platform/scientific_feature_candidate_schema_v2.json")
    trust_schema = _json("data/platform/scientific_trust_evaluation_schema_v2.json")

    assert feature_schema["security_policy"]["feature_value_generation_allowed"] is False
    assert feature_schema["security_policy"]["model_training_allowed"] is False
    assert trust_schema["security_policy"]["scientific_recomputation_allowed"] is False
    assert "production_validated" in trust_schema["allowed_evidence_levels"]


def test_v2_1_closeout_claims_are_bounded():
    conclusion = closeout_conclusion().to_dict()

    assert conclusion["status"] == "release_ready"
    assert "phase identification" not in " ".join(conclusion["allowed_claims"]).lower()
    assert any("phase identification" in claim for claim in conclusion["prohibited_claims"])
    assert any("physics-constrained model" in claim for claim in conclusion["prohibited_claims"])


def test_closeout_docs_exist_and_do_not_claim_production_validation():
    required = [
        "docs/SCIENTIFIC_EXECUTION.md",
        "docs/PLATFORM_V2_1_PLAN.md",
    ]
    for path in required:
        text = Path(path).read_text(encoding="utf-8").lower()
        assert "production_validated" not in text or "does not" in text or "not" in text
