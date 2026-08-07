from __future__ import annotations

from pathlib import Path

from materials_data_analyzer.research_loop import nasa_action_policy as policy
from materials_data_analyzer.research_loop import (
    nasa_external_data_requirement_action as requirement_action,
)


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


def test_executor_prefers_target_reference_blocker(monkeypatch) -> None:
    target_path = Path("target-action-result.json")
    protocol_path = Path("protocol-action-result.json")
    calls: list[str] = []

    def fake_action_report_path(state, action_type):
        del state
        return {
            "target_reference_sensitivity": target_path,
            "protocol_stratification": protocol_path,
        }[action_type]

    def fake_target_requirement(path):
        calls.append("target")
        assert path == target_path
        return ({"outcome": "target"}, [path])

    def fail_protocol_requirement(path):
        raise AssertionError(f"protocol must not override target blocker: {path}")

    monkeypatch.setattr(
        requirement_action,
        "_action_report_path",
        fake_action_report_path,
    )
    monkeypatch.setattr(
        requirement_action,
        "_target_requirement",
        fake_target_requirement,
    )
    monkeypatch.setattr(
        requirement_action,
        "_protocol_requirement",
        fail_protocol_requirement,
    )

    requirement, inputs = requirement_action._build_requirement({})

    assert requirement == {"outcome": "target"}
    assert inputs == [target_path]
    assert calls == ["target"]


def test_executor_falls_back_to_protocol_when_target_is_resolved(monkeypatch) -> None:
    target_path = Path("target-action-result.json")
    protocol_path = Path("protocol-action-result.json")
    calls: list[str] = []

    def fake_action_report_path(state, action_type):
        del state
        return {
            "target_reference_sensitivity": target_path,
            "protocol_stratification": protocol_path,
        }[action_type]

    def fake_target_requirement(path):
        calls.append("target")
        assert path == target_path
        return None

    def fake_protocol_requirement(path):
        calls.append("protocol")
        assert path == protocol_path
        return ({"outcome": "protocol"}, [path])

    monkeypatch.setattr(
        requirement_action,
        "_action_report_path",
        fake_action_report_path,
    )
    monkeypatch.setattr(
        requirement_action,
        "_target_requirement",
        fake_target_requirement,
    )
    monkeypatch.setattr(
        requirement_action,
        "_protocol_requirement",
        fake_protocol_requirement,
    )

    requirement, inputs = requirement_action._build_requirement({})

    assert requirement == {"outcome": "protocol"}
    assert inputs == [protocol_path]
    assert calls == ["target", "protocol"]
