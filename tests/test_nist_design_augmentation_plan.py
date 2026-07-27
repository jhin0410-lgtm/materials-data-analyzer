from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    PROJECT_ROOT
    / "scripts"
    / "plan_nist_ambench_2018_02_design_augmentation.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("nist_design_plan", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _nist_table() -> pd.DataFrame:
    rows = []
    for case_id, power, speed, traces in (
        ("A", 137.9, 400.0, (5, 6, 7)),
        ("B", 179.2, 800.0, (8, 9, 10)),
        ("C", 179.2, 1200.0, (1, 2, 3, 4)),
    ):
        for trace in traces:
            rows.append(
                {
                    "sample_id": f"amb2018_02_ammt_trace_{trace:02d}",
                    "case_id": case_id,
                    "actual_laser_power_w": power,
                    "scan_speed_mm_s": speed,
                    "char__optical_microscopy_metrology__melt_pool_width_mean__um": 100.0
                    + trace,
                }
            )
    return pd.DataFrame(rows)


def test_plan_defines_minimum_staged_conditions_and_trace_counts() -> None:
    module = _module()
    conditions, plan = module.build_augmentation_plan(_nist_table())

    stage_1 = conditions.loc[
        conditions["stage"].eq("stage_1_complete_observed_grid")
    ]
    assert stage_1[
        ["actual_laser_power_w", "scan_speed_mm_s"]
    ].to_dict("records") == [
        {"actual_laser_power_w": 137.9, "scan_speed_mm_s": 800.0},
        {"actual_laser_power_w": 137.9, "scan_speed_mm_s": 1200.0},
        {"actual_laser_power_w": 179.2, "scan_speed_mm_s": 400.0},
    ]
    stage_2 = conditions.loc[
        conditions["stage"].eq("stage_2_add_midpoint_power")
    ]
    assert stage_2["actual_laser_power_w"].tolist() == [158.55, 158.55, 158.55]
    assert stage_2["scan_speed_mm_s"].tolist() == [400.0, 800.0, 1200.0]
    assert set(conditions["minimum_trace_replicates"]) == {3}
    assert not conditions["machine_feasibility_confirmed"].astype(bool).any()
    assert conditions["actual_power_calibration_required"].astype(bool).all()

    assert plan["totals"] == {
        "stage_1_new_conditions": 3,
        "stage_1_new_traces": 9,
        "stage_2_additional_conditions": 3,
        "stage_2_additional_traces": 9,
        "cumulative_new_conditions_through_stage_2": 6,
        "cumulative_new_traces_through_stage_2": 18,
    }
    assert plan["decision"]["recommended_next_action"] == "execute_stage_1_only"


def test_resulting_design_rank_progression_is_explicit() -> None:
    module = _module()
    _, plan = module.build_augmentation_plan(_nist_table())

    current = plan["current_design"]["design_summary"]["models"]
    stage_1 = plan["stages"]["stage_1_complete_observed_grid"][
        "resulting_design"
    ]["models"]
    stage_2 = plan["stages"]["stage_2_add_midpoint_power"][
        "resulting_design"
    ]["models"]

    assert current["main_effects_plus_interaction"]["matrix_rank"] == 3
    assert current["main_effects_plus_interaction"]["parameter_count"] == 4
    assert stage_1["main_effects_plus_interaction"] == {
        "parameter_names": [
            "intercept",
            "actual_laser_power_w",
            "scan_speed_mm_s",
            "actual_laser_power_w:scan_speed_mm_s",
        ],
        "parameter_count": 4,
        "matrix_rank": 4,
        "full_column_rank": True,
        "condition_level_residual_df": 2,
    }
    assert stage_1["interaction_plus_speed_curvature"]["matrix_rank"] == 5
    assert stage_1["interaction_plus_speed_curvature"][
        "condition_level_residual_df"
    ] == 1
    assert stage_1["full_quadratic_response_surface"]["matrix_rank"] == 5
    assert stage_1["full_quadratic_response_surface"]["parameter_count"] == 6
    assert stage_2["full_quadratic_response_surface"]["matrix_rank"] == 6
    assert stage_2["full_quadratic_response_surface"][
        "condition_level_residual_df"
    ] == 3


def test_plan_keeps_validation_targets_unselected_and_claims_bounded() -> None:
    module = _module()
    _, plan = module.build_augmentation_plan(_nist_table())

    validation = plan["stages"]["stage_3_independent_validation"]
    assert validation["numeric_conditions_automatically_selected"] is False
    assert validation["minimum_distinct_validation_conditions"] == 2
    assert validation["minimum_trace_replicates_per_condition"] == 3
    assert plan["software_validation"] == {
        "response_model_fitted": False,
        "response_values_read": False,
        "optimization_performed": False,
        "missing_response_values_inferred": False,
        "machine_feasibility_assumed": False,
    }
    assert "machine control" in plan["scientific_closeout"]["unsuitable_for"]


def test_plan_is_row_order_independent_and_deterministic(tmp_path: Path) -> None:
    module = _module()
    first_source = tmp_path / "first.csv"
    second_source = tmp_path / "second.csv"
    table = _nist_table()
    table.to_csv(first_source, index=False)
    table.sample(frac=1.0, random_state=42).to_csv(second_source, index=False)

    first = module.run_plan(first_source, tmp_path / "first")
    second = module.run_plan(second_source, tmp_path / "second")

    assert first["recommended_conditions"].read_bytes() == second[
        "recommended_conditions"
    ].read_bytes()
    first_plan = json.loads(first["plan"].read_text(encoding="utf-8"))
    second_plan = json.loads(second["plan"].read_text(encoding="utf-8"))
    first_plan.pop("input")
    second_plan.pop("input")
    assert first_plan == second_plan
    assert first["report"].read_bytes() == second["report"].read_bytes()


def test_plan_rejects_inapplicable_or_complete_factor_grid() -> None:
    module = _module()
    invalid = _nist_table()
    invalid.loc[invalid["case_id"].eq("A"), "actual_laser_power_w"] = 158.0
    with pytest.raises(ValueError, match="exactly two observed power levels"):
        module.build_augmentation_plan(invalid)

    complete_rows = []
    sequence = 0
    for power in (137.9, 179.2):
        for speed in (400.0, 800.0, 1200.0):
            for _ in range(3):
                sequence += 1
                complete_rows.append(
                    {
                        "sample_id": f"complete_{sequence:02d}",
                        "case_id": f"P{power}_S{speed}",
                        "actual_laser_power_w": power,
                        "scan_speed_mm_s": speed,
                    }
                )
    with pytest.raises(ValueError, match="already complete"):
        module.build_augmentation_plan(pd.DataFrame(complete_rows))


def test_cli_writes_checksummed_outputs_and_no_model_artifacts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "integrated_sample_table.csv"
    _nist_table().to_csv(source, index=False)
    output = tmp_path / "plan"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--integrated-table",
            str(source),
            "--output",
            str(output),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "augmentation plan completed" in completed.stdout.lower()
    manifest = json.loads(
        (output / "nist_design_augmentation_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["response_model_fitted"] is False
    assert manifest["optimization_performed"] is False
    assert manifest["machine_feasibility_assumed"] is False
    assert manifest["scientific_status"] == "Diagnostic"
    for name, filename in manifest["outputs"].items():
        assert manifest["output_sha256"][name] == module_sha(output / filename)
    assert not list(output.glob("*.pkl"))
    assert not list(output.glob("*model*"))


def module_sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_nonempty_output_is_preserved(tmp_path: Path) -> None:
    module = _module()
    source = tmp_path / "input.csv"
    _nist_table().to_csv(source, index=False)
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="existing files were preserved"):
        module.run_plan(source, output)
    assert sentinel.read_text(encoding="utf-8") == "keep"
