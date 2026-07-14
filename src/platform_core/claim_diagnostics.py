"""Machine-readable claim diagnostics for platform policies."""

from __future__ import annotations

from .diagnostics import ClaimEvaluation


CLAIM_ALIASES = {
    "retrospective_diagnostic": "retrospective offline diagnostic ranking",
    "group_generalization": "bounded group-aware validation",
    "temporal_generalization": "retrospective time-aware diagnostic screening",
    "asset_generalization": "asset/time validation demonstration",
    "calibrated_probability": "calibrated failure probability",
    "production_deployment": "production maintenance automation",
    "root_cause": "causal root cause",
    "maintenance_automation": "production maintenance automation",
    "external_population_generalization": "external population generalization",
    "representative_model_selected": "representative model selected",
    "rul_prediction": "RUL prediction",
    "survival_probability": "survival probability",
}


def evaluate_claim_id(
    claim_id: str,
    *,
    allowed_claims: tuple[str, ...],
    prohibited_claims: tuple[str, ...],
    available_evidence: tuple[str, ...],
) -> ClaimEvaluation:
    claim_text = CLAIM_ALIASES.get(claim_id, claim_id).lower()
    allowed = {claim.lower() for claim in allowed_claims}
    prohibited = {claim.lower() for claim in prohibited_claims}
    evidence = set(available_evidence)
    if claim_text in prohibited or any(claim_text in item or item in claim_text for item in prohibited):
        return ClaimEvaluation(
            claim_id,
            "prohibited",
            conflicting_evidence=("trust_policy.prohibited_claims",),
            reason_code="claim_prohibited_by_policy",
        )
    if claim_id in {"calibrated_probability"} and "independent_calibration" not in evidence:
        return ClaimEvaluation(
            claim_id,
            "unsupported",
            conflicting_evidence=("missing:independent_calibration",),
            reason_code="missing_calibration_evidence",
        )
    if claim_id == "external_population_generalization" and "external_holdout" not in evidence:
        return ClaimEvaluation(
            claim_id,
            "unsupported",
            conflicting_evidence=("missing:external_holdout",),
            reason_code="missing_external_holdout",
        )
    if claim_id == "representative_model_selected" and "representative_model_selected" not in evidence:
        return ClaimEvaluation(
            claim_id,
            "unsupported",
            conflicting_evidence=("missing:representative_model_selected",),
            reason_code="representative_model_not_selected",
        )
    if claim_text in allowed or any(claim_text in item or item in claim_text for item in allowed):
        return ClaimEvaluation(
            claim_id,
            "supported",
            supporting_evidence=("trust_policy.allowed_claims",),
            reason_code="claim_allowed_by_policy",
        )
    return ClaimEvaluation(
        claim_id,
        "unsupported",
        conflicting_evidence=("missing:allowed_claim",),
        reason_code="claim_not_declared_allowed",
    )
