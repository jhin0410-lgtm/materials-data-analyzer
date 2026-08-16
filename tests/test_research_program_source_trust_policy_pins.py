from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.research_program import (
    ResearchProgramError,
    build_research_program,
    validate_research_mission,
)


def _mission() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "mission_id": "pin-test-mission",
        "mission": "Exercise mission-level source-trust policy pins.",
        "success_criteria": ["Keep policy authority explicit."],
        "constraints": ["Do not infer provider identity from labels."],
        "stop_rules": ["Stop on provenance ambiguity."],
        "autonomy_policy": {
            "goal_generation": "bounded_autonomous",
            "reasoning_proposals": "schema_validated",
            "typed_computational_actions": "explicit_request",
            "network_evidence_search": "explicit_authorization",
            "physical_experiment_execution": "external_only",
        },
        "workstreams": [
            {
                "workstream_id": "nist",
                "adapter_id": "nist-ambench-process-characterization",
                "priority": 90,
                "role": "test workstream",
                "enabled": True,
            }
        ],
    }


def _planning_state() -> dict[str, object]:
    return {
        "research_question": "Can this bounded state be used for pin tests?",
        "current_blocker": {
            "kind": "evidence",
            "code": "pin-test",
            "summary": "A bounded blocker exists.",
        },
        "evidence_gap": {"status": "open", "requirements": []},
        "stop_state": {
            "status": "continue",
            "selection_status": "ready_to_execute",
            "reason": "Test fixture.",
            "reopen_conditions": [],
        },
        "selected_action": None,
        "action_frontier": [],
        "claim_boundary": {},
        "evidence_bindings": [],
    }


def _pin(policy_id: str = "mp-local-v1", sha256: str = "a" * 64) -> dict[str, str]:
    return {"policy_id": policy_id, "sha256": sha256}


def test_legacy_mission_without_policy_pins_remains_valid() -> None:
    normalized = validate_research_mission(_mission())
    assert "source_trust_policy_pins" not in normalized


def test_mission_normalizes_first_class_policy_pins() -> None:
    mission = _mission()
    mission["schema_version"] = "1.1"
    mission["source_trust_policy_pins"] = [_pin()]
    normalized = validate_research_mission(mission)
    assert normalized["source_trust_policy_pins"] == [_pin()]


def test_policy_pin_rejects_uppercase_sha() -> None:
    mission = _mission()
    mission["schema_version"] = "1.1"
    mission["source_trust_policy_pins"] = [_pin(sha256="A" * 64)]
    with pytest.raises(ResearchProgramError, match="lowercase SHA-256"):
        validate_research_mission(mission)


def test_policy_pin_rejects_surrounding_policy_id_whitespace() -> None:
    mission = _mission()
    mission["schema_version"] = "1.1"
    mission["source_trust_policy_pins"] = [_pin(policy_id=" mp-local-v1 ")]
    with pytest.raises(ResearchProgramError, match="surrounding whitespace"):
        validate_research_mission(mission)


def test_policy_pin_rejects_unknown_fields() -> None:
    mission = _mission()
    mission["schema_version"] = "1.1"
    pin = {**_pin(), "provider_authenticated": True}
    mission["source_trust_policy_pins"] = [pin]
    with pytest.raises(ResearchProgramError, match="unknown keys"):
        validate_research_mission(mission)


def test_policy_pin_rejects_duplicate_policy_ids() -> None:
    mission = _mission()
    mission["schema_version"] = "1.1"
    mission["source_trust_policy_pins"] = [_pin(), _pin(sha256="b" * 64)]
    with pytest.raises(ResearchProgramError, match="duplicate source trust policy policy_id"):
        validate_research_mission(mission)


def test_policy_pin_rejects_duplicate_policy_shas() -> None:
    mission = _mission()
    mission["schema_version"] = "1.1"
    mission["source_trust_policy_pins"] = [_pin(), _pin(policy_id="alias")]
    with pytest.raises(ResearchProgramError, match="duplicate source trust policy sha256"):
        validate_research_mission(mission)


def test_policy_pin_field_cannot_be_empty_when_explicitly_present() -> None:
    mission = _mission()
    mission["schema_version"] = "1.1"
    mission["source_trust_policy_pins"] = []
    with pytest.raises(ResearchProgramError, match="non-empty list"):
        validate_research_mission(mission)


def test_metadata_does_not_create_first_class_policy_pins() -> None:
    mission = _mission()
    mission["metadata"] = {
        "source_trust_policy_pins": [_pin()],
        "provider_authenticated": True,
    }
    normalized = validate_research_mission(mission)
    assert "source_trust_policy_pins" not in normalized
    assert normalized["metadata"]["provider_authenticated"] is True


def test_program_exports_normalized_policy_pins_and_exact_mission_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mission = _mission()
    mission["schema_version"] = "1.1"
    mission["source_trust_policy_pins"] = [_pin()]
    raw = (json.dumps(mission, sort_keys=True) + "\n").encode()
    mission_path = tmp_path / "mission.json"
    mission_path.write_bytes(raw)
    monkeypatch.setattr(
        "materials_data_analyzer.research_loop.research_program.build_research_planning_state",
        lambda *args, **kwargs: _planning_state(),
    )
    program = build_research_program(mission_path, repository_root=tmp_path)
    assert program["source_trust_policy_pins"] == [_pin()]
    assert program["mission_binding"]["sha256"] == hashlib.sha256(raw).hexdigest()


def test_program_without_policy_pins_exports_empty_pin_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mission_path = tmp_path / "mission.json"
    mission_path.write_text(json.dumps(_mission()), encoding="utf-8")
    monkeypatch.setattr(
        "materials_data_analyzer.research_loop.research_program.build_research_planning_state",
        lambda *args, **kwargs: _planning_state(),
    )
    program = build_research_program(mission_path, repository_root=tmp_path)
    assert program["source_trust_policy_pins"] == []


def test_changing_policy_pin_changes_exact_mission_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "materials_data_analyzer.research_loop.research_program.build_research_planning_state",
        lambda *args, **kwargs: _planning_state(),
    )
    mission = _mission()
    mission["schema_version"] = "1.1"
    mission["source_trust_policy_pins"] = [_pin(sha256="a" * 64)]
    first = tmp_path / "first.json"
    first.write_text(json.dumps(mission, sort_keys=True), encoding="utf-8")
    first_program = build_research_program(first, repository_root=tmp_path)

    mission["source_trust_policy_pins"] = [_pin(sha256="b" * 64)]
    second = tmp_path / "second.json"
    second.write_text(json.dumps(mission, sort_keys=True), encoding="utf-8")
    second_program = build_research_program(second, repository_root=tmp_path)

    assert first_program["mission_binding"]["sha256"] != second_program["mission_binding"]["sha256"]
    assert first_program["source_trust_policy_pins"] != second_program["source_trust_policy_pins"]



def test_legacy_schema_cannot_smuggle_policy_pins() -> None:
    mission = _mission()
    mission["source_trust_policy_pins"] = [_pin()]
    with pytest.raises(ResearchProgramError, match="requires mission schema_version 1.1"):
        validate_research_mission(mission)


def test_current_schema_without_policy_pins_remains_valid() -> None:
    mission = _mission()
    mission["schema_version"] = "1.1"
    normalized = validate_research_mission(mission)
    assert normalized["schema_version"] == "1.1"
    assert "source_trust_policy_pins" not in normalized



def test_program_shape_change_uses_schema_1_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mission_path = tmp_path / "mission.json"
    mission_path.write_text(json.dumps(_mission()), encoding="utf-8")
    monkeypatch.setattr(
        "materials_data_analyzer.research_loop.research_program.build_research_planning_state",
        lambda *args, **kwargs: _planning_state(),
    )
    program = build_research_program(mission_path, repository_root=tmp_path)
    assert program["schema_version"] == "1.1"
    assert "source_trust_policy_pins" in program
