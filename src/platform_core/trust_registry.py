"""Trust policy metadata registry."""

from __future__ import annotations

from dataclasses import dataclass, field


ALLOWED_MODEL_STATUSES = (
    "descriptive_only",
    "diagnostic_only",
    "limited_predictive_evidence",
    "candidate_for_further_validation",
    "resource_limited",
    "not_run",
)


@dataclass(frozen=True)
class TrustPolicyMetadata:
    policy_id: str
    allowed_statuses: tuple[str, ...]
    representative_model_rules: tuple[str, ...]
    calibration_boundary: str
    explainability_boundary: str
    production_claim_allowed: bool
    allowed_claims: tuple[str, ...]
    prohibited_claims: tuple[str, ...]
    required_evidence: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    implementation_reference: str | None = None

    def __post_init__(self) -> None:
        if "production_ready" in self.allowed_statuses:
            raise ValueError("production_ready is not an allowed trust status")
        unsupported = sorted(set(self.allowed_statuses) - set(ALLOWED_MODEL_STATUSES))
        if unsupported:
            raise ValueError(f"unsupported trust statuses: {unsupported}")
        if self.production_claim_allowed:
            raise ValueError("production_claim_allowed must be false in default v2 policies")

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "allowed_statuses": list(self.allowed_statuses),
            "representative_model_rules": list(self.representative_model_rules),
            "calibration_boundary": self.calibration_boundary,
            "explainability_boundary": self.explainability_boundary,
            "production_claim_allowed": self.production_claim_allowed,
            "allowed_claims": list(self.allowed_claims),
            "prohibited_claims": list(self.prohibited_claims),
            "required_evidence": list(self.required_evidence),
            "stop_conditions": list(self.stop_conditions),
            "implementation_reference": self.implementation_reference,
        }


@dataclass
class TrustPolicyRegistry:
    _policies: dict[str, TrustPolicyMetadata] = field(default_factory=dict)

    def register(self, policy: TrustPolicyMetadata) -> None:
        if policy.policy_id in self._policies:
            raise ValueError(f"duplicate trust policy_id: {policy.policy_id}")
        self._policies[policy.policy_id] = policy

    def get(self, policy_id: str) -> TrustPolicyMetadata:
        try:
            return self._policies[policy_id]
        except KeyError as exc:
            raise KeyError(f"unknown trust policy_id: {policy_id}") from exc

    def list_policies(self) -> list[TrustPolicyMetadata]:
        return [self._policies[key] for key in sorted(self._policies)]

    def snapshot(self) -> list[dict[str, object]]:
        return [policy.to_dict() for policy in self.list_policies()]


def build_default_trust_policy_registry() -> TrustPolicyRegistry:
    statuses = ("descriptive_only", "diagnostic_only", "limited_predictive_evidence", "candidate_for_further_validation", "resource_limited", "not_run")
    registry = TrustPolicyRegistry()
    registry.register(
        TrustPolicyMetadata(
            policy_id="materials_group_generalization",
            allowed_statuses=statuses,
            representative_model_rules=(
                "group-aware performance must exceed descriptive baselines",
                "applicability-domain behavior must be stable",
                "no representative model when random split is the only strong evidence",
            ),
            calibration_boundary="no_calibrated_uncertainty_claim",
            explainability_boundary="feature importance is diagnostic only after validation gates pass",
            production_claim_allowed=False,
            allowed_claims=("descriptive screening", "bounded group-aware validation"),
            prohibited_claims=("novel material discovery", "DFT replacement", "production screening readiness"),
            required_evidence=("group_disjoint_validation", "applicability_domain_summary", "claim_boundary_summary"),
            stop_conditions=("source_provenance_missing", "group_validation_not_feasible", "unsupported_claim_detected"),
            implementation_reference="scripts/run_materials_project_v1_3_trust_analysis.py",
        )
    )
    registry.register(
        TrustPolicyMetadata(
            policy_id="smart_factory_time_aware",
            allowed_statuses=statuses,
            representative_model_rules=(
                "chronological validation must be primary",
                "random split cannot select a representative model",
                "calibration and threshold limitations must be documented",
            ),
            calibration_boundary="uncalibrated_risk_score_only",
            explainability_boundary="no root-cause claim from anonymized process features",
            production_claim_allowed=False,
            allowed_claims=("retrospective time-aware diagnostic screening",),
            prohibited_claims=("production alert", "causal root cause", "calibrated production probability"),
            required_evidence=("chronological_metrics", "random_temporal_gap", "trust_summary"),
            stop_conditions=("target_alignment_invalid", "time_order_invalid", "unsupported_claim_detected"),
            implementation_reference="src/analyzers/classification_trust.py",
        )
    )
    registry.register(
        TrustPolicyMetadata(
            policy_id="reliability_asset_time_aware",
            allowed_statuses=statuses,
            representative_model_rules=(
                "combined asset/time validation must be stable",
                "resource-limited models cannot alone become representative",
                "top-risk lift must be interpreted with absolute precision and burden",
                "survival/RUL claims require separate readiness evidence",
            ),
            calibration_boundary="uncalibrated_relative_ranking_score_only",
            explainability_boundary="SHAP deferred unless representative model exists",
            production_claim_allowed=False,
            allowed_claims=("retrospective offline diagnostic ranking", "asset/time validation demonstration"),
            prohibited_claims=("production maintenance automation", "calibrated failure probability", "RUL prediction", "survival probability"),
            required_evidence=("asset_disjoint_metrics", "time_aware_metrics", "combined_metrics", "trust_summary"),
            stop_conditions=("source_sha_mismatch", "asset_overlap_detected", "unsupported_claim_detected"),
            implementation_reference="src/analyzers/reliability_trust.py",
        )
    )
    return registry
