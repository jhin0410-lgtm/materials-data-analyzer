import json
from pathlib import Path

import pytest

from src.platform_core.battery_trajectory_evaluator import (
    EVALUATOR_ID,
    CapacityTrajectoryEvaluatorConfig,
    CapacityTrajectoryInput,
    aggregate_results,
    assess_evaluator_trust,
    canonical_checksum,
    evaluate_capacity_trajectory,
    evaluation_decision,
    evaluator_contract,
    load_evaluator_config,
)


def _trajectory(
    capacities,
    *,
    cycles=None,
    cell_id="T1",
    units=None,
    reference=None,
    maturity="dimensionally_valid",
    lineage_valid=True,
    protocol_signatures=(),
):
    cycles = tuple(cycles or range(1, len(capacities) + 1))
    units = tuple(units or ["Ah"] * len(capacities))
    reference = reference if reference is not None else sorted(float(value) for value in capacities[:5])[2]
    return CapacityTrajectoryInput(
        trajectory_id=f"battery_trajectory_{cell_id}",
        cell_id=cell_id,
        cycle_indices=cycles,
        capacities=tuple(capacities),
        capacity_units=units,
        ordered_state_refs=tuple(f"battery_state_{cell_id}_{cycle:05d}" for cycle in cycles),
        reference_capacity_method="first_n_median",
        recorded_reference_capacity=reference,
        representation_maturity=maturity,
        lineage_valid=lineage_valid,
        protocol_signatures=tuple(protocol_signatures),
    )


def test_config_and_contract_fix_selected_evaluator_and_algorithmic_threshold_semantics():
    config = CapacityTrajectoryEvaluatorConfig()
    contract = evaluator_contract(config)

    assert contract["evaluator_id"] == EVALUATOR_ID
    assert contract["operator_role"] == "Evaluator"
    assert contract["threshold_policy"]["semantics"] == "algorithmic_detection_policy_not_measurement_uncertainty"
    assert contract["target_access_policy"] == "observed_capacity_only_no_predictive_target"
    assert contract["network_policy"] == "no_network"
    with pytest.raises(ValueError, match="only"):
        CapacityTrajectoryEvaluatorConfig(evaluator_id="arrhenius_fit")


def test_tracked_config_loads_and_absolute_or_changed_paths_are_rejected(tmp_path):
    config, _ = load_evaluator_config("configs/examples/battery_capacity_trajectory_evaluator.json")
    assert config.reference_capacity_policy == "source_recorded_first_n_median_window_5"

    payload = json.loads(Path("configs/examples/battery_capacity_trajectory_evaluator.json").read_text(encoding="utf-8"))
    payload["source_path"] = "C:/private/battery.csv"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="repository-relative"):
        load_evaluator_config(bad)


def test_reference_policy_is_deterministic_and_never_uses_post_hoc_maximum():
    trajectory = _trajectory([1.0, 1.1, 5.0, 1.2, 1.3, 1.4], reference=1.2)
    config = CapacityTrajectoryEvaluatorConfig(reference_capacity_policy="first_n_median_first_5")

    result = evaluate_capacity_trajectory(trajectory, config)

    assert result.reference_capacity == pytest.approx(1.2)
    assert result.reference_capacity != 5.0
    assert result.reference_cycle_index == 4
    assert result.reference_selection_evidence == "median_of_earliest_five_positive_discharge_capacities"


def test_eligibility_blocks_short_invalid_order_mixed_units_lineage_and_maturity():
    short = evaluate_capacity_trajectory(_trajectory([1.0, 0.9, 0.8, 0.7], reference=0.9))
    duplicate = evaluate_capacity_trajectory(_trajectory([1.0] * 5, cycles=[1, 2, 2, 3, 4], reference=1.0))
    mixed = evaluate_capacity_trajectory(_trajectory([1.0] * 5, units=["Ah", "Ah", "mAh", "Ah", "Ah"], reference=1.0))
    lineage = evaluate_capacity_trajectory(_trajectory([1.0] * 5, reference=1.0, lineage_valid=False))
    maturity = evaluate_capacity_trajectory(_trajectory([1.0] * 5, reference=1.0, maturity="semantically_mapped"))

    assert short.eligibility_status == "blocked_insufficient_capacity_data"
    assert duplicate.eligibility_status == "blocked_invalid_ordering"
    assert duplicate.finding_counts["duplicate_cycle_candidate"] == 1
    assert mixed.eligibility_status == "blocked_unit_inconsistency"
    assert lineage.eligibility_status == "blocked_lineage"
    assert maturity.eligibility_status == "blocked_lineage"


def test_negative_capacity_and_conflicting_recorded_reference_are_blocked():
    negative = evaluate_capacity_trajectory(_trajectory([1.0, 0.9, -0.1, 0.8, 0.7], reference=0.9))
    conflicting = evaluate_capacity_trajectory(
        _trajectory([1.0, 0.9, 0.8, 0.7, 0.6], reference=9.0),
        CapacityTrajectoryEvaluatorConfig(reference_capacity_policy="first_n_median_first_5"),
    )

    assert negative.eligibility_status == "blocked_insufficient_capacity_data"
    assert conflicting.eligibility_status == "blocked_reference_capacity"


def test_gap_is_recorded_but_not_treated_as_single_cycle_or_physical_time():
    result = evaluate_capacity_trajectory(
        _trajectory([1.0, 0.99, 0.7, 0.69, 0.68], cycles=[1, 2, 10, 11, 12], reference=0.99),
        CapacityTrajectoryEvaluatorConfig(absolute_detection_floor=0.02, robust_scale_multiplier=3.0),
    )

    gap = next(item for item in result.findings if item.finding_category == "missing_cycle_gap")
    assert gap.cycle_gap == 8
    assert "not interpreted as a physical-time gap" in gap.interpretation
    assert result.gap_aware_exclusion_count == 1
    assert all(
        item.start_cycle_index != 2 or item.end_cycle_index != 10
        for item in result.findings
        if item.finding_category.startswith("abrupt_capacity")
    )


def test_non_monotonic_abrupt_plateau_and_terminal_candidates_are_descriptive():
    config = CapacityTrajectoryEvaluatorConfig(
        absolute_detection_floor=0.03,
        robust_scale_multiplier=3.0,
        plateau_threshold=0.015,
        terminal_retention_boundary=0.8,
    )
    rebound = evaluate_capacity_trajectory(_trajectory([1.0, 0.99, 0.98, 1.08, 0.7, 0.69], reference=1.0), config)
    plateau = evaluate_capacity_trajectory(_trajectory([1.0, 1.001, 0.999, 1.0, 1.001, 0.95], reference=1.0), config)

    assert rebound.finding_counts["non_monotonic_increase_candidate"] >= 1
    assert rebound.finding_counts["abrupt_capacity_rise_candidate"] >= 1
    assert rebound.finding_counts["abrupt_capacity_drop_candidate"] >= 1
    assert rebound.finding_counts["terminal_low_retention_observation"] == 1
    assert plateau.finding_counts["plateau_candidate"] >= 1
    assert all("mechanism" not in item.finding_status for item in rebound.findings)


def test_accelerated_and_decelerated_candidates_use_fixed_windows_not_learning():
    config = CapacityTrajectoryEvaluatorConfig(
        absolute_detection_floor=0.001,
        robust_scale_multiplier=2.0,
        accelerated_fade_threshold=0.004,
        window_size=3,
        minimum_window_support=3,
    )
    accelerated = _trajectory([1.0, 0.999, 0.998, 0.997, 0.98, 0.96, 0.94, 0.92], reference=1.0)
    decelerated = _trajectory([1.0, 0.98, 0.96, 0.94, 0.939, 0.938, 0.937, 0.936], reference=1.0)

    accelerated_result = evaluate_capacity_trajectory(accelerated, config)
    decelerated_result = evaluate_capacity_trajectory(decelerated, config)

    assert accelerated_result.finding_counts["accelerated_fade_candidate"] >= 1
    assert decelerated_result.finding_counts["decelerated_fade_candidate"] >= 1
    assert "learned" not in json.dumps(accelerated_result.to_dict(include_findings=True)).lower()


def test_zero_mad_uses_absolute_floor_and_same_input_is_deterministic():
    trajectory = _trajectory([1.0, 0.99, 0.98, 0.97, 0.96, 0.95], reference=1.0)
    config = CapacityTrajectoryEvaluatorConfig(absolute_detection_floor=0.01, robust_scale_multiplier=8.0)

    first = evaluate_capacity_trajectory(trajectory, config)
    second = evaluate_capacity_trajectory(trajectory, config)

    assert first.robust_difference_scale == pytest.approx(0.0, abs=1e-12)
    assert first.event_threshold == pytest.approx(0.01)
    assert canonical_checksum(first.to_dict(include_findings=True)) == canonical_checksum(second.to_dict(include_findings=True))


def test_aggregate_trust_and_decision_never_promote_mechanism_or_prediction():
    result = evaluate_capacity_trajectory(_trajectory([1.0, 0.99, 0.98, 0.97, 0.96], reference=1.0))
    aggregate = aggregate_results([result])
    trust = assess_evaluator_trust(aggregate, deterministic_rerun_match=True)
    decision = evaluation_decision(aggregate, deterministic_rerun_match=True).to_dict()

    assert any(item.status == "execution_valid_but_interpretation_restricted" for item in trust)
    assert decision["status"] == "descriptive_evaluator_executed_with_restrictions"
    assert decision["representative_mechanism"] == "none"
    assert decision["degradation_mechanism_identified"] is False
    assert decision["predictive_model_validated"] is False
    assert decision["physical_parameter_estimated"] is False


def test_module_contains_no_network_solver_training_or_dynamic_execution_imports():
    text = Path("src/platform_core/battery_trajectory_evaluator.py").read_text(encoding="utf-8")

    assert "import requests" not in text
    assert "import urllib" not in text
    assert "import socket" not in text
    assert "import subprocess" not in text
    assert "import importlib" not in text
    assert "eval(" not in text
    assert "exec(" not in text
    assert ".fit(" not in text
    assert ".predict(" not in text
