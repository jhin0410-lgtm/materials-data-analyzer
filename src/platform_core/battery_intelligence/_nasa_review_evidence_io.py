"""Persistence for manifest-bound NASA PCoE review evidence."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ._nasa_review_evidence_binding import _bindings
from ._nasa_review_evidence_content import _bind_import_content
from ._nasa_review_evidence_render import _markdown, _records
from ._nasa_review_evidence_table import build_nasa_review_evidence_table
from ._nasa_review_evidence_validation import _ids
from .common import canonical_json, file_sha256


def audit_nasa_review_evidence(
    *,
    import_output: str | Path,
    analysis_output: str | Path,
) -> dict[str, Any]:
    """Persist battery-level review evidence from existing official-run artifacts."""
    import_root = Path(import_output)
    analysis_root = Path(analysis_output)
    tables = analysis_root / "tables"
    reports = analysis_root / "reports"
    analysis_paths = {
        "tables/nasa_protocol_review_queue.csv": tables
        / "nasa_protocol_review_queue.csv",
        "reports/nasa_protocol_review_queue.json": reports
        / "nasa_protocol_review_queue.json",
        "tables/validation_predictions.csv": tables / "validation_predictions.csv",
        "tables/nasa_protocol_battery_profile.csv": tables
        / "nasa_protocol_battery_profile.csv",
        "reports/nasa_protocol_audit.json": reports / "nasa_protocol_audit.json",
    }
    import_paths = {
        "nasa_pcoe_protocol_summary.csv": import_root
        / "nasa_pcoe_protocol_summary.csv",
        "nasa_pcoe_source_inventory.csv": import_root
        / "nasa_pcoe_source_inventory.csv",
        "nasa_pcoe_excluded_operations.csv": import_root
        / "nasa_pcoe_excluded_operations.csv",
    }
    missing = [
        name
        for name, path in {**analysis_paths, **import_paths}.items()
        if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "NASA review evidence missing required artifacts: " + ", ".join(missing)
        )
    binding = _bindings(import_root, analysis_root, analysis_paths, import_paths)
    queue = pd.read_csv(analysis_paths["tables/nasa_protocol_review_queue.csv"])
    content_binding = _bind_import_content(
        queue,
        pd.read_csv(import_paths["nasa_pcoe_protocol_summary.csv"]),
        pd.read_csv(import_paths["nasa_pcoe_source_inventory.csv"]),
    )
    all_exclusions = pd.read_csv(import_paths["nasa_pcoe_excluded_operations.csv"])
    if not all_exclusions.empty:
        all_exclusion_ids = set(
            _ids(all_exclusions, context="NASA excluded operations")
        )
        unknown_exclusion_ids = sorted(
            all_exclusion_ids - content_binding["inventory_battery_ids"]
        )
        if unknown_exclusion_ids:
            raise ValueError(
                "excluded operations contain batteries absent from source inventory: "
                + ", ".join(unknown_exclusion_ids)
            )
        queue_exclusions = all_exclusions[
            all_exclusions["battery_id"].astype(str).str.strip().isin(
                content_binding["queue_battery_ids"]
            )
        ].copy()
    else:
        queue_exclusions = all_exclusions.copy()
    result = build_nasa_review_evidence_table(
        review_queue=queue,
        excluded_operations=queue_exclusions,
        validation_predictions=pd.read_csv(
            analysis_paths["tables/validation_predictions.csv"]
        ),
        predictive_evidence_level=str(
            binding["queue_summary"].get("predictive_evidence_level", "Inconclusive")
        ),
    )
    summary = result["summary"]
    ignored_inventory_only = sorted(content_binding["inventory_only_battery_ids"])
    summary["ignored_inventory_only_battery_ids"] = ignored_inventory_only
    summary["ignored_inventory_only_excluded_operation_count"] = int(
        len(all_exclusions) - len(queue_exclusions)
    )
    summary["retrieval_receipt_verified"] = bool(
        binding["import_manifest"].get("retrieval_receipt_verified", False)
    )
    summary["source_analysis_run_manifest"] = "run_manifest.json"
    summary["source_import_manifest"] = "nasa_pcoe_import_manifest.json"
    summary["source_import_binding"] = binding["import_binding"]
    summary["source_analysis_artifact_checksums"] = binding["verified_analysis"]
    summary["source_import_artifact_checksums"] = binding["verified_import"]

    table_path = tables / "nasa_protocol_review_evidence.csv"
    report_path = reports / "nasa_protocol_review_evidence.json"
    markdown_path = reports / "nasa_protocol_review_evidence.md"
    result["table"].to_csv(table_path, index=False, lineterminator="\n")
    report_path.write_text(
        canonical_json({"summary": summary, "batteries": _records(result["table"])}),
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown(summary, result["table"]), encoding="utf-8")

    manifest_path = analysis_root / "run_manifest.json"
    manifest = binding["analysis_manifest"]
    manifest["nasa_protocol_review_evidence"] = summary
    paths = [table_path, report_path, markdown_path]
    relative = [path.relative_to(analysis_root).as_posix() for path in paths]
    manifest["artifact_paths"] = sorted(
        set(manifest.get("artifact_paths", [])) | set(relative)
    )
    checksums = dict(manifest.get("artifact_checksums", {}))
    for path, name in zip(paths, relative, strict=True):
        checksums[name] = file_sha256(path)
    manifest["artifact_checksums"] = checksums
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
    return {
        "summary": summary,
        "outputs": {
            "review_evidence_table": str(table_path),
            "review_evidence_report": str(report_path),
            "review_evidence_markdown": str(markdown_path),
        },
    }
