from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from platform_core.battery_intelligence.nasa_review_evidence import (
    audit_nasa_review_evidence,
)
from nasa_review_evidence_run_fixture import _write_run
from nasa_review_evidence_source_fixtures import _excluded, _inventory


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
    by_id = {row["battery_id"]: row for row in report["batteries"]}
    assert by_id["B"]["influence_review_reasons"] == ""
    assert by_id["A"]["causal_attribution_established"] is False
    assert by_id["A"]["battery_removal_authorized"] is False
    assert by_id["A"]["data_repair_authorized"] is False
    assert manifest["nasa_import_artifact_binding"]["binding_status"] == "verified"
    markdown = (
        analysis_output / "reports" / "nasa_protocol_review_evidence.md"
    ).read_text(encoding="utf-8")
    assert "archive.zip!A.mat" in markdown
    assert "Source operation indices: `5`" in markdown
    assert "Highest Ridge-error rows:" in markdown
    assert "row=3" in markdown
    assert "nasa_protocol_review_evidence" in manifest
    assert "tables/nasa_protocol_review_evidence.csv" in manifest[
        "artifact_checksums"
    ]
    for path in result["outputs"].values():
        assert Path(path).is_file()


def test_review_evidence_allows_inventory_only_battery_and_records_ignored_evidence(
    tmp_path: Path,
) -> None:
    inventory = pd.concat(
        [
            _inventory(),
            pd.DataFrame(
                [
                    {
                        "battery_id": "C",
                        "skip_reason": "no_valid_discharge_operations",
                        "imported_discharge_operation_count": 0,
                        "excluded_discharge_operation_count": 1,
                        "invalid_capacity_operation_count": 1,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    excluded = pd.concat(
        [
            _excluded(),
            pd.DataFrame(
                [
                    {
                        "source_location": "archive.zip!C.mat",
                        "battery_id": "C",
                        "source_operation_index": 1,
                        "cycle_index": 1,
                        "capacity_issue": "nonfinite",
                        "observed_value": "nonfinite:nan",
                        "severity": "warning",
                        "code": "invalid_discharge_capacity_excluded",
                        "message": "No value was imputed.",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    import_output = tmp_path / "import"
    analysis_output = tmp_path / "analysis"
    _write_run(
        import_output,
        analysis_output,
        inventory=inventory,
        excluded=excluded,
    )

    result = audit_nasa_review_evidence(
        import_output=import_output,
        analysis_output=analysis_output,
    )

    assert result["summary"]["packet_count"] == 2
    assert result["summary"]["ignored_inventory_only_battery_ids"] == ["C"]
    assert result["summary"]["ignored_inventory_only_excluded_operation_count"] == 1
