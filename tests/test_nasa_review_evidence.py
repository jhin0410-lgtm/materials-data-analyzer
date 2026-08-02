from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from platform_core.battery_intelligence.common import canonical_json, file_sha256
from platform_core.battery_intelligence.nasa_review_evidence import (
    _bind_import_content,
    audit_nasa_review_evidence,
    build_nasa_review_evidence_table,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_nasa_pcoe_review_evidence.ps1"


def _queue() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "battery_id": "A",
                "review_order": 1,
                "review_tier": 2,
                "review_tier_label": "source_quality_plus_error_influence",
                "review_dimensions": "source_quality;error_influence;rated_reference_context",
                "is_evaluated": True,
                "prediction_count": 2,
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
                "persistence_mae": 1.5,
                "ridge_mae": 2.5,
                "ridge_minus_persistence_mae": 1.0,
                "excluded_discharge_operation_count": 1,
                "invalid_capacity_operation_count": 1,
                "cycle_gap_count": 0,
                "maximum_absolute_adjacent_target_change_percent": 5.0,
                "ambient_temperature_median_c": 25.0,
                "imported_discharge_operation_count": 4,
            },
            {
                "battery_id": "B",
                "review_order": 2,
                "review_tier": 1,
                "review_tier_label": "evaluation_coverage",
                "review_dimensions": "evaluation_coverage;rated_reference_context",
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
                "excluded_discharge_operation_count": 0,
                "invalid_capacity_operation_count": 0,
                "cycle_gap_count": 0,
                "maximum_absolute_adjacent_target_change_percent": 2.0,
                "ambient_temperature_median_c": 4.0,
                "imported_discharge_operation_count": 3,
            },
        ]
    )


def _predictions() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "battery_id": "A",
                "actual": 90.0,
                "persistence_prediction": 91.0,
                "ridge_prediction": 92.0,
            },
            {
                "battery_id": "A",
                "actual": 80.0,
                "persistence_prediction": 82.0,
                "ridge_prediction": 83.0,
            },
        ]
    )


def _excluded() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_location": "archive.zip!A.mat",
                "battery_id": "A",
                "source_operation_index": 5,
                "cycle_index": 3,
                "capacity_issue": "nonpositive",
                "observed_value": "nonpositive:0.0",
                "severity": "warning",
                "code": "invalid_discharge_capacity_excluded",
                "message": "No value was imputed.",
            }
        ]
    )


def _protocol() -> pd.DataFrame:
    return _queue()[["battery_id", "ambient_temperature_median_c"]].copy()


def _inventory() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "battery_id": "A",
                "skip_reason": "",
                "imported_discharge_operation_count": 4,
                "excluded_discharge_operation_count": 1,
                "invalid_capacity_operation_count": 1,
            },
            {
                "battery_id": "B",
                "skip_reason": "",
                "imported_discharge_operation_count": 3,
                "excluded_discharge_operation_count": 0,
                "invalid_capacity_operation_count": 0,
            },
            {
                "battery_id": "A",
                "skip_reason": "duplicate_identical_source_copy",
                "imported_discharge_operation_count": 4,
                "excluded_discharge_operation_count": 1,
                "invalid_capacity_operation_count": 1,
            },
        ]
    )


def test_review_evidence_links_source_and_model_rows_without_filtering() -> None:
    result = build_nasa_review_evidence_table(
        review_queue=_queue(),
        excluded_operations=_excluded(),
        validation_predictions=_predictions(),
        predictive_evidence_level="Unsupported",
    )
    table = result["table"].set_index("battery_id")
    summary = result["summary"]

    assert len(table) == 2
    assert summary["packet_count"] == 2
    assert summary["priority_battery_ids"] == ["A", "B"]
    assert summary["linked_excluded_operation_count"] == 1
    assert summary["linked_validation_prediction_count"] == 2
    assert table.loc["A", "excluded_cycle_indices"] == "3"
    assert table.loc["A", "excluded_capacity_issue_counts"] == "nonpositive:1"
    assert "row=3" in table.loc["A", "top_ridge_error_rows"]
    assert table.loc["A", "recommended_action_class"] == (
        "source_quality_and_error_influence_review"
    )
    assert table.loc["B", "recommended_action_class"] == (
        "evaluation_coverage_review"
    )
    assert bool(table.loc["A", "battery_removal_authorized"]) is False
    assert bool(table.loc["A", "data_repair_authorized"]) is False
    assert summary["predictive_evidence_level"] == "Unsupported"


def test_review_evidence_rejects_prediction_count_mismatch() -> None:
    queue = _queue()
    queue.loc[queue["battery_id"] == "A", "prediction_count"] = 3
    with pytest.raises(ValueError, match="prediction counts"):
        build_nasa_review_evidence_table(
            review_queue=queue,
            excluded_operations=_excluded(),
            validation_predictions=_predictions(),
            predictive_evidence_level="Unsupported",
        )


def test_review_evidence_rejects_import_content_mismatch() -> None:
    protocol = _protocol()
    protocol.loc[protocol["battery_id"] == "A", "ambient_temperature_median_c"] = 40.0
    with pytest.raises(ValueError, match="content mismatch"):
        _bind_import_content(_queue(), protocol, _inventory())


def _write_run(import_output: Path, analysis_output: Path) -> None:
    tables = analysis_output / "tables"
    reports = analysis_output / "reports"
    import_output.mkdir(parents=True)
    tables.mkdir(parents=True)
    reports.mkdir(parents=True)

    queue_path = tables / "nasa_protocol_review_queue.csv"
    predictions_path = tables / "validation_predictions.csv"
    queue_summary_path = reports / "nasa_protocol_review_queue.json"
    protocol_path = import_output / "nasa_pcoe_protocol_summary.csv"
    inventory_path = import_output / "nasa_pcoe_source_inventory.csv"
    excluded_path = import_output / "nasa_pcoe_excluded_operations.csv"
    _queue().to_csv(queue_path, index=False)
    _predictions().to_csv(predictions_path, index=False)
    _protocol().to_csv(protocol_path, index=False)
    _inventory().to_csv(inventory_path, index=False)
    _excluded().to_csv(excluded_path, index=False)

    queue_summary = {
        "review_status": "Diagnostic",
        "predictive_evidence_level": "Unsupported",
    }
    queue_summary_path.write_text(canonical_json(queue_summary), encoding="utf-8")
    analysis_manifest = {
        "nasa_protocol_aware_posthoc_audit": {"protocol_audit_status": "Diagnostic"},
        "nasa_focused_review_queue": queue_summary,
        "artifact_paths": [],
        "artifact_checksums": {
            "tables/nasa_protocol_review_queue.csv": file_sha256(queue_path),
            "reports/nasa_protocol_review_queue.json": file_sha256(
                queue_summary_path
            ),
            "tables/validation_predictions.csv": file_sha256(predictions_path),
        },
    }
    (analysis_output / "run_manifest.json").write_text(
        canonical_json(analysis_manifest), encoding="utf-8"
    )
    import_manifest = {
        "retrieval_receipt_verified": True,
        "output_sha256": {
            "protocol_summary": file_sha256(protocol_path),
            "source_inventory": file_sha256(inventory_path),
            "excluded_operations": file_sha256(excluded_path),
        },
    }
    (import_output / "nasa_pcoe_import_manifest.json").write_text(
        canonical_json(import_manifest), encoding="utf-8"
    )


def test_review_evidence_persists_manifest_bound_outputs(tmp_path: Path) -> None:
    import_output = tmp_path / "import"
    analysis_output = tmp_path / "analysis"
    _write_run(import_output, analysis_output)

    result = audit_nasa_review_evidence(
        import_output=import_output,
        analysis_output=analysis_output,
    )
    manifest = json.loads(
        (analysis_output / "run_manifest.json").read_text(encoding="utf-8")
    )
    report = json.loads(
        (
            analysis_output / "reports" / "nasa_protocol_review_evidence.json"
        ).read_text(encoding="utf-8")
    )

    assert result["summary"]["retrieval_receipt_verified"] is True
    assert report["summary"]["packet_count"] == 2
    assert len(report["batteries"]) == 2
    assert "nasa_protocol_review_evidence" in manifest
    assert "tables/nasa_protocol_review_evidence.csv" in manifest[
        "artifact_checksums"
    ]
    for path in result["outputs"].values():
        assert Path(path).is_file()


def test_review_evidence_rejects_tampered_import_artifact(tmp_path: Path) -> None:
    import_output = tmp_path / "import"
    analysis_output = tmp_path / "analysis"
    _write_run(import_output, analysis_output)
    protocol_path = import_output / "nasa_pcoe_protocol_summary.csv"
    protocol_path.write_text(
        protocol_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="checksum mismatch"):
        audit_nasa_review_evidence(
            import_output=import_output,
            analysis_output=analysis_output,
        )


def test_review_evidence_script_has_valid_powershell_syntax() -> None:
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


def test_review_evidence_script_executes_existing_artifacts(tmp_path: Path) -> None:
    executable = shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell is not installed in this environment")
    import_output = tmp_path / "import"
    analysis_output = tmp_path / "analysis"
    _write_run(import_output, analysis_output)

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
    assert "without model fitting or data repair" in completed.stdout
    assert "review_evidence_status: Diagnostic" in completed.stdout
    assert "priority_battery_ids: A,B" in completed.stdout
    assert (
        analysis_output / "reports" / "nasa_protocol_review_evidence.json"
    ).is_file()
