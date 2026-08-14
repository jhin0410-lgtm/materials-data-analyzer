from __future__ import annotations

import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.research_program import (
    ResearchProgramError,
    build_research_program,
    validate_reasoning_proposal,
    validate_research_mission,
)


def _mission(*, workstreams: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "mission_id": "autonomous-materials-research",
        "mission": "Resolve materials research questions through iterative verified evidence and bounded analysis.",
        "success_criteria": [
            "At least one workstream reaches a defensible scientific closeout.",
        ],
        "constraints": [
            "Never fabricate missing measurements or provenance.",
        ],
        "stop_rules": [
            "Stop a scope when no verified positive-value action remains.",
        ],
        "autonomy_policy": {
            "goal_generation": "bounded_autonomous",
            "reasoning_proposals": "schema_validated",
            "typed_computational_actions": "explicit_request",
            "network_evidence_search": "explicit_authorization",
            "physical_experiment_execution": "external_only",
        },
        "workstreams": workstreams
        or [
            {
                "workstream_id": "nist",
                "adapter_id": "nist-ambench-process-characterization",
                "priority": 90,
                "role": "process-characterization design benchmark",
                "enabled": True,
            }
        ],
    }


def _planning_state(*, question: str = "Can the current design support an interaction claim?") -> dict[str, object]:
    return {
        "research_question": question,
        "current_blocker": {
            "kind": "experimental_design",
            "code": "missing_factorial_cells",
            "summary": "Three observed process conditions do not identify the power-speed interaction.",
        },
        "evidence_gap": {
            "status": "additional_independent_conditions_required",
            "requirements": ["Complete the predeclared 2 x 3 process-condition grid."],
        },
        "stop_state": {
            "status": "continue",
            "selection_status": "ready_to_execute",
            "reason": "A bounded next experiment is defined.",
            "reopen_conditions": [],
        },
        "selected_action": {
            "action_type": "minimum_design_augmentation",
            "availability": "planned",
        },
        "action_frontier": [
            {
                "action_type": "minimum_design_augmentation",
                "availability": "planned",
            }
        ],
        "claim_boundary": {
            "evidence_level": "Diagnostic",
            "maximum_allowed_use": "descriptive_and_design_planning",
        },
        "evidence_bindings": [
            {
                "role": "design_readiness",
                "path": "configs/readiness.json",
                "sha256": "a" * 64,
            }
        ],
    }


def test_validate_mission_rejects_duplicate_workstream_ids() -> None:
    mission = _mission(
        workstreams=[
            {
                "workstream_id": "same",
                "adapter_id": "nist-ambench-process-characterization",
                "priority": 90,
                "role": "one",
                "enabled": True,
            },
            {
                "workstream_id": "same",
                "adapter_id": "tm-fe-si-descriptive",
                "priority": 80,
                "role": "two",
                "enabled": True,
            },
        ]
    )
    with pytest.raises(ResearchProgramError, match="duplicate workstream_id"):
        validate_research_mission(mission)


def test_validate_mission_rejects_boolean_priority() -> None:
    mission = _mission()
    mission["workstreams"][0]["priority"] = True  # type: ignore[index]
    with pytest.raises(ResearchProgramError, match="priority must be an integer"):
        validate_research_mission(mission)


def test_build_program_generates_goal_from_verified_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mission_path = tmp_path / "mission.json"
    mission_path.write_text(json.dumps(_mission()), encoding="utf-8")
    monkeypatch.setattr(
        "materials_data_analyzer.research_loop.research_program.build_research_planning_state",
        lambda *args, **kwargs: _planning_state(),
    )

    program = build_research_program(mission_path, repository_root=tmp_path)

    assert program["autonomy_boundary"]["goal_generation_performed"] is True
    assert program["autonomy_boundary"]["scientific_hypotheses_invented"] is False
    assert program["generated_goals"][0]["origin"] == (
        "self_generated_from_verified_planning_state"
    )
    assert program["generated_goals"][0]["status"] == "active"
    assert program["next_program_step"]["mode"] == "delegate_typed_action"
    assert program["next_program_step"]["automatic_execution_authorized"] is False


def test_program_prioritizes_mission_priority_not_fake_information_gain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mission = _mission(
        workstreams=[
            {
                "workstream_id": "low",
                "adapter_id": "tm-fe-si-descriptive",
                "priority": 20,
                "role": "lower priority",
                "enabled": True,
            },
            {
                "workstream_id": "high",
                "adapter_id": "nist-ambench-process-characterization",
                "priority": 95,
                "role": "higher priority",
                "enabled": True,
            },
        ]
    )
    mission_path = tmp_path / "mission.json"
    mission_path.write_text(json.dumps(mission), encoding="utf-8")
    monkeypatch.setattr(
        "materials_data_analyzer.research_loop.research_program.build_research_planning_state",
        lambda *args, **kwargs: _planning_state(),
    )

    program = build_research_program(mission_path, repository_root=tmp_path)

    assert program["generated_goals"][0]["workstream_id"] == "high"
    assert program["generated_goals"][0]["expected_information_gain"]["status"] == (
        "not_quantified"
    )


def test_nasa_workstream_fails_closed_to_runtime_context_goal(tmp_path: Path) -> None:
    mission = _mission(
        workstreams=[
            {
                "workstream_id": "nasa",
                "adapter_id": "nasa-battery",
                "priority": 100,
                "role": "battery longitudinal research benchmark",
                "enabled": True,
            }
        ]
    )
    mission_path = tmp_path / "mission.json"
    mission_path.write_text(json.dumps(mission), encoding="utf-8")

    program = build_research_program(mission_path, repository_root=tmp_path)

    goal = program["generated_goals"][0]
    assert goal["status"] == "runtime_context_required"
    assert program["next_program_step"]["mode"] == "supply_runtime_context"
    assert program["workstreams"][0]["planning_state"] is None


def _program_for_reasoning() -> dict[str, object]:
    goal_id = "mission:nist:resolve-current-blocker"
    question = "Can the current design support an interaction claim?"
    return {
        "generated_goals": [
            {
                "goal_id": goal_id,
                "research_question": question,
            }
        ],
        "workstreams": [
            {
                "workstream_id": "nist",
                "planning_state": {
                    "evidence_bindings": [
                        {
                            "role": "design_readiness",
                            "sha256": "a" * 64,
                        }
                    ]
                },
            }
        ],
    }


def _proposal(*, action_class: str, execution_mode: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "proposal_id": "proposal-1",
        "goal_id": "mission:nist:resolve-current-blocker",
        "research_question": "Can the current design support an interaction claim?",
        "evidence_bindings": [
            {
                "workstream_id": "nist",
                "role": "design_readiness",
                "sha256": "a" * 64,
            }
        ],
        "new_hypotheses": [
            {
                "hypothesis_id": "h1",
                "statement": "A power-speed interaction may be distinguishable after the missing cells are measured.",
                "falsification_criteria": [
                    "The completed design remains rank deficient for the interaction term."
                ],
                "discriminating_evidence": [
                    "Independent traces at all predeclared missing process conditions."
                ],
            }
        ],
        "proposed_actions": [
            {
                "action_id": "a1",
                "action_class": action_class,
                "description": "Run the next bounded research action.",
                "rationale": "It directly addresses the verified blocker.",
                "required_evidence": ["design_readiness"],
                "expected_outcome": "A result that discriminates the current hypothesis.",
                "execution_mode": execution_mode,
            }
        ],
        "known_limitations": [
            "A positive result would not by itself establish causality."
        ],
        "stop_condition": "Stop if the hypothesis is falsified or the design remains non-identifiable.",
    }


def test_reasoning_proposal_preserves_hypothesis_as_unupgraded() -> None:
    result = validate_reasoning_proposal(
        _proposal(
            action_class="computational_experiment",
            execution_mode="typed_local_action",
        ),
        _program_for_reasoning(),
    )

    assert result["proposal_status"] == "validated_for_planning_only"
    assert result["new_hypotheses"][0]["status"] == "proposed_not_evidence_upgraded"
    assert result["proposed_actions"][0]["automatic_execution_authorized"] is False
    assert result["autonomy_boundary"]["scientific_evidence_upgraded"] is False


def test_reasoning_proposal_rejects_unbound_evidence() -> None:
    proposal = _proposal(
        action_class="computational_experiment",
        execution_mode="typed_local_action",
    )
    proposal["evidence_bindings"][0]["sha256"] = "b" * 64  # type: ignore[index]
    with pytest.raises(ResearchProgramError, match="not bound by the verified program state"):
        validate_reasoning_proposal(proposal, _program_for_reasoning())


def test_network_search_requires_explicit_authorization() -> None:
    with pytest.raises(ResearchProgramError, match="must require explicit authorization"):
        validate_reasoning_proposal(
            _proposal(
                action_class="external_evidence_search",
                execution_mode="typed_local_action",
            ),
            _program_for_reasoning(),
        )


def test_physical_experiment_remains_plan_only() -> None:
    with pytest.raises(ResearchProgramError, match="plan-only"):
        validate_reasoning_proposal(
            _proposal(
                action_class="physical_experiment_design",
                execution_mode="explicit_authorization_required",
            ),
            _program_for_reasoning(),
        )
