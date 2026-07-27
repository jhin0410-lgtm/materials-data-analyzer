"""Tests for the NIST AM-Bench 2018-02 real-data case study."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = PROJECT_ROOT / "data" / "case_studies" / "nist_ambench_2018_02"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build_nist_ambench_2018_02_case_study.py"


def _load_case_module():
    spec = importlib.util.spec_from_file_location("ambench_case_study", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tracked_source_tables_reproduce_nist_class_summary() -> None:
    process = pd.read_csv(CASE_DIR / "source_process_conditions.csv")
    measurements = pd.read_csv(CASE_DIR / "source_melt_pool_measurements.csv")

    assert len(process) == 10
    assert len(measurements) == 10
    assert sorted(process["trace_number"].tolist()) == list(range(1, 11))
    assert process.groupby("case_id").size().to_dict() == {"A": 3, "B": 3, "C": 4}
    assert set(process["system"]) == {"AMMT"}
    assert set(process["material"]) == {"IN625"}

    identity = process[["sample_id", "case_id", "trace_number"]].merge(
        measurements[["sample_id", "case_id", "trace_number"]],
        on=["sample_id", "case_id", "trace_number"],
        how="outer",
        validate="one_to_one",
        indicator=True,
    )
    assert identity["_merge"].eq("both").all()

    summary = measurements.groupby("case_id").agg(
        width_mean=("melt_pool_width_mean_um", "mean"),
        width_std=("melt_pool_width_mean_um", "std"),
        depth_mean=("melt_pool_depth_mean_um", "mean"),
        depth_std=("melt_pool_depth_mean_um", "std"),
    )
    rounded = {
        case: {
            "width_mean": round(float(row.width_mean), 1),
            "width_std": round(float(row.width_std), 1),
            "depth_mean": round(float(row.depth_mean), 1),
            "depth_std": round(float(row.depth_std), 1),
        }
        for case, row in summary.iterrows()
    }
    assert rounded == {
        "A": {"width_mean": 147.9, "width_std": 3.7, "depth_mean": 42.5, "depth_std": 1.7},
        "B": {"width_mean": 123.5, "width_std": 6.5, "depth_mean": 36.0, "depth_std": 1.9},
        "C": {"width_mean": 106.0, "width_std": 1.4, "depth_mean": 29.6, "depth_std": 0.6},
    }


def test_source_validation_rejects_identity_mismatch() -> None:
    module = _load_case_module()
    process = pd.read_csv(CASE_DIR / "source_process_conditions.csv")
    measurements = pd.read_csv(CASE_DIR / "source_melt_pool_measurements.csv")
    measurements.loc[0, "case_id"] = "A"

    with pytest.raises(ValueError, match="Case IDs differ"):
        module.validate_source_tables(process, measurements)


def test_case_study_runs_end_to_end_without_modeling(tmp_path: Path) -> None:
    output_dir = tmp_path / "ambench"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--output",
            str(output_dir),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "case study completed" in completed.stdout.lower()

    expected_files = {
        "ambench_characterization_features_long.csv",
        "ambench_process_conditions_normalized.csv",
        "characterization_features_validated_long.csv",
        "characterization_feature_dictionary.csv",
        "characterization_features_wide.csv",
        "integrated_sample_table.csv",
        "sample_join_audit.csv",
        "ambench_case_summary.csv",
        "melt_pool_width_by_linear_energy.png",
        "melt_pool_depth_by_linear_energy.png",
        "ambench_case_study_report.md",
        "ambench_case_study_manifest.json",
        "characterization_handoff_manifest.json",
    }
    assert expected_files.issubset({path.name for path in output_dir.iterdir()})

    audit = pd.read_csv(output_dir / "sample_join_audit.csv")
    assert len(audit) == 10
    assert audit["join_status"].eq("matched").all()

    integrated = pd.read_csv(output_dir / "integrated_sample_table.csv")
    assert len(integrated) == 10
    assert not any("__nan__" in column for column in integrated.columns)
    assert {
        "actual_laser_power_w",
        "scan_speed_mm_s",
        "linear_energy_density_j_mm",
        "char__optical_microscopy_metrology__melt_pool_width_mean__um",
        "char__optical_microscopy_metrology__melt_pool_depth_mean__um",
    }.issubset(integrated.columns)

    summary = pd.read_csv(output_dir / "ambench_case_summary.csv")
    assert summary["case_id"].tolist() == ["A", "B", "C"]
    assert summary["n_traces"].tolist() == [3, 3, 4]

    manifest = json.loads(
        (output_dir / "ambench_case_study_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["counts"] == {
        "trace_count": 10,
        "process_condition_count": 3,
        "characterization_record_count": 40,
        "matched_sample_count": 10,
    }
    assert manifest["validation"]["model_trained"] is False
    assert manifest["validation"]["optimization_performed"] is False
    assert manifest["validation"]["official_rounded_class_summary_reproduced"] is True
    assert manifest["scientific_closeout"]["status"] == "diagnostic"
    assert "predictive modeling" in manifest["scientific_closeout"]["unsuitable_for"]

    report = (output_dir / "ambench_case_study_report.md").read_text(encoding="utf-8")
    assert "Scientific status: **Diagnostic**" in report
    assert "does not account for" not in report  # line-energy limitations are stated elsewhere
    assert not list(output_dir.glob("*.pkl"))
    assert not list(output_dir.glob("*model*"))


def test_case_study_core_outputs_are_deterministic(tmp_path: Path) -> None:
    module = _load_case_module()
    first = module.run_case_study(tmp_path / "first")
    second = module.run_case_study(tmp_path / "second")

    for key in ("case_summary", "report", "characterization_long"):
        assert first[key].read_bytes() == second[key].read_bytes()
