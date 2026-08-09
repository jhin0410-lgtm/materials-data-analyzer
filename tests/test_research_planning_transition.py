from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import materials_data_analyzer.research_loop.planning_transition as transition


ROOT = Path(__file__).resolve().parents[1]


def _state(
    stop_status: str,
    *,
    selection_status: str = "ready_to_execute",
    selected_action: object = None,
    evidence_gap_status: str = "action_expected_to_reduce_uncertainty",
    reopen_conditions: list[str] | None = None,
) -> dict[str, object]:
    return {
        "adapter_id": "test-adapter",
        "domain": "test-domain",
        "selected_action": selected_action,
        "evidence_gap": {
            "status": evidence_gap_status,
            "requirements": [],
        },
        "stop_state": {
            "status": stop_status,
            "selection_status": selection_status,
            "reason": "test reason",
            "reopen_conditions": reopen_conditions or [],
        },
        "evidence_bindings": [
            {
                "role": "test-planning-evidence",
                "path": "evidence.json",
                "sha256": "a" * 64,
            }
        ],
    }


def test_ready_action_is_pending_authorization_not_executed() -> None:
    result = transition.determine_research_transition(
        _state(
            "continue",
            selected_action={"action_type": "protocol_stratification"},
        )
    )

    assert result["transition_type"] == "action_pending_authorization"
    assert result["automatic_execution_authorized"] is False
    assert result["action_executed"] is False
    assert result["scientific_evidence_upgraded"] is False


def test_transition_preserves_planning_evidence_bindings() -> None:
    state = _state(
        "continue",
        selected_action={"action_type": "protocol_stratification"},
    )

    result = transition.determine_research_transition(state)

    assert result["planning_evidence_bindings"] == state["evidence_bindings"]
    assert result["planning_evidence_bindings"] is not state["evidence_bindings"]


def test_external_evidence_requirement_has_separate_transition() -> None:
    result = transition.determine_research_transition(
        _state(
            "continue",
            selected_action={"action_type": "external_data_requirement_generation"},
            evidence_gap_status="requirement_definition_needed",
        )
    )

    assert result["transition_type"] == "evidence_requirement_pending_authorization"
    assert result["automatic_execution_authorized"] is False


def test_active_state_without_bounded_action_fails_to_manual_review() -> None:
    result = transition.determine_research_transition(_state("continue"))

    assert result["transition_type"] == "manual_review_required"
    assert "no valid bounded selected action" in result["reason"]


@pytest.mark.parametrize(
    "selected_action",
    [{}, {"action_type": ""}, {"action_type": None}],
)
def test_active_state_with_malformed_action_fails_to_manual_review(
    selected_action: object,
) -> None:
    result = transition.determine_research_transition(
        _state("continue", selected_action=selected_action)
    )

    assert result["transition_type"] == "manual_review_required"
    assert result["selected_action"] is None
    assert result["automatic_execution_authorized"] is False


@pytest.mark.parametrize(
    ("stop_status", "expected"),
    [
        ("manual_review_gate", "manual_review_required"),
        ("operationally_blocked", "blocked"),
        ("terminal_for_current_scope", "stop_current_scope"),
    ],
)
def test_noncontinuation_states_map_fail_closed(stop_status: str, expected: str) -> None:
    result = transition.determine_research_transition(
        _state(
            stop_status,
            selection_status="no_positive_value_action",
            selected_action={"action_type": "must_not_execute"},
        )
    )

    assert result["transition_type"] == expected
    assert result["automatic_execution_authorized"] is False
    assert result["automatic_reopen_authorized"] is False
    if stop_status == "terminal_for_current_scope":
        assert result["selected_action"] is None


def test_current_materials_project_transition_is_stop_current_scope() -> None:
    result = transition.build_current_research_transition(
        "materials-project-external-source",
        repository_root=ROOT,
    )

    assert result["transition_type"] == "stop_current_scope"
    assert result["planning_evidence_bindings"]
    assert result["automatic_reopen_authorized"] is False
    assert result["network_access_performed"] is False


def test_current_tm_fe_si_transition_is_stop_current_scope() -> None:
    result = transition.build_current_research_transition(
        "tm-fe-si-descriptive",
        repository_root=ROOT,
    )

    assert result["transition_type"] == "stop_current_scope"
    assert result["planning_evidence_bindings"]
    assert result["automatic_execution_authorized"] is False


def test_reopen_evidence_is_checksum_bound_but_not_semantically_accepted(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "candidate-evidence.txt"
    evidence.write_text("new authoritative evidence candidate\n", encoding="utf-8")
    state = _state(
        "terminal_for_current_scope",
        selection_status="no_positive_value_action",
        reopen_conditions=["A new source directly resolves the frozen semantic blocker."],
    )

    result = transition.prepare_reopen_evidence_review(
        state,
        condition_index=0,
        evidence_path=evidence,
    )

    evidence_bytes = evidence.read_bytes()
    assert result["review_status"] == "manual_semantic_review_required"
    assert result["requested_transition"] == "reopen_current_scope"
    assert result["next_transition"] == "manual_review_required"
    assert result["planning_evidence_bindings"] == state["evidence_bindings"]
    assert result["evidence_binding"]["sha256"] == hashlib.sha256(
        evidence_bytes
    ).hexdigest()
    assert result["evidence_binding"]["size_bytes"] == len(evidence_bytes)
    assert isinstance(result["evidence_binding"]["mtime_ns"], int)
    assert result["condition_satisfaction_established"] is False
    assert result["scientific_comparability_established"] is False
    assert result["automatic_reopen_authorized"] is False
    assert result["automatic_execution_authorized"] is False
    assert result["scientific_evidence_upgraded"] is False


def test_transition_allows_absent_legacy_planning_evidence_bindings() -> None:
    state = _state(
        "continue",
        selected_action={"action_type": "protocol_stratification"},
    )
    state.pop("evidence_bindings")

    result = transition.determine_research_transition(state)

    assert result["planning_evidence_bindings"] == []
    assert result["transition_type"] == "action_pending_authorization"


def test_transition_rejects_malformed_planning_evidence_bindings() -> None:
    state = _state(
        "continue",
        selected_action={"action_type": "protocol_stratification"},
    )
    state["evidence_bindings"] = "not-a-list"

    with pytest.raises(transition.PlanningTransitionError, match="evidence_bindings"):
        transition.determine_research_transition(state)


def test_reopen_review_rejects_nonterminal_state(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("evidence", encoding="utf-8")

    with pytest.raises(transition.PlanningTransitionError, match="only valid"):
        transition.prepare_reopen_evidence_review(
            _state("continue", reopen_conditions=["condition"]),
            condition_index=0,
            evidence_path=evidence,
        )


def test_reopen_review_rejects_unknown_condition_index(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("evidence", encoding="utf-8")

    with pytest.raises(transition.PlanningTransitionError, match="out of range"):
        transition.prepare_reopen_evidence_review(
            _state(
                "terminal_for_current_scope",
                selection_status="no_positive_value_action",
                reopen_conditions=["condition"],
            ),
            condition_index=1,
            evidence_path=evidence,
        )


def test_reopen_review_rejects_empty_evidence_file(tmp_path: Path) -> None:
    evidence = tmp_path / "empty.txt"
    evidence.write_bytes(b"")

    with pytest.raises(transition.PlanningTransitionError, match="must not be empty"):
        transition.prepare_reopen_evidence_review(
            _state(
                "terminal_for_current_scope",
                selection_status="no_positive_value_action",
                reopen_conditions=["condition"],
            ),
            condition_index=0,
            evidence_path=evidence,
        )