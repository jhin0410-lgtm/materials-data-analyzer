from __future__ import annotations

import pytest

from materials_data_analyzer.research_loop.autonomous_decision_integration import (
    AutonomousDecisionIntegrationError,
    build_autonomous_decision_report,
)
from materials_data_analyzer.research_loop.experimental_lineage import ObservationLineage


def _action(action_id: str, *, execution_mode: str = "plan_only", utility: float = 0.5) -> dict:
    return {
        "action_id": action_id,
        "action_class": "sensitivity_analysis",
        "execution_mode": execution_mode,
        "cost_units": 1.0,
        "utility_score": utility,
        "physical_experiment_execution_authorized": False,
    }


def _plan() -> dict:
    first = _action("a:first", execution_mode="typed_local_action", utility=0.8)
    second = _action("a:second", execution_mode="explicit_authorization_required", utility=0.6)
    return {
        "planning_budget": {"budget_units": 4.0, "minimum_utility": 0.01},
        "ranked_actions": [first, second],
        "selected_next_action": first,
        "stop_decision": {"stop": False, "reason": "informative_action_available"},
    }


def _benchmark(*, passed: bool = True, critical: int = 0) -> dict:
    return {
        "benchmark_passed": passed,
        "critical_failure_count": critical,
        "scenario_count": 3,
    }


def _eig(value: float, digest: str = "a" * 64) -> dict:
    return {
        "mode": "probabilistic_eig",
        "model_artifact_sha256": digest,
        "eig_per_cost_unit": value,
    }


def test_preserves_planner_selection_without_true_eig() -> None:
    report = build_autonomous_decision_report(
        _plan(),
        eig_results={"a:second": {"mode": "structural_proxy_only"}},
        benchmark_summary=_benchmark(),
    )
    assert report["selected_action"]["action_id"] == "a:first"
    assert report["selection_reason"] == "upstream_planner_order_preserved"
    assert report["ignored_eig_results"] == {
        "a:second": "structural_proxy_cannot_reorder_actions"
    }
    assert report["execution_handoff"]["authorization_granted_here"] is False
    assert report["scientific_status_changed"] is False


def test_true_sha_bound_probabilistic_eig_can_reorder_only_eligible_frontier() -> None:
    report = build_autonomous_decision_report(
        _plan(),
        eig_results={"a:first": _eig(0.2), "a:second": _eig(0.9, "b" * 64)},
        benchmark_summary=_benchmark(),
    )
    assert report["selected_action"]["action_id"] == "a:second"
    assert report["selection_reason"].startswith("validated_probabilistic_eig")
    assert report["planner_frontier_expanded"] is False
    assert report["execution_handoff"][
        "eligible_to_request_existing_authorization_chain"
    ] is True
    assert report["execution_handoff"]["execution_performed_here"] is False


def test_eig_cannot_inject_action_outside_planner_frontier() -> None:
    with pytest.raises(AutonomousDecisionIntegrationError, match="non-eligible"):
        build_autonomous_decision_report(
            _plan(),
            eig_results={"attacker:new-action": _eig(1.0)},
        )


def test_benchmark_failure_blocks_automatic_handoff_but_not_planning() -> None:
    report = build_autonomous_decision_report(
        _plan(),
        benchmark_summary=_benchmark(passed=False, critical=1),
    )
    assert report["selected_action"]["action_id"] == "a:first"
    assert report["benchmark_qualified_for_automatic_handoff"] is False
    assert report["execution_handoff"][
        "eligible_to_request_existing_authorization_chain"
    ] is False


def test_inconsistent_benchmark_fails_closed() -> None:
    with pytest.raises(AutonomousDecisionIntegrationError, match="critical failures"):
        build_autonomous_decision_report(
            _plan(),
            benchmark_summary=_benchmark(passed=True, critical=1),
        )


def test_lineage_statistics_are_reported_without_row_independence_inference() -> None:
    lineages = [
        ObservationLineage(
            source_id="source-a",
            lab_id="lab-a",
            material_lot_id="lot-a",
            build_or_synthesis_id="build-a",
            specimen_id="specimen-a",
            process_run_id="run-a",
            acquisition_id="acq-a",
            measurement_id="measurement-1",
        ),
        ObservationLineage(
            source_id="source-a",
            lab_id="lab-a",
            material_lot_id="lot-a",
            build_or_synthesis_id="build-a",
            specimen_id="specimen-a",
            process_run_id="run-a",
            acquisition_id="acq-a",
            measurement_id="measurement-2",
        ),
    ]
    report = build_autonomous_decision_report(
        _plan(),
        lineages=lineages,
        fixed_effects_declared=True,
        repeated_measurements_expected=True,
    )
    stats = report["advanced_statistics_eligibility"]
    assert stats["physical_counts"]["row_count"] == 2
    assert stats["physical_counts"]["unique_specimens"] == 1
    assert stats["naive_independent_row_model_eligible"] is False
    assert stats["row_count_used_as_independence_without_lineage"] is False


def test_stop_decision_cannot_be_overridden_by_eig() -> None:
    plan = _plan()
    plan["stop_decision"] = {"stop": True, "reason": "mission_scope_exhausted"}
    plan["selected_next_action"] = None
    report = build_autonomous_decision_report(
        plan,
        eig_results={"a:first": _eig(10.0)},
        benchmark_summary=_benchmark(),
    )
    assert report["selected_action"] is None
    assert report["selection_reason"] == "upstream_stop_decision"
    assert report["execution_handoff"][
        "eligible_to_request_existing_authorization_chain"
    ] is False
