from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from platform_core.battery_intelligence.influence_triage import (
    audit_battery_influence_run,
    build_battery_influence_triage,
)


def _target_integrity() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "battery_id": ["A", "B", "C", "D"],
            "outside_plausibility_count": [0, 0, 0, 2],
            "reference_consistency_flag": [False, False, False, False],
            "first_target_deviation_from_100_percent": [0.0, 0.0, 0.0, 0.0],
            "maximum_absolute_adjacent_target_change_percent": [
                1.0,
                1.0,
                1.0,
                25.0,
            ],
            "cycle_gap_count": [0, 0, 0, 0],
            "target_comparability_flag": [False, False, False, True],
            "median_observed_ambient_temperature_c": [24.0, 24.0, 30.0, 30.0],
        }
    )


def _predictions() -> pd.DataFrame:
    rows = []
    for battery_id, error in [("A", 1.0), ("B", 1.0), ("C", 1.0), ("D", 20.0)]:
        for _ in range(3):
            rows.append(
                {
                    "battery_id": battery_id,
                    "actual": 100.0,
                    "persistence_prediction": 100.0 - error,
                    "ridge_prediction": 100.0 - 1.2 * error,
                }
            )
    return pd.DataFrame(rows)


def test_influence_triage_ranks_disproportionate_battery_without_filtering() -> None:
    result = build_battery_influence_triage(
        target_integrity=_target_integrity(),
        predictions=_predictions(),
        group_column="battery_id",
    )

    priority = result["diagnostic_priority"]
    battery_d = priority.loc[priority["battery_id"] == "D"].iloc[0]
    battery_a = priority.loc[priority["battery_id"] == "A"].iloc[0]

    assert battery_d["diagnostic_review_order"] == 1
    assert bool(battery_d["requires_source_protocol_review"]) is True
    assert bool(battery_d["disproportionate_error_contributor_any_model"]) is True
    assert "large_adjacent_target_jump" in battery_d["diagnostic_flag_reasons"]
    assert bool(battery_a["requires_source_protocol_review"]) is False

    influence = result["influence_by_model"]
    persistence_d = influence[
        (influence["model"] == "persistence")
        & (influence["battery_id"] == "D")
    ].iloc[0]
    assert persistence_d["total_absolute_error_fraction"] > 0.8
    assert persistence_d["row_weighted_mae_reduction_if_omitted"] > 0
    assert len(influence["battery_id"].unique()) == 4
    assert result["summary"]["pooled_interpretation"] == "diagnostic_only"


def test_balanced_small_cohort_is_not_disproportionately_flagged() -> None:
    target = _target_integrity().copy()
    target["outside_plausibility_count"] = 0
    target["maximum_absolute_adjacent_target_change_percent"] = 1.0
    target["target_comparability_flag"] = False
    predictions = _predictions().copy()
    predictions["persistence_prediction"] = 99.0
    predictions["ridge_prediction"] = 99.0

    result = build_battery_influence_triage(
        target_integrity=target,
        predictions=predictions,
        group_column="battery_id",
    )

    priority = result["diagnostic_priority"]
    assert not priority["disproportionate_error_contributor_any_model"].any()
    assert not priority["requires_source_protocol_review"].any()
    assert (
        result["summary"]["pooled_interpretation"]
        == "not_flagged_but_protocol_identity_unverified"
    )


def test_audit_persists_artifacts_and_updates_manifest(tmp_path: Path) -> None:
    output = tmp_path / "run"
    tables = output / "tables"
    reports = output / "reports"
    tables.mkdir(parents=True)
    reports.mkdir(parents=True)

    _target_integrity().to_csv(
        tables / "target_integrity_by_battery.csv",
        index=False,
    )
    _predictions().to_csv(tables / "validation_predictions.csv", index=False)
    (output / "config_snapshot.json").write_text(
        json.dumps({"config": {"group_column": "battery_id"}}),
        encoding="utf-8",
    )
    (reports / "scientific_closeout.json").write_text(
        json.dumps(
            {
                "evidence_level": "Unsupported",
                "component_statuses": {},
                "strongest_evidence": {},
                "limitations": [],
                "primary_limitation": "Existing limitation.",
            }
        ),
        encoding="utf-8",
    )
    (reports / "scientific_closeout.md").write_text(
        "# Scientific Closeout\n",
        encoding="utf-8",
    )
    (output / "run_manifest.json").write_text(
        json.dumps(
            {
                "artifact_paths": [],
                "artifact_checksums": {},
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )

    result = audit_battery_influence_run(output)

    assert Path(result["outputs"]["battery_influence_by_model"]).is_file()
    assert Path(result["outputs"]["battery_diagnostic_priority"]).is_file()
    assert Path(result["outputs"]["battery_condition_error_profile"]).is_file()
    assert Path(result["outputs"]["battery_influence_triage"]).is_file()

    manifest = json.loads(
        (output / "run_manifest.json").read_text(encoding="utf-8")
    )
    assert "battery_influence_triage" in manifest
    assert (
        "reports/battery_influence_triage.json"
        in manifest["artifact_checksums"]
    )

    closeout = json.loads(
        (reports / "scientific_closeout.json").read_text(encoding="utf-8")
    )
    assert (
        "battery_influence_and_observed_condition_triage"
        in closeout["component_statuses"]
    )

    audit_battery_influence_run(output)
    closeout_rerun = json.loads(
        (reports / "scientific_closeout.json").read_text(encoding="utf-8")
    )
    limitation = (
        "Battery-level omission deltas and observed-condition profiles show that "
        "pooled scores require source- and protocol-aware review; omission "
        "sensitivity is diagnostic and cannot be used as a replacement score."
    )
    assert closeout_rerun["limitations"].count(limitation) == 1
    assert closeout_rerun["primary_limitation"].count(limitation) == 1
