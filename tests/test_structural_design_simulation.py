from __future__ import annotations

import json
import runpy
from pathlib import Path

import pandas as pd
import pytest

from materials_data_analyzer.research_loop.design_simulation import (
    DesignSimulationError,
    simulate_design_structure,
    simulate_design_structure_file,
    validate_design_simulation_config,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/research/nist_ambench_stage1_structural_design_simulation.v1.json"


def _tracked_config() -> dict[str, object]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _model_changes(result: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        item["model"]: item
        for item in result["comparison"]["model_changes"]
    }


def test_nist_stage1_completes_grid_and_identifies_interaction_structure() -> None:
    result = simulate_design_structure_file(CONFIG)

    before = result["before"]["grid"]
    after = result["after_proposal"]["grid"]
    assert before["total_replicates"] == 10
    assert before["unique_cell_count"] == 3
    assert before["possible_observed_level_cell_count"] == 6
    assert before["observed_level_grid_complete"] is False
    assert before["missing_observed_level_cells"] == [
        {"actual_laser_power_w": 137.9, "scan_speed_mm_s": 800.0},
        {"actual_laser_power_w": 137.9, "scan_speed_mm_s": 1200.0},
        {"actual_laser_power_w": 179.2, "scan_speed_mm_s": 400.0},
    ]

    assert after["total_replicates"] == 19
    assert after["unique_cell_count"] == 6
    assert after["observed_level_grid_complete"] is True
    assert after["missing_observed_level_cells"] == []

    changes = _model_changes(result)
    interaction = changes["interaction"]
    assert interaction == {
        "model": "interaction",
        "rank_before": 3,
        "rank_after": 4,
        "rank_gain": 1,
        "residual_df_before": 7,
        "residual_df_after": 15,
        "residual_df_gain": 8,
        "full_column_rank_before": False,
        "full_column_rank_after": True,
    }


def test_stage1_does_not_overclaim_quadratic_readiness() -> None:
    result = simulate_design_structure_file(CONFIG)
    changes = _model_changes(result)

    quadratic = changes["quadratic"]
    assert quadratic["rank_before"] == 3
    assert quadratic["rank_after"] == 5
    assert quadratic["rank_gain"] == 2
    assert quadratic["full_column_rank_before"] is False
    assert quadratic["full_column_rank_after"] is False
    assert quadratic["residual_df_after"] == 14

    # Two power levels cannot identify a distinct quadratic power term even after
    # the 2 x 3 factorial grid is completed.
    assert result["after_proposal"]["grid"]["factor_levels"]["actual_laser_power_w"] == [
        137.9,
        179.2,
    ]


def test_main_effects_are_already_structurally_full_rank_before_stage1() -> None:
    result = simulate_design_structure_file(CONFIG)
    changes = _model_changes(result)
    main = changes["main_effects"]

    assert main["rank_before"] == 3
    assert main["rank_after"] == 3
    assert main["rank_gain"] == 0
    assert main["full_column_rank_before"] is True
    assert main["full_column_rank_after"] is True
    assert main["residual_df_before"] == 7
    assert main["residual_df_after"] == 16


def test_simulation_never_generates_response_or_information_gain_claims() -> None:
    result = simulate_design_structure_file(CONFIG)

    assert result["expected_information_gain"] == {
        "status": "not_quantified",
        "value": None,
        "reason": (
            "Rank gain and residual degrees of freedom describe design structure; "
            "they are not a probabilistic expected-information-gain estimate."
        ),
    }
    assert result["scientific_boundary"] == {
        "response_values_allowed": False,
        "coefficient_estimation_allowed": False,
        "effect_size_estimation_allowed": False,
        "predictive_modeling_allowed": False,
        "causal_inference_allowed": False,
        "optimization_allowed": False,
        "engineering_decision_allowed": False,
        "response_values_used": False,
        "synthetic_response_generated": False,
        "coefficients_estimated": False,
        "effect_sizes_estimated": False,
        "predictions_generated": False,
        "causal_effects_inferred": False,
        "optimization_performed": False,
        "engineering_decision_made": False,
    }


def test_unknown_response_field_is_rejected_instead_of_ignored() -> None:
    config = _tracked_config()
    config["response_values"] = [1.0, 2.0]

    with pytest.raises(DesignSimulationError, match="unknown keys"):
        validate_design_simulation_config(config)


def test_boolean_factor_value_is_rejected_before_numeric_coercion() -> None:
    config = _tracked_config()
    config["observed_cells"][0]["factor_values"]["actual_laser_power_w"] = True

    with pytest.raises(DesignSimulationError, match="finite numeric value"):
        validate_design_simulation_config(config)


def test_replication_only_proposal_increases_residual_df_not_rank() -> None:
    config = _tracked_config()
    config["proposed_cells"] = [
        {
            "cell_id": "repeat-A",
            "factor_values": {
                "actual_laser_power_w": 137.9,
                "scan_speed_mm_s": 400.0,
            },
            "replicates": 2,
        }
    ]
    result = simulate_design_structure(config)
    changes = _model_changes(result)

    assert result["comparison"]["new_unique_cell_count"] == 0
    assert result["comparison"]["replication_only_cell_count"] == 1
    assert changes["interaction"]["rank_gain"] == 0
    assert changes["interaction"]["residual_df_gain"] == 2


def test_tracked_config_matches_frozen_nist_case_contract_and_stage1_plan() -> None:
    config = validate_design_simulation_config(_tracked_config())
    case_module = runpy.run_path(
        str(ROOT / "scripts/build_nist_ambench_2018_02_case_study.py")
    )
    expected_cases = case_module["EXPECTED_CASES"]

    observed = {
        cell["cell_id"]: (
            cell["factor_values"]["actual_laser_power_w"],
            cell["factor_values"]["scan_speed_mm_s"],
            cell["replicates"],
        )
        for cell in config["observed_cells"]
    }
    assert observed == {
        case_id: (
            float(expected_cases[case_id]["power"]),
            float(expected_cases[case_id]["speed"]),
            int(expected_cases[case_id]["count"]),
        )
        for case_id in ("A", "B", "C")
    }

    # Bind the proposed cells to the planner's real, current output rather than
    # duplicating an imaginary constant. This makes the regression fail closed if
    # the source table or augmentation planner changes independently.
    plan_module = runpy.run_path(
        str(ROOT / "scripts/plan_nist_ambench_2018_02_design_augmentation.py")
    )
    source_process = pd.read_csv(case_module["PROCESS_SOURCE"])
    recommendations, _ = plan_module["build_augmentation_plan"](source_process)
    stage1 = recommendations.loc[
        recommendations["stage"] == "stage_1_complete_observed_grid"
    ]

    proposed = {
        (
            cell["factor_values"]["actual_laser_power_w"],
            cell["factor_values"]["scan_speed_mm_s"],
            cell["replicates"],
        )
        for cell in config["proposed_cells"]
    }
    expected_stage1 = {
        (
            float(row["actual_laser_power_w"]),
            float(row["scan_speed_mm_s"]),
            int(row["minimum_trace_replicates"]),
        )
        for _, row in stage1.iterrows()
    }
    assert proposed == expected_stage1
