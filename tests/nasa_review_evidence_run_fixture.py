from __future__ import annotations

from pathlib import Path

from platform_core.battery_intelligence.common import canonical_json, file_sha256
from platform_core.battery_intelligence.nasa_import_binding import (
    bind_nasa_import_to_analysis,
)
from nasa_review_evidence_queue_fixture import _queue
from nasa_review_evidence_source_fixtures import (
    _excluded,
    _inventory,
    _predictions,
    _protocol,
)


def _write_run(
    import_output: Path,
    analysis_output: Path,
    *,
    inventory=None,
    excluded=None,
    import_input: dict[str, object] | None = None,
) -> None:
    tables = analysis_output / "tables"
    reports = analysis_output / "reports"
    import_output.mkdir(parents=True)
    tables.mkdir(parents=True)
    reports.mkdir(parents=True)

    queue_path = tables / "nasa_protocol_review_queue.csv"
    profile_path = tables / "nasa_protocol_battery_profile.csv"
    predictions_path = tables / "validation_predictions.csv"
    queue_summary_path = reports / "nasa_protocol_review_queue.json"
    protocol_audit_path = reports / "nasa_protocol_audit.json"
    protocol_path = import_output / "nasa_pcoe_protocol_summary.csv"
    inventory_path = import_output / "nasa_pcoe_source_inventory.csv"
    excluded_path = import_output / "nasa_pcoe_excluded_operations.csv"

    queue = _queue()
    queue.to_csv(queue_path, index=False)
    queue.to_csv(profile_path, index=False)
    _predictions().to_csv(predictions_path, index=False)
    _protocol().to_csv(protocol_path, index=False)
    (inventory if inventory is not None else _inventory()).to_csv(
        inventory_path, index=False
    )
    (excluded if excluded is not None else _excluded()).to_csv(
        excluded_path, index=False
    )

    protocol_audit = {
        "protocol_audit_status": "Diagnostic",
        "predictive_evidence_level": "Unsupported",
    }
    protocol_audit_path.write_text(canonical_json(protocol_audit), encoding="utf-8")
    queue_summary = {
        "review_status": "Diagnostic",
        "predictive_evidence_level": "Unsupported",
        "source_artifact_checksums": {
            "tables/nasa_protocol_battery_profile.csv": file_sha256(profile_path),
            "reports/nasa_protocol_audit.json": file_sha256(protocol_audit_path),
        },
    }
    queue_summary_path.write_text(canonical_json(queue_summary), encoding="utf-8")
    analysis_manifest = {
        "nasa_protocol_aware_posthoc_audit": protocol_audit,
        "nasa_focused_review_queue": queue_summary,
        "artifact_paths": [],
        "artifact_checksums": {
            "tables/nasa_protocol_review_queue.csv": file_sha256(queue_path),
            "reports/nasa_protocol_review_queue.json": file_sha256(
                queue_summary_path
            ),
            "tables/validation_predictions.csv": file_sha256(predictions_path),
            "tables/nasa_protocol_battery_profile.csv": file_sha256(profile_path),
            "reports/nasa_protocol_audit.json": file_sha256(protocol_audit_path),
        },
    }
    (analysis_output / "run_manifest.json").write_text(
        canonical_json(analysis_manifest), encoding="utf-8"
    )
    import_manifest = {
        "retrieval_receipt_verified": True,
        "input": import_input or {"sha256": "fixture-import-sha256"},
        "output_sha256": {
            "protocol_summary": file_sha256(protocol_path),
            "source_inventory": file_sha256(inventory_path),
            "excluded_operations": file_sha256(excluded_path),
        },
    }
    (import_output / "nasa_pcoe_import_manifest.json").write_text(
        canonical_json(import_manifest), encoding="utf-8"
    )
    binding = bind_nasa_import_to_analysis(
        import_output=import_output,
        analysis_output=analysis_output,
    )
    assert binding["binding_status"] == "verified"
    assert binding["binding_written"] is True
