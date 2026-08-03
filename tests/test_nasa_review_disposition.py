from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from platform_core.battery_intelligence.common import canonical_json, file_sha256
from platform_core.battery_intelligence.nasa_review_disposition import (
    finalize_nasa_review_disposition,
    initialize_nasa_review_disposition,
)


def _write_evidence(root: Path) -> None:
    tables = root / "tables"
    reports = root / "reports"
    tables.mkdir(parents=True)
    reports.mkdir(parents=True)
    evidence = pd.DataFrame(
        [
            {
                "review_order": 1,
                "battery_id": "B0052",
                "review_tier": 1,
                "recommended_action_class": "evaluation_coverage_review",
                "review_check_codes": "verify_battery_and_source_identity;inspect_exact_horizon_coverage",
                "predictive_evidence_level": "Unsupported",
            },
            {
                "review_order": 2,
                "battery_id": "B0050",
                "review_tier": 2,
                "recommended_action_class": "source_quality_and_error_influence_review",
                "review_check_codes": "verify_battery_and_source_identity;inspect_source_quality_and_quarantine_records;inspect_high_error_rows_without_filtering",
                "predictive_evidence_level": "Unsupported",
            },
        ]
    )
    evidence_path = tables / "nasa_protocol_review_evidence.csv"
    report_path = reports / "nasa_protocol_review_evidence.json"
    evidence.to_csv(evidence_path, index=False, lineterminator="\n")
    report_path.write_text(
        canonical_json(
            {
                "summary": {
                    "packet_count": 2,
                    "review_status": "Diagnostic",
                    "predictive_evidence_level": "Unsupported",
                },
                "batteries": evidence.to_dict(orient="records"),
            }
        ),
        encoding="utf-8",
    )
    manifest = {
        "artifact_paths": [
            "tables/nasa_protocol_review_evidence.csv",
            "reports/nasa_protocol_review_evidence.json",
        ],
        "artifact_checksums": {
            "tables/nasa_protocol_review_evidence.csv": file_sha256(evidence_path),
            "reports/nasa_protocol_review_evidence.json": file_sha256(report_path),
        },
    }
    (root / "run_manifest.json").write_text(
        canonical_json(manifest), encoding="utf-8"
    )


def test_initialize_disposition_preserves_evidence_identity(tmp_path: Path) -> None:
    _write_evidence(tmp_path)
    result = initialize_nasa_review_disposition(analysis_output=tmp_path)
    worksheet = pd.read_csv(
        result["outputs"]["review_disposition_worksheet"], keep_default_na=False
    )

    assert result["summary"]["battery_count"] == 2
    assert result["summary"]["priority_battery_count"] == 2
    assert worksheet["battery_id"].tolist() == ["B0052", "B0050"]
    assert worksheet["review_status"].tolist() == ["pending", "pending"]
    assert worksheet["source_evidence_sha256"].nunique() == 1
    assert bool(result["summary"]["scientific_claim_changed"]) is False


def test_initialize_refuses_to_overwrite_manual_work_by_default(tmp_path: Path) -> None:
    _write_evidence(tmp_path)
    initialize_nasa_review_disposition(analysis_output=tmp_path)
    with pytest.raises(FileExistsError, match="already exists"):
        initialize_nasa_review_disposition(analysis_output=tmp_path)


def test_finalize_disposition_writes_bound_complete_snapshot(tmp_path: Path) -> None:
    _write_evidence(tmp_path)
    initialized = initialize_nasa_review_disposition(analysis_output=tmp_path)
    path = Path(initialized["outputs"]["review_disposition_worksheet"])
    worksheet = pd.read_csv(path, keep_default_na=False)
    worksheet.loc[worksheet["battery_id"] == "B0052", [
        "review_status",
        "conclusion_code",
        "reviewer",
        "reviewed_at_utc",
        "rationale",
    ]] = [
        "completed",
        "inconclusive",
        "reviewer-a",
        "2026-08-03T05:00:00Z",
        "No exact-horizon rows exist, so the available packet cannot resolve performance.",
    ]
    worksheet.loc[worksheet["battery_id"] == "B0050", [
        "review_status",
        "conclusion_code",
        "reviewer",
        "reviewed_at_utc",
        "evidence_refs",
        "rationale",
        "follow_up_action",
    ]] = [
        "follow_up_required",
        "source_quality_issue_confirmed",
        "reviewer-a",
        "2026-08-03T05:05:00Z",
        "excluded_source_operation_indices=53;top_ridge_error_rows=row=10",
        "The quarantined source operation is confirmed; causality for model error is not established.",
        "Inspect the original MAT operation and protocol metadata.",
    ]
    worksheet.to_csv(path, index=False, lineterminator="\n")

    result = finalize_nasa_review_disposition(analysis_output=tmp_path)
    summary = result["summary"]
    final = pd.read_csv(result["outputs"]["review_disposition_final"], keep_default_na=False)
    manifest = json.loads((tmp_path / "run_manifest.json").read_text(encoding="utf-8"))

    assert summary["disposition_status"] == "complete"
    assert summary["reviewed_battery_count"] == 2
    assert summary["pending_priority_battery_ids"] == []
    assert summary["predictive_evidence_level"] == "Unsupported"
    assert bool(summary["scientific_claim_changed"]) is False
    assert bool(summary["causal_attribution_established"]) is False
    assert final["battery_id"].tolist() == ["B0052", "B0050"]
    assert "nasa_protocol_review_disposition" in manifest
    assert "reports/nasa_protocol_review_disposition.json" in manifest["artifact_checksums"]


def test_finalize_rejects_immutable_identity_change(tmp_path: Path) -> None:
    _write_evidence(tmp_path)
    initialized = initialize_nasa_review_disposition(analysis_output=tmp_path)
    path = Path(initialized["outputs"]["review_disposition_worksheet"])
    worksheet = pd.read_csv(path, keep_default_na=False)
    worksheet.loc[0, "battery_id"] = "B9999"
    worksheet.to_csv(path, index=False, lineterminator="\n")

    with pytest.raises(ValueError, match="immutable column changed: battery_id"):
        finalize_nasa_review_disposition(analysis_output=tmp_path)


def test_finalize_requires_evidence_and_follow_up_for_confirmed_issue(
    tmp_path: Path,
) -> None:
    _write_evidence(tmp_path)
    initialized = initialize_nasa_review_disposition(analysis_output=tmp_path)
    path = Path(initialized["outputs"]["review_disposition_worksheet"])
    worksheet = pd.read_csv(path, keep_default_na=False)
    worksheet.loc[0, [
        "review_status",
        "conclusion_code",
        "reviewer",
        "reviewed_at_utc",
        "rationale",
    ]] = [
        "follow_up_required",
        "evaluation_coverage_issue_confirmed",
        "reviewer-a",
        "2026-08-03T05:00:00Z",
        "Coverage is absent.",
    ]
    worksheet.to_csv(path, index=False, lineterminator="\n")

    with pytest.raises(ValueError, match="evidence_refs required"):
        finalize_nasa_review_disposition(analysis_output=tmp_path)
