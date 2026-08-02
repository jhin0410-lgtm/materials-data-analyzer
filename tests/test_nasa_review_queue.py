from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from platform_core.battery_intelligence.common import file_sha256
from platform_core.battery_intelligence.nasa_review_queue import (
    audit_nasa_focused_review_queue,
    build_nasa_focused_review_queue,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_nasa_pcoe_review_queue.ps1"


def _profile() -> pd.DataFrame:
    rows = [
        {
            "battery_id": "A",
            "is_evaluated": True,
            "prediction_count": 3,
            "reference_start_context_flag": True,
            "reference_context_only": True,
            "source_quality_issue": False,
            "trajectory_continuity_issue": False,
            "evaluation_coverage_issue": False,
            "structural_or_coverage_issue": False,
            "disproportionate_error_influence": False,
            "context_reasons": "first_target_not_near_rated_capacity",
            "structural_review_reasons": "",
            "influence_review_reasons": "",
            "persistence_mae": 1.0,
            "ridge_mae": 2.0,
            "ridge_minus_persistence_mae": 1.0,
        },
        {
            "battery_id": "B",
            "is_evaluated": True,
            "prediction_count": 3,
            "reference_start_context_flag": True,
            "reference_context_only": False,
            "source_quality_issue": True,
            "trajectory_continuity_issue": False,
            "evaluation_coverage_issue": False,
            "structural_or_coverage_issue": True,
            "disproportionate_error_influence": True,
            "context_reasons": "first_target_not_near_rated_capacity",
            "structural_review_reasons": "invalid_capacity_quarantine",
            "influence_review_reasons": "disproportionate_error_influence",
            "persistence_mae": 10.0,
            "ridge_mae": 12.0,
            "ridge_minus_persistence_mae": 2.0,
        },
        {
            "battery_id": "C",
            "is_evaluated": True,
            "prediction_count": 3,
            "reference_start_context_flag": True,
            "reference_context_only": False,
            "source_quality_issue": False,
            "trajectory_continuity_issue": True,
            "evaluation_coverage_issue": False,
            "structural_or_coverage_issue": True,
            "disproportionate_error_influence": True,
            "context_reasons": "first_target_not_near_rated_capacity",
            "structural_review_reasons": "cycle_index_gap",
            "influence_review_reasons": "disproportionate_error_influence",
            "persistence_mae": 8.0,
            "ridge_mae": 7.0,
            "ridge_minus_persistence_mae": -1.0,
        },
        {
            "battery_id": "D",
            "is_evaluated": True,
            "prediction_count": 3,
            "reference_start_context_flag": True,
            "reference_context_only": False,
            "source_quality_issue": False,
            "trajectory_continuity_issue": False,
            "evaluation_coverage_issue": False,
            "structural_or_coverage_issue": False,
            "disproportionate_error_influence": True,
            "context_reasons": "first_target_not_near_rated_capacity",
            "structural_review_reasons": "",
            "influence_review_reasons": "disproportionate_error_influence",
            "persistence_mae": 6.0,
            "ridge_mae": 9.0,
            "ridge_minus_persistence_mae": 3.0,
        },
        {
            "battery_id": "E",
            "is_evaluated": True,
            "prediction_count": 3,
            "reference_start_context_flag": True,
            "reference_context_only": False,
            "source_quality_issue": True,
            "trajectory_continuity_issue": True,
            "evaluation_coverage_issue": False,
            "structural_or_coverage_issue": True,
            "disproportionate_error_influence": False,
            "context_reasons": "first_target_not_near_rated_capacity",
            "structural_review_reasons": "invalid_capacity_quarantine;cycle_index_gap",
            "influence_review_reasons": "",
            "persistence_mae": 2.0,
            "ridge_mae": 3.0,
            "ridge_minus_persistence_mae": 1.0,
        },
        {
            "battery_id": "F",
            "is_evaluated": False,
            "prediction_count": 0,
            "reference_start_context_flag": True,
            "reference_context_only": False,
            "source_quality_issue": False,
            "trajectory_continuity_issue": False,
            "evaluation_coverage_issue": True,
            "structural_or_coverage_issue": True,
            "disproportionate_error_influence": False,
            "context_reasons": "first_target_not_near_rated_capacity",
            "structural_review_reasons": "no_exact_horizon_forecast_rows",
            "influence_review_reasons": "",
            "persistence_mae": None,
            "ridge_mae": None,
            "ridge_minus_persistence_mae": None,
        },
    ]
    return pd.DataFrame(rows)


def _summary() -> dict[str, object]:
    return {
        "battery_count": 6,
        "evaluated_battery_count": 5,
        "unevaluated_battery_count": 1,
        "reference_start_context_battery_count": 6,
        "reference_context_only_battery_count": 1,
        "source_quality_issue_battery_count": 2,
        "trajectory_continuity_issue_battery_count": 2,
        "structural_or_coverage_issue_battery_count": 4,
        "disproportionate_error_influence_battery_count": 3,
        "predictive_evidence_level": "Unsupported",
    }


def test_focused_review_queue_intersects_observed_dimensions_without_filtering() -> None:
    result = build_nasa_focused_review_queue(
        battery_profile=_profile(),
        protocol_audit_summary=_summary(),
    )
    queue = result["review_queue"].set_index("battery_id")
    summary = result["summary"]

    assert len(queue) == 6
    assert queue.loc["F", "review_tier"] == 1
    assert queue.loc["B", "review_tier"] == 2
    assert queue.loc["C", "review_tier"] == 3
    assert queue.loc["D", "review_tier"] == 4
    assert queue.loc["E", "review_tier"] == 5
    assert queue.loc["A", "review_tier"] == 7
    assert queue.loc["C", "error_pattern"] == "ridge_better_for_this_battery"
    assert queue.loc["B", "error_pattern"] == "persistence_better_for_this_battery"
    assert not queue["causal_attribution_established"].any()
    assert not queue["battery_removal_authorized"].any()

    assert summary["influence_with_source_quality_count"] == 1
    assert summary["influence_with_trajectory_continuity_count"] == 1
    assert summary["influence_with_structural_or_coverage_count"] == 2
    assert summary["influence_without_structural_or_coverage_count"] == 1
    assert summary["structural_or_coverage_without_influence_count"] == 2
    assert summary["unevaluated_battery_ids"] == ["F"]
    assert summary["source_quality_plus_influence_battery_ids"] == ["B"]
    assert summary["trajectory_continuity_plus_influence_battery_ids"] == ["C"]
    assert summary["influence_without_structural_or_coverage_battery_ids"] == ["D"]
    assert summary["predictive_evidence_level"] == "Unsupported"
    assert summary["causal_attribution_established"] is False


def test_focused_review_queue_rejects_mixed_run_summary_counts() -> None:
    summary = _summary()
    summary["battery_count"] = 7
    with pytest.raises(ValueError, match="summary/profile count mismatch"):
        build_nasa_focused_review_queue(
            battery_profile=_profile(),
            protocol_audit_summary=summary,
        )


def test_focused_review_queue_rejects_evaluation_inconsistency() -> None:
    profile = _profile()
    profile.loc[profile["battery_id"] == "F", "prediction_count"] = 1
    with pytest.raises(ValueError, match="evaluation status conflicts"):
        build_nasa_focused_review_queue(
            battery_profile=profile,
            protocol_audit_summary=_summary(),
        )


def test_focused_review_queue_rejects_invalid_boolean_cells() -> None:
    profile = _profile()
    profile.loc[profile["battery_id"] == "A", "source_quality_issue"] = "tru"
    with pytest.raises(ValueError, match="invalid boolean values"):
        build_nasa_focused_review_queue(
            battery_profile=profile,
            protocol_audit_summary=_summary(),
        )


def _write_existing_audit(output: Path) -> None:
    tables = output / "tables"
    reports = output / "reports"
    tables.mkdir(parents=True)
    reports.mkdir(parents=True)
    profile_path = tables / "nasa_protocol_battery_profile.csv"
    audit_path = reports / "nasa_protocol_audit.json"
    profile = _profile()
    summary = _summary()
    profile.to_csv(profile_path, index=False)
    audit_path.write_text(json.dumps(summary), encoding="utf-8")
    manifest = {
        "artifact_paths": [
            "tables/nasa_protocol_battery_profile.csv",
            "reports/nasa_protocol_audit.json",
        ],
        "artifact_checksums": {
            "tables/nasa_protocol_battery_profile.csv": file_sha256(profile_path),
            "reports/nasa_protocol_audit.json": file_sha256(audit_path),
        },
        "nasa_protocol_aware_posthoc_audit": summary,
    }
    (output / "run_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )


def test_existing_audit_queue_persists_outputs_and_updates_manifest(tmp_path: Path) -> None:
    output = tmp_path / "analysis"
    _write_existing_audit(output)

    result = audit_nasa_focused_review_queue(analysis_output=output)

    for path in result["outputs"].values():
        assert Path(path).is_file()
    queue = pd.read_csv(result["outputs"]["review_queue"])
    assert len(queue) == 6
    assert queue.iloc[0]["battery_id"] == "F"
    assert result["summary"]["source_run_manifest"] == "run_manifest.json"
    assert set(result["summary"]["source_artifact_checksums"]) == {
        "tables/nasa_protocol_battery_profile.csv",
        "reports/nasa_protocol_audit.json",
    }
    manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
    assert "nasa_focused_review_queue" in manifest
    assert "tables/nasa_protocol_review_queue.csv" in manifest["artifact_checksums"]
    assert "reports/nasa_protocol_review_queue.json" in manifest["artifact_checksums"]


def test_existing_audit_queue_rejects_same_count_mixed_run_artifact(tmp_path: Path) -> None:
    output = tmp_path / "analysis"
    _write_existing_audit(output)
    profile_path = output / "tables" / "nasa_protocol_battery_profile.csv"
    profile = pd.read_csv(profile_path)
    profile.loc[profile["battery_id"] == "B", "persistence_mae"] = 11.0
    profile.loc[profile["battery_id"] == "B", "ridge_minus_persistence_mae"] = 1.0
    profile.to_csv(profile_path, index=False)

    with pytest.raises(ValueError, match="source artifact checksum mismatch"):
        audit_nasa_focused_review_queue(analysis_output=output)


def test_review_queue_script_has_valid_powershell_syntax() -> None:
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


def test_review_queue_script_executes_existing_audit(tmp_path: Path) -> None:
    executable = shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell is not installed in this environment")
    output = tmp_path / "analysis"
    _write_existing_audit(output)

    completed = subprocess.run(
        [
            executable,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(SCRIPT),
            "-AnalysisOutput",
            str(output),
        ],
        cwd=PROJECT_ROOT,
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "without import or model fitting" in completed.stdout
    assert "review_status: Diagnostic" in completed.stdout
    assert "unevaluated_battery_ids: F" in completed.stdout
    assert "source_quality_plus_influence_battery_ids: B" in completed.stdout
