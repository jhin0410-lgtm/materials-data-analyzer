from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from materials_data_analyzer.battery_target_sensitivity_cli import (
    main,
    run_target_sensitivity,
)
from platform_core.battery_intelligence import build_target_reference_sensitivity


def _frames(*, ridge_better_in_absolute: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    cycle_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    references = {"B1": 2.0, "B2": 1.0}
    for battery_id, reference in references.items():
        for cycle in range(1, 5):
            retention = 101.0 - cycle
            cycle_rows.append(
                {
                    "battery_id": battery_id,
                    "cycle_index": cycle,
                    "capacity_retention_percent": retention,
                    "reference_capacity_ah": reference,
                    "discharge_capacity_ah": retention * reference / 100.0,
                }
            )
        for target_cycle in (3, 4):
            actual = 101.0 - target_cycle
            persistence_error = 1.0
            ridge_error = 2.0
            if ridge_better_in_absolute and battery_id == "B1":
                persistence_error = 3.0
                ridge_error = 0.5
            if ridge_better_in_absolute and battery_id == "B2":
                persistence_error = 0.1
                ridge_error = 2.0
            prediction_rows.append(
                {
                    "battery_id": battery_id,
                    "origin_cycle": target_cycle - 2,
                    "target_cycle": target_cycle,
                    "actual": actual,
                    "persistence_prediction": actual + persistence_error,
                    "ridge_prediction": actual + ridge_error,
                    "trailing_mean_prediction": actual + 1.5,
                }
            )
    return pd.DataFrame(cycle_rows), pd.DataFrame(prediction_rows)


def test_stable_conclusion_reuses_fixed_predictions_without_refit() -> None:
    cycles, predictions = _frames()
    original_cycles = cycles.copy(deep=True)
    original_predictions = predictions.copy(deep=True)

    result = build_target_reference_sensitivity(
        cycle_summary=cycles,
        predictions=predictions,
        group_column="battery_id",
    )

    summary = result["summary"]
    assert summary["outcome"] == "conclusion_stable_across_defensible_targets"
    assert summary["primary_conclusion_stable"] is True
    assert summary["primary_comparison"][
        "ridge_beats_persistence_battery_macro"
    ] is False
    assert summary["alternative_comparison"][
        "ridge_beats_persistence_battery_macro"
    ] is False
    assert set(result["model_comparison"]["target_definition"]) == {
        "rated_capacity_retention_percent",
        "absolute_discharge_capacity_ah",
    }
    assert len(result["per_battery_comparison"]) == 12
    pd.testing.assert_frame_equal(cycles, original_cycles)
    pd.testing.assert_frame_equal(predictions, original_predictions)


def test_capacity_scale_can_change_pooled_conclusion_and_is_reported() -> None:
    cycles, predictions = _frames(ridge_better_in_absolute=True)

    result = build_target_reference_sensitivity(
        cycle_summary=cycles,
        predictions=predictions,
        group_column="battery_id",
    )

    summary = result["summary"]
    assert summary["outcome"] == "conclusion_sensitive_to_target_reference"
    assert summary["primary_comparison"][
        "ridge_beats_persistence_row_weighted"
    ] is False
    assert summary["alternative_comparison"][
        "ridge_beats_persistence_row_weighted"
    ] is True
    alternative = result["model_comparison"].query(
        "target_definition == 'absolute_discharge_capacity_ah'"
    )
    assert set(alternative["pooled_comparability"]) == {
        "diagnostic_only_capacity_scale_dependent"
    }


def test_missing_or_invalid_reference_remains_explicitly_inconclusive() -> None:
    cycles, predictions = _frames()
    cycles.loc[0, "reference_capacity_ah"] = float("nan")

    result = build_target_reference_sensitivity(
        cycle_summary=cycles,
        predictions=predictions,
        group_column="battery_id",
    )

    assert result["summary"]["outcome"] == "required_reference_metadata_missing"
    assert result["model_comparison"].empty
    assert result["bound_predictions"].empty


def test_prediction_actual_must_match_bound_target() -> None:
    cycles, predictions = _frames()
    predictions.loc[0, "actual"] += 1.0

    with pytest.raises(ValueError, match="actual values do not match"):
        build_target_reference_sensitivity(
            cycle_summary=cycles,
            predictions=predictions,
            group_column="battery_id",
        )


def test_duplicate_target_cycle_binding_is_rejected() -> None:
    cycles, predictions = _frames()
    cycles = pd.concat([cycles, cycles.iloc[[0]]], ignore_index=True)

    with pytest.raises(ValueError, match="duplicate group/cycle"):
        build_target_reference_sensitivity(
            cycle_summary=cycles,
            predictions=predictions,
            group_column="battery_id",
        )


def _write_run(path: Path) -> None:
    cycles, predictions = _frames()
    tables = path / "tables"
    tables.mkdir(parents=True)
    cycles.to_csv(tables / "validated_cycle_summary.csv", index=False)
    predictions.to_csv(tables / "validation_predictions.csv", index=False)
    (path / "config_snapshot.json").write_text(
        json.dumps({"config": {"group_column": "battery_id"}}),
        encoding="utf-8",
    )


def test_cli_writes_transactional_outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run = tmp_path / "run"
    output = tmp_path / "sensitivity"
    _write_run(run)

    assert main(["--run", str(run), "--output", str(output)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["outcome"] == "conclusion_stable_across_defensible_targets"
    assert (output / "summary.json").is_file()
    assert (output / "model_comparison_by_target.csv").is_file()
    assert (output / "per_battery_comparison.csv").is_file()
    assert (output / "bound_validation_predictions.csv").is_file()
    assert (output / "report.md").is_file()

    with pytest.raises(FileExistsError):
        run_target_sensitivity(run, output)


def test_cli_failure_does_not_replace_prior_valid_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = tmp_path / "run"
    output = tmp_path / "sensitivity"
    _write_run(run)
    run_target_sensitivity(run, output)
    original = (output / "summary.json").read_bytes()

    def fail(*args: object, **kwargs: object) -> object:
        raise RuntimeError("forced failure")

    monkeypatch.setattr(
        "materials_data_analyzer.battery_target_sensitivity_cli.build_target_reference_sensitivity",
        fail,
    )
    with pytest.raises(RuntimeError, match="forced failure"):
        run_target_sensitivity(run, output, overwrite=True)
    assert (output / "summary.json").read_bytes() == original
