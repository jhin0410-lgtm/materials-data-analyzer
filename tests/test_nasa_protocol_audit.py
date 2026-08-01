from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from platform_core.battery_intelligence.nasa_protocol_audit import (
    _diagnostic_limitation,
    audit_nasa_protocol_run,
    build_nasa_protocol_audit,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_nasa_pcoe_protocol_audit.ps1"
BATTERIES = ["A", "B", "C", "D", "E", "F"]


def _protocol_summary() -> pd.DataFrame:
    temperatures = {
        "A": 25.0,
        "B": 25.0,
        "C": 25.0,
        "D": 40.0,
        "E": 40.0,
        "F": 4.0,
    }
    rows = []
    for index, battery in enumerate(BATTERIES):
        rows.append(
            {
                "battery_id": battery,
                "discharge_cycle_count": 20 if battery != "F" else 3,
                "raw_point_count": 1000 if battery != "F" else 100,
                "ambient_temperature_min_c": temperatures[battery],
                "ambient_temperature_median_c": temperatures[battery],
                "ambient_temperature_max_c": temperatures[battery],
                "voltage_min_v": 2.0 + 0.01 * index,
                "voltage_max_v": 4.2,
                "current_abs_median_a": 1.0 + 0.1 * index,
                "current_abs_max_a": 1.2 + 0.1 * index,
                "sample_interval_median_s": 10.0,
                "discharge_duration_median_s": 3600.0 - 100.0 * index,
                "initial_discharge_capacity_ah": 1.8,
                "final_discharge_capacity_ah": 1.5,
                "minimum_discharge_capacity_ah": 1.5,
                "maximum_discharge_capacity_ah": 1.9,
                "minimum_capacity_retention_percent": 75.0,
                "median_capacity_retention_percent": 85.0 - index,
                "maximum_capacity_retention_percent": 95.0,
                "rated_capacity_ah": 2.0,
                "reference_capacity_method": "source_rated_capacity_2_ah",
                "initial_discharge_capacity_fraction_of_rated": 0.9,
            }
        )
    return pd.DataFrame(rows)


def _target_integrity() -> pd.DataFrame:
    rows = []
    for battery in BATTERIES:
        rows.append(
            {
                "battery_id": battery,
                "first_target_deviation_from_100_percent": 10.0,
                "reference_consistency_flag": battery == "E",
                "outside_plausibility_count": 0,
                "cycle_gap_count": 1 if battery == "C" else 0,
                "maximum_absolute_adjacent_target_change_percent": (
                    30.0 if battery == "D" else 2.0
                ),
            }
        )
    return pd.DataFrame(rows)


def _priority() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "battery_id": BATTERIES,
            "persistence_is_disproportionate_absolute_error_contributor": [
                False,
                False,
                False,
                True,
                False,
                False,
            ],
            "ridge_is_disproportionate_absolute_error_contributor": [
                False,
                False,
                False,
                True,
                False,
                False,
            ],
        }
    )


def _inventory() -> pd.DataFrame:
    rows = []
    for battery in BATTERIES:
        rows.append(
            {
                "battery_id": battery,
                "skip_reason": "",
                "imported_discharge_operation_count": 20,
                "excluded_discharge_operation_count": 2 if battery == "D" else 0,
                "invalid_capacity_operation_count": 2 if battery == "D" else 0,
                "nonfinite_capacity_operation_count": 2 if battery == "D" else 0,
            }
        )
    rows.append(
        {
            "battery_id": "D",
            "skip_reason": "duplicate_identical_source_copy",
            "imported_discharge_operation_count": 20,
            "excluded_discharge_operation_count": 2,
            "invalid_capacity_operation_count": 2,
            "nonfinite_capacity_operation_count": 2,
        }
    )
    return pd.DataFrame(rows)


def _predictions(*, ridge_error: float | None = None) -> pd.DataFrame:
    rows = []
    for battery in BATTERIES[:-1]:
        persistence_error = 1.0
        battery_ridge_error = (
            ridge_error
            if ridge_error is not None
            else 0.5 if battery == "B" else 2.0
        )
        for cycle in range(3):
            actual = 90.0 - cycle
            rows.append(
                {
                    "battery_id": battery,
                    "actual": actual,
                    "persistence_prediction": actual + persistence_error,
                    "ridge_prediction": actual + battery_ridge_error,
                }
            )
    return pd.DataFrame(rows)


def _signal_comparison() -> dict[str, float]:
    return {
        "capacity_only_ridge_mae": 4.3,
        "signal_enriched_ridge_mae": 4.6,
        "improvement_percent": -6.0,
    }


def _build_audit(
    *,
    source_inventory: pd.DataFrame | None = None,
    predictions: pd.DataFrame | None = None,
    declared_evidence_level: str = "Unsupported",
) -> dict[str, object]:
    return build_nasa_protocol_audit(
        protocol_summary=_protocol_summary(),
        source_inventory=(
            _inventory() if source_inventory is None else source_inventory
        ),
        target_integrity=_target_integrity(),
        diagnostic_priority=_priority(),
        predictions=_predictions() if predictions is None else predictions,
        signal_feature_comparison=_signal_comparison(),
        declared_evidence_level=declared_evidence_level,
    )


def test_protocol_audit_separates_context_from_structural_issues() -> None:
    result = _build_audit()
    summary = result["summary"]
    profile = result["battery_profile"].set_index("battery_id")

    assert summary["battery_count"] == 6
    assert summary["evaluated_battery_count"] == 5
    assert summary["unevaluated_battery_count"] == 1
    assert summary["reference_start_context_battery_count"] == 6
    assert summary["reference_context_only_battery_count"] == 2
    assert summary["source_quality_issue_battery_count"] == 2
    assert summary["trajectory_continuity_issue_battery_count"] == 2
    assert summary["structural_or_coverage_issue_battery_count"] == 4
    assert summary["disproportionate_error_influence_battery_count"] == 1
    assert summary["invalid_capacity_quarantine_operation_count"] == 2
    assert bool(profile.loc["A", "reference_context_only"]) is True
    assert bool(profile.loc["B", "reference_context_only"]) is True
    assert bool(profile.loc["D", "invalid_capacity_quarantine_issue"]) is True
    assert bool(profile.loc["F", "evaluation_coverage_issue"]) is True
    assert "first_target_not_near_rated_capacity" in profile.loc[
        "A", "context_reasons"
    ]
    assert profile.loc["A", "structural_review_reasons"] == ""
    assert len(profile) == 6


def test_protocol_audit_reports_model_failure_and_suppresses_sparse_strata() -> None:
    result = _build_audit()
    summary = result["summary"]
    strata = result["temperature_strata"].set_index(
        "ambient_temperature_median_c"
    )

    assert summary["persistence_row_weighted_mae"] == pytest.approx(1.0)
    assert summary["ridge_row_weighted_mae"] == pytest.approx(1.7)
    assert summary["ridge_improvement_vs_persistence_percent"] == pytest.approx(
        -70.0
    )
    assert summary["ridge_better_than_persistence_battery_count"] == 1
    assert summary["signal_enriched_improvement_percent"] == -6.0
    assert summary["predictive_evidence_level"] == "Unsupported"
    assert "Persistence remains better" in summary["primary_model_result"]

    assert bool(
        strata.loc[25.0, "supported_for_within_stratum_description"]
    ) is True
    assert bool(
        strata.loc[40.0, "supported_for_within_stratum_description"]
    ) is False
    assert bool(
        strata.loc[4.0, "supported_for_within_stratum_description"]
    ) is False
    assert pd.notna(strata.loc[25.0, "ridge_row_weighted_mae"])
    assert pd.isna(strata.loc[40.0, "ridge_row_weighted_mae"])
    assert pd.isna(strata.loc[4.0, "ridge_row_weighted_mae"])
    assert summary["supported_temperature_stratum_count"] == 1
    assert not result["error_associations"].empty


def test_protocol_audit_preserves_evidence_and_derives_model_result() -> None:
    result = _build_audit(
        predictions=_predictions(ridge_error=0.5),
        declared_evidence_level="Inconclusive",
    )
    summary = result["summary"]

    assert summary["predictive_evidence_level"] == "Inconclusive"
    assert "Ridge is lower than persistence" in summary["primary_model_result"]
    assert "preserves" in summary["evidence_preservation_boundary"]


def test_protocol_audit_rejects_unknown_prediction_identity() -> None:
    predictions = _predictions().copy()
    predictions.loc[len(predictions)] = {
        "battery_id": "UNKNOWN",
        "actual": 90.0,
        "persistence_prediction": 89.0,
        "ridge_prediction": 88.0,
    }
    with pytest.raises(ValueError, match="absent from NASA protocol summary"):
        _build_audit(predictions=predictions)


def test_protocol_audit_accepts_inventory_without_quarantine_counters() -> None:
    inventory = pd.DataFrame(
        {"battery_id": BATTERIES, "skip_reason": [""] * len(BATTERIES)}
    )
    result = _build_audit(source_inventory=inventory)

    assert result["summary"]["invalid_capacity_quarantine_operation_count"] == 0
    assert result["summary"]["source_quality_issue_battery_count"] == 1


def test_protocol_audit_rejects_missing_inventory_battery() -> None:
    inventory = _inventory()
    inventory = inventory[inventory["battery_id"] != "F"].copy()

    with pytest.raises(ValueError, match="missing protocol batteries: F"):
        _build_audit(source_inventory=inventory)


def test_neutral_limitation_does_not_invent_findings() -> None:
    limitation = _diagnostic_limitation(
        {
            "reference_start_context_battery_count": 0,
            "source_quality_issue_battery_count": 0,
            "trajectory_continuity_issue_battery_count": 0,
            "unevaluated_battery_count": 0,
            "supported_temperature_stratum_count": 0,
            "diagnostic_association_count": 0,
        }
    )

    assert "did not identify supported" in limitation
    assert "trajectory discontinuities" not in limitation
    assert "condition-dependent error structure" not in limitation


def _write_existing_run(import_output: Path, analysis_output: Path) -> None:
    reports = analysis_output / "reports"
    tables = analysis_output / "tables"
    import_output.mkdir(parents=True)
    reports.mkdir(parents=True)
    tables.mkdir(parents=True)

    _protocol_summary().to_csv(
        import_output / "nasa_pcoe_protocol_summary.csv", index=False
    )
    _inventory().to_csv(
        import_output / "nasa_pcoe_source_inventory.csv", index=False
    )
    _target_integrity().to_csv(
        tables / "target_integrity_by_battery.csv", index=False
    )
    _priority().to_csv(tables / "battery_diagnostic_priority.csv", index=False)
    _predictions().to_csv(tables / "validation_predictions.csv", index=False)
    (reports / "signal_feature_comparison.json").write_text(
        json.dumps(_signal_comparison()), encoding="utf-8"
    )
    closeout = {
        "evidence_level": "Unsupported",
        "component_statuses": {},
        "strongest_evidence": {},
        "limitations": [],
        "primary_limitation": "Existing limitation.",
    }
    (reports / "scientific_closeout.json").write_text(
        json.dumps(closeout), encoding="utf-8"
    )
    (reports / "scientific_closeout.md").write_text(
        "# Scientific Closeout\n", encoding="utf-8"
    )
    (analysis_output / "run_manifest.json").write_text(
        json.dumps(
            {
                "artifact_paths": [],
                "artifact_checksums": {},
                "scientific_closeout": closeout,
                "scientific_validation": "Unsupported",
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )


def test_existing_run_audit_is_idempotent_and_preserves_markdown_suffix(
    tmp_path: Path,
) -> None:
    import_output = tmp_path / "import"
    analysis_output = tmp_path / "analysis"
    _write_existing_run(import_output, analysis_output)

    result = audit_nasa_protocol_run(
        import_output=import_output,
        analysis_output=analysis_output,
    )
    for path in result["outputs"].values():
        assert Path(path).is_file()

    closeout_path = analysis_output / "reports" / "scientific_closeout.json"
    markdown_path = analysis_output / "reports" / "scientific_closeout.md"
    closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
    limitation = closeout["limitations"][-1]
    assert closeout["evidence_level"] == "Unsupported"
    assert result["summary"]["predictive_evidence_level"] == "Unsupported"
    assert (
        closeout["component_statuses"][
            "nasa_protocol_aware_posthoc_audit"
        ]["status"]
        == "Diagnostic"
    )

    suffix = (
        "<!-- later-tool:start -->\n\n## Later Tool\n\nkeep me\n\n"
        "<!-- later-tool:end -->\n"
    )
    markdown_path.write_text(
        markdown_path.read_text(encoding="utf-8").rstrip()
        + "\n\n"
        + suffix,
        encoding="utf-8",
    )

    audit_nasa_protocol_run(
        import_output=import_output,
        analysis_output=analysis_output,
    )
    rerun = json.loads(closeout_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    manifest = json.loads(
        (analysis_output / "run_manifest.json").read_text(encoding="utf-8")
    )

    assert rerun["limitations"].count(limitation) == 1
    assert rerun["primary_limitation"].count(limitation) == 1
    assert markdown.count("<!-- nasa-protocol-audit:start -->") == 1
    assert "<!-- later-tool:start -->" in markdown
    assert "keep me" in markdown
    assert "nasa_protocol_aware_posthoc_audit" in manifest
    assert "reports/nasa_protocol_audit.json" in manifest["artifact_checksums"]


def test_protocol_audit_script_has_valid_powershell_syntax() -> None:
    executable = shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell is not installed in this environment")
    command = (
        "$tokens = $null; $errors = $null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{SCRIPT.as_posix()}', "
        "[ref]$tokens, [ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }"
    )
    completed = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_protocol_audit_script_executes_existing_artifacts(tmp_path: Path) -> None:
    executable = shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell is not installed in this environment")
    import_output = tmp_path / "import"
    analysis_output = tmp_path / "analysis"
    _write_existing_run(import_output, analysis_output)

    completed = subprocess.run(
        [
            executable,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(SCRIPT),
            "-ImportOutput",
            str(import_output),
            "-AnalysisOutput",
            str(analysis_output),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "No import or model fitting will be performed" in completed.stdout
    assert "protocol_audit_status: Diagnostic" in completed.stdout
    assert "predictive_evidence_level: Unsupported" in completed.stdout
    assert "reference_context_only_battery_count: 2" in completed.stdout
    assert "structural_or_coverage_issue_battery_count: 4" in completed.stdout
