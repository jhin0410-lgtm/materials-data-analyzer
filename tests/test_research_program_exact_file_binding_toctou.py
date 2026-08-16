from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import materials_data_analyzer.research_loop.research_program as research_program
from materials_data_analyzer.research_loop.research_program import (
    ResearchProgramError,
    build_research_program,
    validate_reasoning_proposal_file,
)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _mission(*, nasa: bool = False) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "mission_id": "snapshot-mission",
        "mission": "Verify one immutable file snapshot per exact binding.",
        "success_criteria": ["Parsed content and binding SHA identify the same bytes."],
        "constraints": ["Do not infer scientific authority from file integrity."],
        "stop_rules": ["Stop on any exact-file binding mismatch."],
        "autonomy_policy": {
            "goal_generation": "bounded_autonomous",
            "reasoning_proposals": "schema_validated",
            "typed_computational_actions": "explicit_request",
            "network_evidence_search": "explicit_authorization",
            "physical_experiment_execution": "external_only",
        },
        "workstreams": [
            {
                "workstream_id": "nasa" if nasa else "nist",
                "adapter_id": "nasa-battery" if nasa else "nist-ambench-process-characterization",
                "priority": 90,
                "role": "binding-race regression",
                "enabled": True,
            }
        ],
    }


def _planning_state() -> dict[str, object]:
    return {
        "research_question": "Does one snapshot bind parsing and hashing?",
        "current_blocker": {
            "kind": "provenance",
            "code": "snapshot-binding",
            "summary": "Exact file bytes must remain bound to their parsed content.",
        },
        "evidence_gap": {"status": "open", "requirements": []},
        "stop_state": {
            "status": "continue",
            "selection_status": "ready_to_execute",
            "reason": "Regression fixture.",
            "reopen_conditions": [],
        },
        "selected_action": None,
        "action_frontier": [],
        "claim_boundary": {},
        "evidence_bindings": [],
    }


def _program_for_reasoning() -> dict[str, object]:
    return {
        "generated_goals": [
            {
                "goal_id": "snapshot-mission:nist:resolve-current-blocker",
                "research_question": "Does one snapshot bind parsing and hashing?",
            }
        ],
        "workstreams": [
            {
                "workstream_id": "nist",
                "planning_state": {
                    "evidence_bindings": [
                        {"role": "bound", "sha256": "a" * 64}
                    ]
                },
            }
        ],
    }


def _proposal() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "proposal_id": "snapshot-proposal",
        "goal_id": "snapshot-mission:nist:resolve-current-blocker",
        "research_question": "Does one snapshot bind parsing and hashing?",
        "evidence_bindings": [
            {"workstream_id": "nist", "role": "bound", "sha256": "a" * 64}
        ],
        "new_hypotheses": [],
        "proposed_actions": [],
        "known_limitations": ["File integrity does not establish scientific validity."],
        "stop_condition": "Stop on any provenance mismatch.",
    }


def test_mission_binding_uses_same_snapshot_that_was_parsed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission_path = tmp_path / "mission.json"
    original_bytes = _json_bytes(_mission())
    mission_path.write_bytes(original_bytes)
    replacement = _mission()
    replacement["mission_id"] = "replacement-mission"
    replacement_bytes = _json_bytes(replacement)

    original_loader = research_program._load_json_snapshot

    def mutate_after_snapshot(path: Path) -> tuple[dict[str, object], str]:
        value, sha256 = original_loader(path)
        if path == mission_path.resolve():
            path.write_bytes(replacement_bytes)
        return value, sha256

    monkeypatch.setattr(research_program, "_load_json_snapshot", mutate_after_snapshot)
    monkeypatch.setattr(
        research_program,
        "build_research_planning_state",
        lambda *args, **kwargs: _planning_state(),
    )

    program = build_research_program(mission_path, repository_root=tmp_path)

    assert program["mission"]["mission_id"] == "snapshot-mission"
    assert program["mission_binding"]["sha256"] == hashlib.sha256(original_bytes).hexdigest()
    assert program["mission_binding"]["sha256"] != hashlib.sha256(replacement_bytes).hexdigest()
    assert mission_path.read_bytes() == replacement_bytes


def test_runtime_context_binding_uses_same_snapshot_that_was_parsed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission_path = tmp_path / "mission.json"
    mission_path.write_bytes(_json_bytes(_mission(nasa=True)))
    context_path = tmp_path / "context.json"
    original_context = {
        "schema_version": "1.0",
        "workstreams": {
            "nasa": {
                "research_run": "run-A",
                "action_registry_path": "registry-A.json",
            }
        },
    }
    original_bytes = _json_bytes(original_context)
    context_path.write_bytes(original_bytes)
    replacement_context = {
        "schema_version": "1.0",
        "workstreams": {
            "nasa": {
                "research_run": "run-B",
                "action_registry_path": "registry-B.json",
            }
        },
    }
    replacement_bytes = _json_bytes(replacement_context)
    captured: dict[str, object] = {}

    original_loader = research_program._load_json_snapshot

    def mutate_after_snapshot(path: Path) -> tuple[dict[str, object], str]:
        value, sha256 = original_loader(path)
        if path == context_path.resolve():
            path.write_bytes(replacement_bytes)
        return value, sha256

    def planning_state(*args: object, **kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return _planning_state()

    monkeypatch.setattr(research_program, "_load_json_snapshot", mutate_after_snapshot)
    monkeypatch.setattr(research_program, "build_research_planning_state", planning_state)

    program = build_research_program(
        mission_path,
        repository_root=tmp_path,
        runtime_context_path=context_path,
    )

    assert captured["research_run"] == "run-A"
    assert captured["action_registry_path"] == "registry-A.json"
    assert program["runtime_context_binding"]["sha256"] == hashlib.sha256(original_bytes).hexdigest()
    assert program["runtime_context_binding"]["sha256"] != hashlib.sha256(replacement_bytes).hexdigest()
    assert context_path.read_bytes() == replacement_bytes


def test_reasoning_proposal_binding_uses_same_snapshot_that_was_parsed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_path = tmp_path / "proposal.json"
    original_bytes = _json_bytes(_proposal())
    proposal_path.write_bytes(original_bytes)
    replacement = _proposal()
    replacement["proposal_id"] = "replacement-proposal"
    replacement_bytes = _json_bytes(replacement)

    original_loader = research_program._load_json_snapshot

    def mutate_after_snapshot(path: Path) -> tuple[dict[str, object], str]:
        value, sha256 = original_loader(path)
        if path == proposal_path.resolve():
            path.write_bytes(replacement_bytes)
        return value, sha256

    monkeypatch.setattr(research_program, "_load_json_snapshot", mutate_after_snapshot)

    result = validate_reasoning_proposal_file(proposal_path, _program_for_reasoning())

    assert result["proposal_id"] == "snapshot-proposal"
    assert result["proposal_binding"]["sha256"] == hashlib.sha256(original_bytes).hexdigest()
    assert result["proposal_binding"]["sha256"] != hashlib.sha256(replacement_bytes).hexdigest()
    assert proposal_path.read_bytes() == replacement_bytes


def test_exact_snapshot_rejects_invalid_utf8_with_domain_error(tmp_path: Path) -> None:
    mission_path = tmp_path / "mission.json"
    mission_path.write_bytes(b"\xff\xfe")
    with pytest.raises(ResearchProgramError, match="valid UTF-8 JSON"):
        build_research_program(mission_path, repository_root=tmp_path)


def test_exact_snapshot_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    mission_path = tmp_path / "mission.json"
    mission_path.write_bytes(b'{"schema_version":"1.0","schema_version":"1.0"}')
    with pytest.raises(ResearchProgramError, match="duplicate JSON key"):
        build_research_program(mission_path, repository_root=tmp_path)
