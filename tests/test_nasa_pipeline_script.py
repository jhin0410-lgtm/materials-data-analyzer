from __future__ import annotations

import csv
import json
import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_nasa_pcoe_battery_pipeline.ps1"


def test_nasa_pipeline_script_runs_import_analysis_and_audits() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'Join-Path $PSScriptRoot ".."' in text
    assert "5_Battery_Data_Set.zip" in text
    assert "retrieval_receipt.json" in text
    assert "materials_data_analyzer.nasa_battery_cli" in text
    assert "materials_data_analyzer.battery_cli" in text
    assert "materials_data_analyzer.nasa_protocol_audit_cli" in text
    assert "[1/3]" in text
    assert "[2/3]" in text
    assert "[3/3]" in text
    assert "--raw-signal-provenance" in text
    assert "--overwrite" in text
    assert "target_reference_method" in text
    assert "target_comparability_flag_battery_count" in text
    assert "source_protocol_review_battery_count" in text
    assert "reference_context_only_battery_count" in text
    assert "structural_or_coverage_issue_battery_count" in text
    assert "diagnostic_reason_counts" in text
    assert "signal_enriched_improvement_percent" in text
    assert "PYTHONPATH" in text


def test_nasa_pipeline_script_has_summary_only_mode() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "[switch]$SummaryOnly" in text
    assert "if (-not $SummaryOnly)" in text
    assert "analysis_recomputed" in text
    assert "protocol_audit_recomputed" in text
    assert "existing import and analysis artifacts will not be recomputed" in text
    assert "battery_diagnostic_priority.csv" in text
    assert "nasa_protocol_audit.json" in text
    assert "protocol_audit_available: False" in text


def _write_required_summary_artifacts(
    import_output: Path,
    analysis_output: Path,
    *,
    include_protocol_audit: bool,
) -> None:
    reports = analysis_output / "reports"
    tables = analysis_output / "tables"
    import_output.mkdir()
    reports.mkdir(parents=True)
    tables.mkdir(parents=True)

    (import_output / "nasa_pcoe_import_manifest.json").write_text(
        json.dumps(
            {
                "target_reference": {
                    "method": "source_rated_capacity_2_ah",
                    "rated_capacity_ah": 2.0,
                },
                "retrieval_receipt_verified": True,
                "imported_discharge_operation_count": 10,
                "excluded_discharge_operation_count": 1,
                "invalid_capacity_operation_count": 1,
            }
        ),
        encoding="utf-8",
    )
    (reports / "target_comparability_audit.json").write_text(
        json.dumps(
            {
                "target_comparability_flag_battery_count": 2,
                "reference_consistency_flag_battery_count": 0,
                "cycle_gap_battery_count": 1,
                "large_adjacent_target_jump_battery_count": 1,
                "outside_plausibility_target_count": 0,
                "pooled_error_stability_status": "unstable_heavy_tail_or_concentrated",
            }
        ),
        encoding="utf-8",
    )
    (reports / "battery_influence_triage.json").write_text(
        json.dumps(
            {
                "source_protocol_review_battery_count": 2,
                "target_or_continuity_flag_battery_count": 2,
                "disproportionate_error_contributor_battery_count": 1,
                "unevaluated_battery_count": 0,
                "model_metric_summary": {
                    "persistence": {
                        "row_weighted_mae": 3.0,
                        "battery_macro_mae": 2.5,
                        "evaluated_battery_count": 2,
                    },
                    "ridge": {
                        "row_weighted_mae": 4.0,
                        "battery_macro_mae": 3.5,
                        "evaluated_battery_count": 2,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    (reports / "scientific_closeout.json").write_text(
        json.dumps({"evidence_level": "Unsupported"}),
        encoding="utf-8",
    )
    (reports / "signal_feature_comparison.json").write_text(
        json.dumps(
            {
                "capacity_only_ridge_mae": 4.2,
                "signal_enriched_ridge_mae": 4.0,
                "improvement_percent": 4.7619,
            }
        ),
        encoding="utf-8",
    )
    if include_protocol_audit:
        (reports / "nasa_protocol_audit.json").write_text(
            json.dumps(
                {
                    "summary": {
                        "protocol_audit_status": "Diagnostic",
                        "predictive_evidence_level": "Unsupported",
                        "reference_start_context_battery_count": 2,
                        "reference_context_only_battery_count": 1,
                        "source_quality_issue_battery_count": 1,
                        "trajectory_continuity_issue_battery_count": 1,
                        "structural_or_coverage_issue_battery_count": 1,
                        "disproportionate_error_influence_battery_count": 1,
                        "ridge_improvement_vs_persistence_percent": -33.3333,
                        "ridge_better_than_persistence_battery_count": 0,
                        "supported_temperature_stratum_count": 1,
                    }
                }
            ),
            encoding="utf-8",
        )

    with (tables / "battery_diagnostic_priority.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["battery_id", "diagnostic_flag_reasons"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "battery_id": "A",
                "diagnostic_flag_reasons": (
                    "first_target_not_near_100_percent;cycle_index_gap"
                ),
            }
        )
        writer.writerow(
            {
                "battery_id": "B",
                "diagnostic_flag_reasons": "first_target_not_near_100_percent",
            }
        )


def _run_summary_only(import_output: Path, analysis_output: Path) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell is not installed in this environment")
    return subprocess.run(
        [
            executable,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(SCRIPT),
            "-SummaryOnly",
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


def test_nasa_pipeline_summary_only_reads_protocol_audit_when_available(
    tmp_path: Path,
) -> None:
    import_output = tmp_path / "import"
    analysis_output = tmp_path / "analysis"
    _write_required_summary_artifacts(
        import_output,
        analysis_output,
        include_protocol_audit=True,
    )

    completed = _run_summary_only(import_output, analysis_output)

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "analysis_recomputed: False" in completed.stdout
    assert "protocol_audit_recomputed: False" in completed.stdout
    assert "protocol_audit_available: True" in completed.stdout
    assert "protocol_audit_status: Diagnostic" in completed.stdout
    assert "reference_context_only_battery_count: 1" in completed.stdout
    assert "structural_or_coverage_issue_battery_count: 1" in completed.stdout
    assert "ridge_improvement_vs_persistence_percent: -33.3333" in completed.stdout
    assert "supported_temperature_stratum_count: 1" in completed.stdout
    assert "first_target_not_near_100_percent: 2" in completed.stdout
    assert "cycle_index_gap: 1" in completed.stdout
    assert "signal_enriched_improvement_percent: 4.7619" in completed.stdout
    assert "evidence_level: Unsupported" in completed.stdout


def test_nasa_pipeline_summary_only_remains_compatible_without_protocol_audit(
    tmp_path: Path,
) -> None:
    import_output = tmp_path / "import"
    analysis_output = tmp_path / "analysis"
    _write_required_summary_artifacts(
        import_output,
        analysis_output,
        include_protocol_audit=False,
    )

    completed = _run_summary_only(import_output, analysis_output)

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "analysis_recomputed: False" in completed.stdout
    assert "protocol_audit_available: False" in completed.stdout
    assert "first_target_not_near_100_percent: 2" in completed.stdout
    assert "evidence_level: Unsupported" in completed.stdout


def test_nasa_pipeline_script_has_valid_powershell_syntax() -> None:
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
