"""Tests for the real NIST AM-Bench 2018-02 single-track case study."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from loaders.nist_ambench_single_track import (
    build_case_summary,
    build_characterization_feature_table,
    build_process_table,
    load_source_contract,
    load_trace_measurements,
    validate_trace_measurements,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = (
    PROJECT_ROOT
    / "data"
    / "case_studies"
    / "nist_ambench_2018_single_track"
)
TABLE_PATH = CASE_DIR / "trace_measurements.csv"
CONTRACT_PATH = CASE_DIR / "source_contract.json"


def _loaded() -> tuple[dict[str, object], pd.DataFrame]:
    contract = load_source_contract(CONTRACT_PATH)
    table = load_trace_measurements(TABLE_PATH, contract)
    return contract, table


def test_official_trace_table_contract_and_identifiers() -> None:
    contract, table = _loaded()
    assert len(table) == 10
    assert table["trace_number"].tolist() == list(range(1, 11))
    assert table["sample_id"].tolist() == [
        f"amb2018_02_trace_{trace:02d}" for trace in range(1, 11)
    ]
    assert table.groupby("case_id").size().to_dict() == {"A": 3, "B": 3, "C": 4}
    assert contract["provenance_status"] == (
        "manual_transcription_from_official_nist_result_table"
    )


def test_corrected_process_metadata_is_preserved_and_used() -> None:
    contract, table = _loaded()
    process = build_process_table(table, contract)
    assert set(table["legacy_reported_spot_size_fwhm_um"]) == {45.0}
    assert set(process["corrected_spot_size_fwhm_um"]) == {100.0}
    assert set(process["spot_size_metadata_status"]) == {
        "corrected_nist_value_used"
    }
    energies = process.groupby("case_id")["linear_energy_j_mm"].first().to_dict()
    assert energies["A"] == pytest.approx(137.9 / 400.0)
    assert energies["B"] == pytest.approx(179.2 / 800.0)
    assert energies["C"] == pytest.approx(179.2 / 1200.0)


def test_case_summary_reproduces_official_rounded_values() -> None:
    contract, table = _loaded()
    summary = build_case_summary(table, contract).set_index("case_id")
    expected = {
        "A": (147.9, 3.7, 42.5, 1.7),
        "B": (123.5, 6.5, 36.0, 1.9),
        "C": (106.0, 1.4, 29.6, 0.6),
    }
    for case_id, values in expected.items():
        calculated = (
            round(summary.loc[case_id, "width_mean_um"], 1),
            round(summary.loc[case_id, "width_between_trace_std_dev_um"], 1),
            round(summary.loc[case_id, "depth_mean_um"], 1),
            round(summary.loc[case_id, "depth_between_trace_std_dev_um"], 1),
        )
        assert calculated == values


def test_characterization_contract_contains_four_features_per_trace() -> None:
    contract, table = _loaded()
    features = build_characterization_feature_table(table, contract)
    assert len(features) == 40
    assert features["sample_id"].nunique() == 10
    assert set(features["instrument"]) == {"optical_microscopy"}
    assert set(features["feature_name"]) == {
        "melt_pool_width_mean",
        "melt_pool_width_std_dev",
        "melt_pool_depth_mean",
        "melt_pool_depth_std_dev",
    }
    assert features["feature_label"].isna().all()
    assert set(features["quality_flag"]) == {"official_reported_measurement"}


def test_process_setting_mutation_is_rejected() -> None:
    contract, table = _loaded()
    mutated = table.copy()
    mutated.loc[
        mutated["case_id"].eq("A"), "calibrated_laser_power_w"
    ] = 150.0
    with pytest.raises(ValueError, match="calibrated_laser_power_w"):
        validate_trace_measurements(mutated, contract)


def test_clean_checkout_cli_runs_real_handoff_without_nan_keys(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "nist_case"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_nist_ambench_single_track_case_study.py",
            "--output",
            str(output_dir),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "case study completed" in completed.stdout

    audit = pd.read_csv(output_dir / "handoff" / "sample_join_audit.csv")
    assert len(audit) == 10
    assert audit["join_status"].eq("matched").all()

    integrated = pd.read_csv(
        output_dir / "handoff" / "integrated_sample_table.csv"
    )
    assert not any("__nan__" in column for column in integrated.columns)
    assert "char__optical_microscopy__melt_pool_width_mean__um" in integrated
    assert "linear_energy_j_mm" in integrated

    manifest = json.loads(
        (output_dir / "case_study_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["software_validation"]["status"] == "supported"
    assert manifest["scientific_closeout"]["status"] == "diagnostic"
    assert manifest["model_training_performed"] is False
    assert manifest["raw_image_reanalysis_performed"] is False

    report = (output_dir / "case_study_report.md").read_text(encoding="utf-8")
    assert "Scientific closeout: Diagnostic" in report
    assert "Only three unique process settings" in report
