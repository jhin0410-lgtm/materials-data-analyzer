"""Validation policy metadata registry."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ValidationPolicyMetadata:
    policy_id: str
    validation_type: str
    group_key: str | None
    time_key: str | None
    primary_evidence: tuple[str, ...]
    optimistic_reference: str | None
    overlap_rules: tuple[str, ...]
    preprocessing_scope: str
    threshold_policy: str
    metric_family: tuple[str, ...]
    claim_scope: str
    implementation_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.policy_id:
            raise ValueError("policy_id is required")
        if self.preprocessing_scope != "train_only":
            raise ValueError("v2 validation policies must use train_only preprocessing")

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "validation_type": self.validation_type,
            "group_key": self.group_key,
            "time_key": self.time_key,
            "primary_evidence": list(self.primary_evidence),
            "optimistic_reference": self.optimistic_reference,
            "overlap_rules": list(self.overlap_rules),
            "preprocessing_scope": self.preprocessing_scope,
            "threshold_policy": self.threshold_policy,
            "metric_family": list(self.metric_family),
            "claim_scope": self.claim_scope,
            "implementation_reference": self.implementation_reference,
        }


@dataclass
class ValidationPolicyRegistry:
    _policies: dict[str, ValidationPolicyMetadata] = field(default_factory=dict)

    def register(self, policy: ValidationPolicyMetadata) -> None:
        if policy.policy_id in self._policies:
            raise ValueError(f"duplicate validation policy_id: {policy.policy_id}")
        self._policies[policy.policy_id] = policy

    def get(self, policy_id: str) -> ValidationPolicyMetadata:
        try:
            return self._policies[policy_id]
        except KeyError as exc:
            raise KeyError(f"unknown validation policy_id: {policy_id}") from exc

    def list_policies(self) -> list[ValidationPolicyMetadata]:
        return [self._policies[key] for key in sorted(self._policies)]

    def snapshot(self) -> list[dict[str, object]]:
        return [policy.to_dict() for policy in self.list_policies()]


def build_default_validation_policy_registry() -> ValidationPolicyRegistry:
    registry = ValidationPolicyRegistry()
    registry.register(
        ValidationPolicyMetadata(
            policy_id="random_reference_only",
            validation_type="random_split_reference",
            group_key=None,
            time_key=None,
            primary_evidence=(),
            optimistic_reference="random_row_split",
            overlap_rules=("not_primary_evidence",),
            preprocessing_scope="train_only",
            threshold_policy="fixed_or_train_validation_only",
            metric_family=("regression", "classification"),
            claim_scope="optimistic_reference_only",
        )
    )
    registry.register(
        ValidationPolicyMetadata(
            policy_id="group_aware_regression",
            validation_type="group_disjoint_regression",
            group_key="case_study_defined_group",
            time_key=None,
            primary_evidence=("group_disjoint_split", "group_kfold_when_feasible"),
            optimistic_reference="random_split",
            overlap_rules=("train_test_group_overlap_zero",),
            preprocessing_scope="train_only",
            threshold_policy="not_applicable",
            metric_family=("r2", "mae", "rmse"),
            claim_scope="unseen_group_generalization_when_supported",
            implementation_reference="src/analyzers/grouped_regression_validation.py",
        )
    )
    registry.register(
        ValidationPolicyMetadata(
            policy_id="time_aware_classification",
            validation_type="chronological_classification",
            group_key=None,
            time_key="observation_timestamp",
            primary_evidence=("chronological_holdout", "future_period_validation"),
            optimistic_reference="stratified_random_split",
            overlap_rules=("train_time_before_test_time", "no_sample_overlap"),
            preprocessing_scope="train_only",
            threshold_policy="fixed_0_5_and_train_validation_only",
            metric_family=("average_precision", "roc_auc", "mcc", "brier"),
            claim_scope="future_period_diagnostic_screening",
            implementation_reference="src/analyzers/temporal_classification_validation.py",
        )
    )
    registry.register(
        ValidationPolicyMetadata(
            policy_id="asset_time_combined_classification",
            validation_type="asset_disjoint_time_aware_classification",
            group_key="asset_id",
            time_key="observation_timestamp",
            primary_evidence=("asset_disjoint", "time_aware", "combined_asset_time"),
            optimistic_reference="stratified_random_row_split",
            overlap_rules=("train_test_asset_overlap_zero", "future_test_period", "no_sample_overlap"),
            preprocessing_scope="train_only",
            threshold_policy="fixed_0_5_and_train_validation_only",
            metric_family=("average_precision", "roc_auc", "top_risk_lift", "mcc", "brier"),
            claim_scope="retrospective_asset_time_diagnostic_ranking",
            implementation_reference="src/analyzers/asset_temporal_classification.py",
        )
    )
    return registry
