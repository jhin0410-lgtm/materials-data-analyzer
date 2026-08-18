from __future__ import annotations

import copy

import pytest

from materials_data_analyzer.research_loop.live_real_data_mvp_sequence import (
    LiveMvpSequenceError,
    bind_live_episode_sequence,
)


def _report(
    *,
    episode_id: str,
    family: str,
    modality: str,
    evidence_class: str,
    observed_artifacts: dict[str, str],
) -> dict[str, object]:
    placeholder_action_sha = "f" * 64
    return {
        "episode_id": episode_id,
        "episode_family_id": family,
        "modality": modality,
        "evidence_class": evidence_class,
        "real_source_binding": {
            "source_kind": "real-test-source",
            "source_locator": f"doi:test/{episode_id}",
            "artifact_sha256": "a" * 64,
            "acquisition_receipt_sha256": None,
            "synthetic": False,
        },
        "research_question": f"What does {episode_id} support?",
        "scientific_intake": {"status": "accepted", "reason": "bounded real evidence"},
        "analysis": {"performed": True},
        "weaknesses_or_contradictions": ["bounded weakness"],
        "next_action_decision": {
            "decision_report_sha256": placeholder_action_sha,
            "action_recorded": True,
        },
        "next_action_record": {"action_type": "placeholder"},
        "iteration_count": 2,
        "terminal_state": "stopped",
        "terminal_reason": "bounded stop",
        "scientific_status_changed": False,
        "scientific_promotion_authorized": False,
        "observed_artifacts": observed_artifacts,
    }


def _suite() -> dict[str, object]:
    return {
        "episode_reports": [
            _report(
                episode_id="live-nasa-pcoe-battery-v1",
                family="nasa",
                modality="battery",
                evidence_class="E0_raw_experiment",
                observed_artifacts={
                    "target_comparability_audit_sha256": "1" * 64,
                    "battery_influence_triage_sha256": "2" * 64,
                    "diagnostic_priority_sha256": "3" * 64,
                    "protocol_audit_sha256": "4" * 64,
                },
            ),
            _report(
                episode_id="live-public-dwcnt-multimodal-v1",
                family="dwcnt",
                modality="spectroscopy",
                evidence_class="E1_processed_experiment",
                observed_artifacts={
                    "source_manifest_sha256": "5" * 64,
                    "analysis_manifest_sha256": "6" * 64,
                    "tga_case_review_sha256": "7" * 64,
                },
            ),
            _report(
                episode_id="live-public-rwgs-xrd-eds-v1",
                family="rwgs",
                modality="characterization",
                evidence_class="E1_processed_experiment",
                observed_artifacts={
                    "analysis_manifest_sha256": "8" * 64,
                    "comparability_matrix_sha256": "9" * 64,
                    "independent_validation_summary_sha256": "b" * 64,
                },
            ),
        ],
        "scientific_status_changed": False,
        "execution_authorized_here": False,
        "human_review_synthesized_here": False,
        "issue_76_status_changed_here": False,
        "result_sha256": "c" * 64,
    }


def test_sequence_binding_records_actual_action_before_reanalysis() -> None:
    result = bind_live_episode_sequence(_suite())
    assert result["suite_acceptance"]["mvp_acceptance_passed"] is True
    assert result["sequence_binding"]["weakness_to_action_to_reanalysis_bound"] is True
    assert result["sequence_binding"]["future_followups_kept_separate_from_completed_reanalysis"] is True
    for episode in result["episode_reports"]:
        decision_sha = episode["next_action_decision"]["decision_report_sha256"]
        reanalysis = episode["reanalysis_record"]
        assert reanalysis["iteration"] == 2
        assert reanalysis["triggering_decision_sha256"] == decision_sha
        assert reanalysis["scientific_status_changed"] is False
        assert episode["post_stop_followup"]["executed_in_this_episode"] is False
        assert episode["scientific_status_changed"] is False


def test_missing_persisted_reanalysis_artifact_fails_closed() -> None:
    value = _suite()
    del value["episode_reports"][1]["observed_artifacts"]["tga_case_review_sha256"]
    with pytest.raises(LiveMvpSequenceError, match="tga_case_review_sha256"):
        bind_live_episode_sequence(value)


def test_scientific_promotion_cannot_be_hidden_by_sequence_binding() -> None:
    value = _suite()
    value["episode_reports"][2]["scientific_status_changed"] = True
    with pytest.raises(LiveMvpSequenceError, match="changed scientific status"):
        bind_live_episode_sequence(value)


def test_sequence_binding_is_deterministic_and_does_not_mutate_input() -> None:
    value = _suite()
    original = copy.deepcopy(value)
    first = bind_live_episode_sequence(value)
    second = bind_live_episode_sequence(value)
    assert first == second
    assert value == original
    assert first["result_sha256"] != original["result_sha256"]
