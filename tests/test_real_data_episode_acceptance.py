from __future__ import annotations

import pytest

from materials_data_analyzer.research_loop.real_data_episode_acceptance import (
    RealDataEpisodeAcceptanceError,
    evaluate_real_data_episode,
    evaluate_real_data_episode_suite,
)


def _report(
    episode_id: str,
    family: str,
    modality: str,
    evidence_class: str,
    *,
    intake: str = "accepted",
    analysis: bool = True,
    iterations: int = 2,
    terminal: str = "stopped",
) -> dict:
    return {
        "episode_id": episode_id,
        "episode_family_id": family,
        "modality": modality,
        "evidence_class": evidence_class,
        "research_question": "Does the independently bound evidence resolve the declared gap?",
        "real_source_binding": {
            "source_kind": "public_repository_artifact",
            "source_locator": f"doi:10.0000/{family}",
            "artifact_sha256": "a" * 64,
            "acquisition_receipt_sha256": "b" * 64,
            "synthetic": False,
        },
        "scientific_intake": {
            "status": intake,
            "reason": "domain semantics were explicitly adjudicated" if intake == "accepted" else "review remains unresolved",
        },
        "analysis": {
            "performed": analysis,
            "ineligibility_reason": None if analysis else "scientific intake did not authorize analysis",
        },
        "weaknesses_or_contradictions": ["cross-source comparability remains bounded"],
        "next_action_decision": {
            "decision_report_sha256": "c" * 64,
            "action_recorded": True,
        },
        "iteration_count": iterations,
        "terminal_state": terminal,
        "terminal_reason": "bounded evidence scope exhausted",
        "scientific_status_changed": False,
        "scientific_promotion_authorized": False,
    }


def test_blocked_pending_review_episode_is_valid_but_not_mvp_full_cycle() -> None:
    report = _report(
        "zenodo-in625",
        "zenodo-in625-supplement",
        "lpbf_melt_pool",
        "E2_publication_supplement",
        intake="pending_review",
        analysis=False,
        iterations=1,
        terminal="blocked",
    )
    result = evaluate_real_data_episode(report)
    assert result["episode_valid"] is True
    assert result["bounded_blocked_episode"] is True
    assert result["mvp_full_cycle_complete"] is False


def test_three_materially_different_full_cycles_pass_suite() -> None:
    reports = [
        _report("ep-1", "in625", "lpbf_melt_pool", "E2_publication_supplement"),
        _report("ep-2", "nasa-battery", "battery_degradation", "E0_raw_experiment"),
        _report("ep-3", "tm-fe-si", "materials_characterization", "E1_processed_experiment"),
    ]
    result = evaluate_real_data_episode_suite(reports)
    assert result["full_cycle_count"] == 3
    assert result["materially_different_full_cycles"] is True
    assert result["mvp_acceptance_passed"] is True
    assert result["human_review_synthesized_here"] is False


def test_three_copies_of_same_family_do_not_satisfy_material_difference() -> None:
    reports = [
        _report(f"ep-{index}", "same-family", "same-modality", "E0_raw_experiment")
        for index in range(3)
    ]
    result = evaluate_real_data_episode_suite(reports)
    assert result["full_cycle_count"] == 3
    assert result["materially_different_full_cycles"] is False
    assert result["mvp_acceptance_passed"] is False


def test_synthetic_evidence_cannot_count_as_real_episode() -> None:
    report = _report("ep-synthetic", "sim", "simulation", "E6_computational_evidence")
    report["real_source_binding"]["synthetic"] = True
    result = evaluate_real_data_episode(report)
    assert result["stages"]["real_evidence_bound"] is False
    assert result["episode_valid"] is False
    assert result["mvp_full_cycle_complete"] is False


def test_false_scientific_promotion_invalidates_episode() -> None:
    report = _report("ep-bad", "in625", "lpbf_melt_pool", "E2_publication_supplement")
    report["scientific_status_changed"] = True
    result = evaluate_real_data_episode(report)
    assert result["false_scientific_promotion_detected"] is True
    assert result["episode_valid"] is False


def test_duplicate_episode_ids_fail_closed() -> None:
    one = _report("same-id", "f1", "m1", "E0_raw_experiment")
    two = _report("same-id", "f2", "m2", "E1_processed_experiment")
    with pytest.raises(RealDataEpisodeAcceptanceError, match="episode IDs"):
        evaluate_real_data_episode_suite([one, two], required_full_cycles=1)
