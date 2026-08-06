from __future__ import annotations

from materials_data_analyzer.research_loop import nasa_action_policy as policy


def test_required_evidence_candidate_keeps_highest_score() -> None:
    target_reference = {
        "action_type": policy.EXTERNAL_DATA_REQUIREMENT_ACTION_TYPE,
        "score": 140,
        "trigger": "required_reference_metadata_missing",
    }
    protocol_support = {
        "action_type": policy.EXTERNAL_DATA_REQUIREMENT_ACTION_TYPE,
        "score": 135,
        "trigger": "protocol_groups_too_small",
    }

    assert policy._prefer_required_candidate(None, protocol_support) is protocol_support
    assert (
        policy._prefer_required_candidate(protocol_support, target_reference)
        is target_reference
    )
    assert (
        policy._prefer_required_candidate(target_reference, protocol_support)
        is target_reference
    )


def test_required_evidence_candidate_is_stable_on_equal_score() -> None:
    first = {"score": 140, "trigger": "first"}
    second = {"score": 140, "trigger": "second"}

    assert policy._prefer_required_candidate(first, second) is first
