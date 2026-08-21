from __future__ import annotations

import pytest

import materials_data_analyzer.research_loop.recursive_research_cycle_evidence as evidence
from materials_data_analyzer.research_loop.kernel import ResearchLoopError
from materials_data_analyzer.research_loop.recursive_research_cycle_evidence import (
    RecursiveResearchEvidenceError,
)


def test_public_progression_threads_expected_recursive_limits_into_planning_validation(
    monkeypatch,
) -> None:
    limits = {
        "max_cycles": 3,
        "max_action_slots": 2,
        "max_planned_cost_units": 5.0,
    }
    captured: dict[str, object] = {}

    def stop_after_capture(*args, **kwargs):
        captured.update(kwargs)
        raise ResearchLoopError("sentinel after validation-input capture")

    monkeypatch.setattr(
        evidence,
        "validate_validated_recursive_planning_checkpoint",
        stop_after_capture,
    )

    with pytest.raises(
        RecursiveResearchEvidenceError,
        match="exact validated planning artifact",
    ):
        evidence.advance_recursive_cycle_after_verified_transition(
            validated_planning_artifact={},
            planning_handoff={},
            source_discrepancy_report={},
            source_evaluated_graph={},
            fresh_plan={},
            planner_program_state={},
            recursive_limits=limits,
            execution_adapter_id="unused",
            repository_root="unused",
            research_run="unused",
            action_registry_path="unused",
            request_path="unused",
            action_report_path="unused",
            transition_bundle_root="unused",
            program_state={},
        )

    assert captured["recursive_limits"] == limits
