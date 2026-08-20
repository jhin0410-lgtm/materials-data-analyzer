from __future__ import annotations

from materials_data_analyzer.research_loop.delimited_structural_intake import (
    inspect_delimited_structure,
)
from materials_data_analyzer.research_loop.post_mvp_failure_mode_benchmark import (
    evaluate_structural_claim_safety,
    run_post_mvp_failure_mode_benchmark,
)


def test_locked_post_mvp_failure_modes_have_zero_unsafe_authorization():
    report = run_post_mvp_failure_mode_benchmark()

    assert report["scenario_count"] == 5
    assert report["unsafe_authorization_count"] == 0
    assert report["missing_required_blocker_scenario_count"] == 0
    assert report["scientific_status_change_count"] == 0
    assert report["zero_false_evidence_promotion"] is True
    assert report["all_required_failure_modes_detected"] is True
    assert report["generic_intake_scientific_status_unchanged"] is True
    assert report["benchmark_pass"] is True
    assert report["regression_fixtures_are_scientific_evidence"] is False
    assert len(report["benchmark_sha256"]) == 64


def test_repeated_time_rows_cannot_be_promoted_to_replicate_effect():
    structure = inspect_delimited_structure(
        b"time_s,value\n0.0,1.0\n0.1,1.1\n0.2,1.2\n"
    )

    result = evaluate_structural_claim_safety(
        structure=structure,
        claim_kind="independent_replicate_effect",
        provenance_authenticated=True,
        domain_intake_accepted=True,
        independent_units_established=False,
    )

    assert result["authorized"] is False
    assert "independent_experimental_units_not_established" in result["blockers"]
    assert "repeated_observation_axis_cannot_supply_independent_n" in result["blockers"]
    assert result["scientific_status_changed"] is False


def test_valid_generic_structure_still_needs_separate_domain_acceptance():
    structure = inspect_delimited_structure(b"sample_id,value\ns1,1\ns2,2\n")

    result = evaluate_structural_claim_safety(
        structure=structure,
        claim_kind="scientific_status_promotion",
        provenance_authenticated=True,
        domain_intake_accepted=False,
    )

    assert result["authorized"] is False
    assert result["blockers"] == ["domain_scientific_intake_not_accepted"]
