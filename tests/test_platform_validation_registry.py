import pytest

from src.platform_core.validation_registry import (
    ValidationPolicyMetadata,
    ValidationPolicyRegistry,
    build_default_validation_policy_registry,
)


def test_validation_policy_lookup_and_snapshot():
    registry = build_default_validation_policy_registry()

    policy = registry.get("asset_time_combined_classification")
    snapshot = registry.snapshot()

    assert policy.group_key == "asset_id"
    assert policy.time_key == "observation_timestamp"
    assert [item["policy_id"] for item in snapshot] == sorted(item["policy_id"] for item in snapshot)


def test_validation_policy_unknown_and_duplicate_rejected():
    registry = ValidationPolicyRegistry()
    policy = ValidationPolicyMetadata(
        policy_id="demo_policy",
        validation_type="demo",
        group_key=None,
        time_key=None,
        primary_evidence=("demo",),
        optimistic_reference=None,
        overlap_rules=("no_overlap",),
        preprocessing_scope="train_only",
        threshold_policy="fixed",
        metric_family=("metric",),
        claim_scope="demo",
    )
    registry.register(policy)

    with pytest.raises(ValueError, match="duplicate validation policy_id"):
        registry.register(policy)

    with pytest.raises(KeyError, match="unknown validation policy_id"):
        registry.get("missing")


def test_validation_policy_requires_train_only_preprocessing():
    with pytest.raises(ValueError, match="train_only"):
        ValidationPolicyMetadata(
            policy_id="bad",
            validation_type="demo",
            group_key=None,
            time_key=None,
            primary_evidence=("demo",),
            optimistic_reference=None,
            overlap_rules=("no_overlap",),
            preprocessing_scope="full_dataset",
            threshold_policy="fixed",
            metric_family=("metric",),
            claim_scope="demo",
        )
