from __future__ import annotations

import pytest

from materials_data_analyzer.research_loop.epistemic_control import (
    EpistemicControlError,
    derive_epistemic_directive,
)


def _evaluation(*statuses: tuple[str, str]) -> dict[str, object]:
    return {
        "graph_id": "graph-v1",
        "assessments": [
            {
                "node_id": node_id,
                "node_type": "hypothesis",
                "status": status,
                "verified_support_edges": [],
                "verified_contradiction_edges": [],
                "verified_falsification_edges": [],
                "diagnostic_relation_edges": [],
                "final_positive_support_granted": False,
                "domain_closeout_required_for_positive_conclusion": status
                == "provisionally_supported",
                "confidence_score": None,
            }
            for node_id, status in statuses
        ],
    }


def test_inconclusive_targets_allow_only_bounded_discriminating_research() -> None:
    result = derive_epistemic_directive(
        _evaluation(("h1", "inconclusive")), target_node_ids=["h1"]
    )
    assert result["directive"] == "continue_discriminating_research"
    assert result["automatic_execution_permitted"] is True
    assert result["autonomy_boundary"]["numeric_confidence_invented"] is False


def test_verified_falsification_dominates_and_stops_repetition() -> None:
    result = derive_epistemic_directive(
        _evaluation(
            ("h1", "inconclusive"),
            ("h2", "falsified_within_verified_scope"),
        ),
        target_node_ids=["h1", "h2"],
    )
    assert result["directive"] == "stop_falsified_target"
    assert result["automatic_execution_permitted"] is False


def test_verified_conflict_or_contradiction_requires_discrimination() -> None:
    contested = derive_epistemic_directive(
        _evaluation(("h1", "contested")), target_node_ids=["h1"]
    )
    contradicted = derive_epistemic_directive(
        _evaluation(("h1", "contradicted_within_verified_scope")),
        target_node_ids=["h1"],
    )
    assert contested["directive"] == "manual_discrimination_required"
    assert contradicted["directive"] == "manual_discrimination_required"
    assert contested["automatic_execution_permitted"] is False
    assert contradicted["automatic_execution_permitted"] is False


def test_positive_support_routes_to_domain_closeout_not_more_confirmation() -> None:
    result = derive_epistemic_directive(
        _evaluation(("claim", "provisionally_supported")),
        target_node_ids=["claim"],
    )
    assert result["directive"] == "domain_closeout_required"
    assert result["automatic_execution_permitted"] is False
    assert result["autonomy_boundary"]["positive_support_grants_final_truth"] is False


def test_missing_or_duplicate_target_is_rejected_fail_closed() -> None:
    evaluation = _evaluation(("h1", "inconclusive"))
    with pytest.raises(EpistemicControlError, match="missing"):
        derive_epistemic_directive(evaluation, target_node_ids=["missing"])
    with pytest.raises(EpistemicControlError, match="duplicate"):
        derive_epistemic_directive(evaluation, target_node_ids=["h1", "h1"])


def test_unknown_epistemic_status_is_rejected() -> None:
    with pytest.raises(EpistemicControlError, match="unsupported epistemic status"):
        derive_epistemic_directive(
            _evaluation(("h1", "scientifically_true")), target_node_ids=["h1"]
        )
