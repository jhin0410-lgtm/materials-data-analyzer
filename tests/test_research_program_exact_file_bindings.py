from __future__ import annotations

import hashlib
import json
from pathlib import Path

from materials_data_analyzer.research_loop import research_program


def _mission_bytes(*, mission_id: str) -> bytes:
    return json.dumps(
        {
            "schema_version": "1.1",
            "mission_id": mission_id,
            "mission": "Exercise exact-byte program bindings.",
            "success_criteria": ["Preserve exact parsed bytes."],
            "constraints": [],
            "stop_rules": ["Stop after the binding check."],
            "autonomy_policy": {
                "goal_generation": "manual_only",
                "reasoning_proposals": "disabled",
                "typed_computational_actions": "disabled",
                "network_evidence_search": "disabled",
                "physical_experiment_execution": "disabled",
            },
            "workstreams": [
                {
                    "workstream_id": "snapshot-test",
                    "adapter_id": "nasa-battery",
                    "priority": 1,
                    "role": "binding regression",
                    "enabled": False,
                }
            ],
            "source_trust_policy_pins": [
                {"policy_id": "local-test-policy", "sha256": "a" * 64}
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_program_bindings_use_the_same_snapshots_that_were_parsed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    mission_path = tmp_path / "mission.json"
    context_path = tmp_path / "runtime-context.json"
    mission_original = _mission_bytes(mission_id="original-mission")
    mission_mutated = _mission_bytes(mission_id="mutated-mission")
    context_original = b'{"schema_version":"1.0","workstreams":{}}'
    context_mutated = b'{"schema_version":"1.0","workstreams":{"late":{}}}'
    mission_path.write_bytes(mission_original)
    context_path.write_bytes(context_original)

    real_snapshot = research_program._load_json_snapshot

    def snapshot_then_mutate(path: Path):
        value, sha256 = real_snapshot(path)
        if path == mission_path:
            path.write_bytes(mission_mutated)
        elif path == context_path:
            path.write_bytes(context_mutated)
        return value, sha256

    monkeypatch.setattr(research_program, "_load_json_snapshot", snapshot_then_mutate)

    program = research_program.build_research_program(
        mission_path,
        repository_root=tmp_path,
        runtime_context_path=context_path,
    )

    assert mission_path.read_bytes() == mission_mutated
    assert context_path.read_bytes() == context_mutated
    assert program["mission"]["mission_id"] == "original-mission"
    assert program["mission_binding"]["sha256"] == hashlib.sha256(
        mission_original
    ).hexdigest()
    assert program["runtime_context_binding"]["sha256"] == hashlib.sha256(
        context_original
    ).hexdigest()


def test_reasoning_proposal_binding_uses_the_same_snapshot_that_was_parsed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    proposal_path = tmp_path / "proposal.json"
    proposal_original = json.dumps(
        {
            "schema_version": "1.0",
            "proposal_id": "proposal-original",
            "goal_id": "goal-1",
            "research_question": "What evidence is still missing?",
            "evidence_bindings": [],
            "new_hypotheses": [],
            "proposed_actions": [],
            "known_limitations": ["Planning only."],
            "stop_condition": "Stop after validation.",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    proposal_mutated = proposal_original.replace(
        b"proposal-original", b"proposal-mutated!"
    )
    proposal_path.write_bytes(proposal_original)

    real_snapshot = research_program._load_json_snapshot

    def snapshot_then_mutate(path: Path):
        value, sha256 = real_snapshot(path)
        if path == proposal_path:
            path.write_bytes(proposal_mutated)
        return value, sha256

    monkeypatch.setattr(research_program, "_load_json_snapshot", snapshot_then_mutate)

    program_state = {
        "generated_goals": [
            {
                "goal_id": "goal-1",
                "research_question": "What evidence is still missing?",
            }
        ],
        "workstreams": [],
    }
    validated = research_program.validate_reasoning_proposal_file(
        proposal_path,
        program_state,
    )

    assert proposal_path.read_bytes() == proposal_mutated
    assert validated["proposal_id"] == "proposal-original"
    assert validated["proposal_binding"]["sha256"] == hashlib.sha256(
        proposal_original
    ).hexdigest()


def test_snapshot_rejects_invalid_utf8_without_falling_back_to_path_state(
    tmp_path: Path,
) -> None:
    path = tmp_path / "invalid.json"
    path.write_bytes(b"\xff{\"schema_version\":\"1.0\"}")

    try:
        research_program._load_json_snapshot(path)
    except research_program.ResearchProgramError as exc:
        assert "valid UTF-8 JSON" in str(exc)
    else:
        raise AssertionError("invalid UTF-8 must fail closed")
