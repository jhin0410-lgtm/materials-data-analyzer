import pytest

from src.platform_core.trust_registry import TrustPolicyMetadata, TrustPolicyRegistry, build_default_trust_policy_registry


def test_trust_policy_lookup_and_production_ready_absent():
    registry = build_default_trust_policy_registry()

    policy = registry.get("reliability_asset_time_aware")

    assert policy.production_claim_allowed is False
    assert "production_ready" not in policy.allowed_statuses
    assert all("production_ready" not in item["allowed_statuses"] for item in registry.snapshot())


def test_trust_policy_unknown_and_duplicate_rejected():
    registry = TrustPolicyRegistry()
    policy = TrustPolicyMetadata(
        policy_id="demo_trust",
        allowed_statuses=("diagnostic_only",),
        representative_model_rules=("rule",),
        calibration_boundary="none",
        explainability_boundary="none",
        production_claim_allowed=False,
        allowed_claims=("demo",),
        prohibited_claims=("production",),
        required_evidence=("evidence",),
        stop_conditions=("stop",),
    )
    registry.register(policy)

    with pytest.raises(ValueError, match="duplicate trust policy_id"):
        registry.register(policy)

    with pytest.raises(KeyError, match="unknown trust policy_id"):
        registry.get("missing")


def test_trust_policy_rejects_production_ready_or_production_claim():
    with pytest.raises(ValueError, match="production_ready"):
        TrustPolicyMetadata(
            policy_id="bad_status",
            allowed_statuses=("production_ready",),
            representative_model_rules=("rule",),
            calibration_boundary="none",
            explainability_boundary="none",
            production_claim_allowed=False,
            allowed_claims=("demo",),
            prohibited_claims=("production",),
            required_evidence=("evidence",),
            stop_conditions=("stop",),
        )

    with pytest.raises(ValueError, match="production_claim_allowed"):
        TrustPolicyMetadata(
            policy_id="bad_claim",
            allowed_statuses=("diagnostic_only",),
            representative_model_rules=("rule",),
            calibration_boundary="none",
            explainability_boundary="none",
            production_claim_allowed=True,
            allowed_claims=("demo",),
            prohibited_claims=("production",),
            required_evidence=("evidence",),
            stop_conditions=("stop",),
        )
