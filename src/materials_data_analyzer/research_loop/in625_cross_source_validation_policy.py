"""Scientific promotion policy for cross-source IN625 physical evidence.

The policy is deliberately conservative: heterogeneous machines, material states,
power semantics, or independent experiment families cannot be collapsed into a
naive pooled validation claim. Instead the caller receives an explicit
stratified and leave-one-experiment-family-out validation plan.
"""
from __future__ import annotations

from collections import Counter
from typing import Any


class CrossSourceValidationPolicyError(ValueError):
    """Raised when a requested scientific promotion violates source boundaries."""


def _nonblank(record: dict[str, Any], key: str, index: int) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CrossSourceValidationPolicyError(
            f"validated_records[{index}] requires non-blank {key}."
        )
    return value.strip()


def build_cross_source_validation_plan(
    validated_records: list[dict[str, Any]],
    intake_audit: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(validated_records, list) or not validated_records:
        raise CrossSourceValidationPolicyError(
            "validated_records must be a non-empty list."
        )
    if not isinstance(intake_audit, dict):
        raise CrossSourceValidationPolicyError("intake_audit must be an object.")

    normalized: list[dict[str, str]] = []
    for index, record in enumerate(validated_records):
        if not isinstance(record, dict):
            raise CrossSourceValidationPolicyError(
                f"validated_records[{index}] must be an object."
            )
        normalized.append(
            {
                "experiment_family_id": _nonblank(
                    record, "experiment_family_id", index
                ),
                "machine_id": _nonblank(record, "machine_id", index),
                "material_state": _nonblank(record, "material_state", index),
                "power_semantics": _nonblank(record, "power_semantics", index),
                "evidence_stratum": _nonblank(record, "evidence_stratum", index),
            }
        )

    families = sorted({record["experiment_family_id"] for record in normalized})
    machines = sorted({record["machine_id"] for record in normalized})
    states = sorted({record["material_state"] for record in normalized})
    power_semantics = sorted({record["power_semantics"] for record in normalized})
    strata = sorted({record["evidence_stratum"] for record in normalized})
    audit_authorizes_naive = intake_audit.get("naive_cross_source_pooling_allowed")
    if not isinstance(audit_authorizes_naive, bool):
        raise CrossSourceValidationPolicyError(
            "intake_audit.naive_cross_source_pooling_allowed must be boolean."
        )

    independently_homogeneous = (
        len(families) == 1
        and len(machines) == 1
        and len(states) == 1
        and len(power_semantics) == 1
        and not intake_audit.get("duplicate_physical_response_views")
    )
    naive_authorized = audit_authorizes_naive and independently_homogeneous

    family_counts = Counter(
        record["experiment_family_id"] for record in normalized
    )
    leave_one_family_out = [
        {
            "holdout_experiment_family_id": family,
            "training_experiment_family_ids": [
                other for other in families if other != family
            ],
            "holdout_record_count": family_counts[family],
        }
        for family in families
    ] if len(families) >= 2 else []

    if naive_authorized:
        strategy = "single_family_homogeneous_validation"
        promotion_status = "eligible_for_within_family_validation_only"
    else:
        strategy = (
            "machine_source_stratified_leave_one_experiment_family_out"
            if len(families) >= 2
            else "source_stratified_no_cross_source_promotion_yet"
        )
        promotion_status = "naive_pooled_scientific_promotion_blocked"

    return {
        "record_count": len(normalized),
        "experiment_family_ids": families,
        "machine_ids": machines,
        "material_states": states,
        "power_semantics": power_semantics,
        "evidence_strata": strata,
        "naive_pooled_validation_authorized": naive_authorized,
        "strategy": strategy,
        "promotion_status": promotion_status,
        "explicit_factors": {
            "experiment_family_id": len(families) >= 2,
            "machine_id": len(machines) >= 2,
            "material_state": len(states) >= 2,
            "power_semantics": len(power_semantics) >= 2,
            "evidence_stratum": len(strata) >= 2,
        },
        "leave_one_experiment_family_out_folds": leave_one_family_out,
        "scientific_boundary": {
            "cross_source_pooled_fit_is_validation_without_stratification": False,
            "leave_one_family_out_is_available_with_one_family": False,
            "model_promotion_requires_holdout_results": len(families) >= 2,
            "issue_76_is_not_modified_by_cross_source_validation": True,
        },
    }


def require_naive_pooled_validation_authorized(
    plan: dict[str, Any],
) -> None:
    """Fail closed before a caller promotes a naive pooled cross-source result."""
    if not isinstance(plan, dict):
        raise CrossSourceValidationPolicyError("validation plan must be an object.")
    if plan.get("naive_pooled_validation_authorized") is not True:
        raise CrossSourceValidationPolicyError(
            "Naive pooled scientific validation is not authorized; use the "
            "stratified/leave-one-experiment-family-out plan instead."
        )
