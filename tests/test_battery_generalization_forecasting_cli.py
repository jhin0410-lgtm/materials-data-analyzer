import json
from pathlib import Path

import pandas as pd

from src.cli import main
from src.platform_core.battery_forecasting import BENCHMARK_ID


def _repo(tmp_path):
    rows = []
    for group_index in range(4):
        for cycle in range(1, 16):
            rows.append(
                {
                    "battery_id": f"B{group_index}",
                    "cycle_index": cycle,
                    "capacity_retention_percent": 100 - cycle * (0.2 + group_index * 0.02),
                }
            )
    (tmp_path / "data").mkdir()
    (tmp_path / "configs").mkdir()
    pd.DataFrame(rows).to_csv(tmp_path / "data/input.csv", index=False)
    (tmp_path / "data/lineage.json").write_text("{}", encoding="utf-8")
    config = {
        "schema_version": "2.6.1",
        "benchmark_id": BENCHMARK_ID,
        "case_study_id": "kaggle_battery",
        "input_path": "data/input.csv",
        "source_lineage_path": "data/lineage.json",
        "group_column": "battery_id",
        "time_column": "cycle_index",
        "target_column": "capacity_retention_percent",
        "target_unit": "percent",
        "horizon": 5,
        "lags": [1, 2, 3],
        "rolling_window": 5,
        "minimum_history": 5,
        "split_method": "group_kfold",
        "n_splits": 3,
        "random_seed": 42,
        "models": ["persistence", "ridge"],
        "ridge_alpha": 1.0,
        "plausibility_min": 0.0,
        "plausibility_max": 150.0,
        "large_change_threshold": 25.0,
        "duplicate_cycle_policy": "reject_trajectory",
        "unordered_cycle_policy": "stable_sort_with_audit",
        "credential_policy": {
            "store_credentials": False,
            "network_access_required": False,
        },
        "output_root": "outputs/v2_6_battery_generalization",
        "output_policy": "local_details_and_tracked_compact_summary",
    }
    (tmp_path / "configs/config.json").write_text(
        json.dumps(config),
        encoding="utf-8",
    )


def test_preview_cli_is_json_and_side_effect_free(tmp_path, monkeypatch, capsys):
    _repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    code = main(
        [
            "--json",
            "preview-battery-generalization-forecast",
            "configs/config.json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    assert code == 0
    assert payload["status"] == "ready"
    assert payload["writes_performed"] is False
    assert before == after


def test_run_cli_writes_only_registered_outputs(tmp_path, monkeypatch, capsys):
    _repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    code = main(
        [
            "--json",
            "run-battery-generalization-forecast",
            "configs/config.json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "completed"
    assert payload["evaluation_scenario"] == "warm_start_cross_battery"
    assert payload["network_called"] is False
    assert payload["credentials_read"] is False
    assert (tmp_path / "outputs/v2_6_battery_generalization/forecast_summary.json").is_file()
    assert (
        tmp_path
        / "data/processed/battery_v2_6_1_generalization_forecast_summary.json"
    ).is_file()


def test_validate_cli_accepts_result_and_rejects_checksum_tampering(
    tmp_path,
    monkeypatch,
    capsys,
):
    _repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main(
        [
            "--json",
            "run-battery-generalization-forecast",
            "configs/config.json",
            "--local-only",
        ]
    ) == 0
    capsys.readouterr()
    result_path = "outputs/v2_6_battery_generalization/forecast_summary.json"

    assert main(
        ["--json", "validate-battery-generalization-forecast", result_path]
    ) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True

    payload = json.loads((tmp_path / result_path).read_text(encoding="utf-8"))
    payload["forecast_horizon_cycles"] = 99
    (tmp_path / result_path).write_text(json.dumps(payload), encoding="utf-8")
    assert main(
        ["--json", "validate-battery-generalization-forecast", result_path]
    ) == 2
    error = json.loads(capsys.readouterr().out)
    assert "deterministic checksum mismatch" in error["errors"]


def test_actual_tracked_example_preview_uses_no_network(capsys):
    code = main(
        [
            "--json",
            "preview-battery-generalization-forecast",
            "configs/examples/battery_generalization_forecast.json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["eligible_prediction_rows"] == 2100
    assert payload["evaluable_trajectory_count"] == 33
    assert payload["network_called"] is False
