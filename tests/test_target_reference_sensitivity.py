from __future__ import annotations

import pandas as pd
import pytest

from materials_data_analyzer.research_loop import (
    TargetReferenceSensitivityError,
    build_target_reference_sensitivity,
)


def _frames(
    *,
    capacities: dict[str, float],
    persistence_errors_ah: dict[str, float],
    ridge_errors_ah: dict[str, float],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cycle_rows: list[dict[str, float | int | str]] = []
    prediction_rows: list[dict[str, float | int | str]] = []
    declared_reference = 2.0
    for battery_id, capacity in capacities.items():
        actual_percent = 100.0 * capacity / declared_reference
        for cycle in range(1, 7):
            cycle_rows.append(
                {
                    "battery_id": battery_id,
                    "cycle_index": cycle,
                    "reference_capacity_ah": declared_reference,
                    "discharge_capacity_ah": capacity,
                    "capacity_retention_percent": actual_percent,
                }
            )
        for origin_cycle, target_cycle in ((3, 4), (4, 5), (5, 6)):
            prediction_rows.append(
                {
                    "battery_id": battery_id,
                    "origin_cycle": origin_cycle,
                    "target_cycle": target_cycle,
                    "actual": actual_percent,
                    "persistence_prediction": actual_percent
                    + 100.0 * persistence_errors_ah[battery_id] / declared_reference,
                    "ridge_prediction": actual_percent
                    + 100.0 * ridge_errors_ah[battery_id] / declared_reference,
                }
            )
    return pd.DataFrame(cycle_rows), pd.DataFrame(prediction_rows)


def test_conclusion_is_stable_when_persistence_is_better_for_every_battery() -> None:
    cycles, predictions = _frames(
        capacities={"A": 1.0, "B": 4.0},
        persistence_errors_ah={"A": 0.1, "B": 0.1},
        ridge_errors_ah={"A": 0.2, "B": 0.2},
    )

    result = build_target_reference_sensitivity(
        cycle_summary=cycles,
        predictions=predictions,
        config={"group_column": "battery_id", "cycle_column": "cycle_index"},
    )

    summary = result["summary"]
    assert summary["outcome"] == "conclusion_stable_across_defensible_targets"
    assert {item["preferred_model"] for item in summary["ridge_vs_persistence"]} == {
        "persistence"
    }
    assert len(summary["ridge_vs_persistence"]) == 3
    assert summary["prediction_count"] == len(predictions)
    assert summary["source_rows_removed"] is False
    assert summary["model_refit_performed"] is False
    assert summary["alternative_references_bounded_by_earliest_forecast_origin"]
    assert (
        summary["future_target_observations_used_to_define_alternative_references"]
        is False
    )
    assert set(result["model_metrics_by_reference"]["prediction_count"]) == {
        len(predictions)
    }


def test_conclusion_sensitivity_detects_reference_weighting_sign_flip() -> None:
    cycles, predictions = _frames(
        capacities={"A": 4.0, "B": 1.0},
        persistence_errors_ah={"A": 0.1, "B": 0.3},
        ridge_errors_ah={"A": 0.4, "B": 0.1},
    )

    result = build_target_reference_sensitivity(
        cycle_summary=cycles,
        predictions=predictions,
        config={"group_column": "battery_id", "cycle_column": "cycle_index"},
    )

    summary = result["summary"]
    assert summary["outcome"] == "conclusion_sensitive_to_target_reference"
    preferred = {
        item["reference_id"]: item["preferred_model"]
        for item in summary["ridge_vs_persistence"]
    }
    assert preferred["declared_reference"] == "persistence"
    assert preferred["preforecast_window_median_capacity"] == "ridge"
    assert preferred["preforecast_window_maximum_capacity"] == "ridge"
    assert summary["primary_reference_id"] == "declared_reference"


def test_missing_preforecast_reference_is_explicitly_inconclusive() -> None:
    cycles, predictions = _frames(
        capacities={"A": 2.0, "B": 2.0},
        persistence_errors_ah={"A": 0.1, "B": 0.1},
        ridge_errors_ah={"A": 0.2, "B": 0.2},
    )
    cycles = cycles[
        ~(
            (cycles["battery_id"] == "B")
            & (cycles["cycle_index"] == 3)
        )
    ]

    result = build_target_reference_sensitivity(
        cycle_summary=cycles,
        predictions=predictions,
        config={"group_column": "battery_id", "cycle_column": "cycle_index"},
    )

    assert result["summary"]["outcome"] == "required_reference_metadata_missing"
    schemes = {
        item["reference_id"]: item for item in result["summary"]["schemes"]
    }
    scheme = schemes["preforecast_window_median_capacity"]
    assert scheme["complete"] is False
    assert scheme["incomplete_battery_count"] == 1
    assert (
        "fewer_than_three_valid_preforecast_window_observations"
        in scheme["incomplete_reasons"]
    )


def test_existing_actual_must_reconstruct_from_declared_reference() -> None:
    cycles, predictions = _frames(
        capacities={"A": 2.0},
        persistence_errors_ah={"A": 0.1},
        ridge_errors_ah={"A": 0.2},
    )
    predictions.loc[0, "actual"] += 1.0

    with pytest.raises(
        TargetReferenceSensitivityError,
        match="actual target is not reproducible",
    ):
        build_target_reference_sensitivity(
            cycle_summary=cycles,
            predictions=predictions,
            config={"group_column": "battery_id", "cycle_column": "cycle_index"},
        )


def test_duplicate_prediction_target_is_rejected() -> None:
    cycles, predictions = _frames(
        capacities={"A": 2.0},
        persistence_errors_ah={"A": 0.1},
        ridge_errors_ah={"A": 0.2},
    )
    predictions = pd.concat([predictions, predictions.iloc[[0]]], ignore_index=True)

    with pytest.raises(TargetReferenceSensitivityError, match="duplicate"):
        build_target_reference_sensitivity(
            cycle_summary=cycles,
            predictions=predictions,
            config={"group_column": "battery_id", "cycle_column": "cycle_index"},
        )


def test_target_cycle_must_follow_origin_cycle() -> None:
    cycles, predictions = _frames(
        capacities={"A": 2.0},
        persistence_errors_ah={"A": 0.1},
        ridge_errors_ah={"A": 0.2},
    )
    predictions.loc[0, "target_cycle"] = predictions.loc[0, "origin_cycle"]

    with pytest.raises(TargetReferenceSensitivityError, match="later than its origin"):
        build_target_reference_sensitivity(
            cycle_summary=cycles,
            predictions=predictions,
            config={"group_column": "battery_id", "cycle_column": "cycle_index"},
        )
