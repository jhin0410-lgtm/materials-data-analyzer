from __future__ import annotations

import pytest

from materials_data_analyzer.research_loop.in625_cross_source_validation_policy import (
    CrossSourceValidationPolicyError,
    build_cross_source_validation_plan,
    require_naive_pooled_validation_authorized,
)


def _record(
    family: str,
    machine: str,
    *,
    material_state: str = "bare_plate",
    power_semantics: str = "machine_setting",
    stratum: str = "publication_derived_physical",
) -> dict[str, object]:
    return {
        "experiment_family_id": family,
        "machine_id": machine,
        "material_state": material_state,
        "power_semantics": power_semantics,
        "evidence_stratum": stratum,
    }


def test_heterogeneous_sources_generate_leave_one_family_out_plan_and_block_pooling() -> None:
    records = [
        _record("family-a", "eos_m270"),
        _record("family-a", "eos_m270"),
        _record("family-b", "concept_laser_m2", material_state="powder_single_track"),
    ]
    audit = {
        "naive_cross_source_pooling_allowed": False,
        "duplicate_physical_response_views": [],
    }

    plan = build_cross_source_validation_plan(records, audit)

    assert plan["naive_pooled_validation_authorized"] is False
    assert plan["strategy"] == (
        "machine_source_stratified_leave_one_experiment_family_out"
    )
    assert len(plan["leave_one_experiment_family_out_folds"]) == 2
    assert plan["explicit_factors"]["experiment_family_id"] is True
    assert plan["explicit_factors"]["machine_id"] is True
    assert plan["explicit_factors"]["material_state"] is True
    with pytest.raises(CrossSourceValidationPolicyError, match="not authorized"):
        require_naive_pooled_validation_authorized(plan)


def test_single_homogeneous_family_can_only_authorize_with_matching_intake_audit() -> None:
    records = [_record("family-a", "eos_m270"), _record("family-a", "eos_m270")]
    audit = {
        "naive_cross_source_pooling_allowed": True,
        "duplicate_physical_response_views": [],
    }

    plan = build_cross_source_validation_plan(records, audit)
    assert plan["naive_pooled_validation_authorized"] is True
    assert plan["strategy"] == "single_family_homogeneous_validation"
    assert plan["leave_one_experiment_family_out_folds"] == []
    require_naive_pooled_validation_authorized(plan)


def test_duplicate_response_views_override_false_positive_audit_authorization() -> None:
    records = [_record("family-a", "eos_m270")]
    audit = {
        "naive_cross_source_pooling_allowed": True,
        "duplicate_physical_response_views": [
            {
                "experiment_family_id": "family-a",
                "replication_unit_id": "track-1",
                "response_name": "melt_pool_width",
                "record_ids": ["paper", "repo"],
            }
        ],
    }

    plan = build_cross_source_validation_plan(records, audit)
    assert plan["naive_pooled_validation_authorized"] is False
    with pytest.raises(CrossSourceValidationPolicyError):
        require_naive_pooled_validation_authorized(plan)


def test_audit_cannot_claim_pooling_for_multiple_experiment_families() -> None:
    records = [_record("family-a", "eos_m270"), _record("family-b", "eos_m270")]
    audit = {
        "naive_cross_source_pooling_allowed": True,
        "duplicate_physical_response_views": [],
    }

    plan = build_cross_source_validation_plan(records, audit)
    assert plan["naive_pooled_validation_authorized"] is False
    assert len(plan["leave_one_experiment_family_out_folds"]) == 2
