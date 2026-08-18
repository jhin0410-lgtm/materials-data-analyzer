from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from materials_data_analyzer.research_loop.acquisition_record_binding import (
    authenticate_acquisition_record_binding,
)
from materials_data_analyzer.research_loop.nist_mds2_2923_scientific_intake import (
    audit_mds2_2923,
    compact_micrograph_manifest,
)
from materials_data_analyzer.research_loop.scientific_review_release import (
    build_review_request,
)


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _package_for_artifact(
    root: Path, artifact_name: str
) -> tuple[Path, dict[str, Any]]:
    matches: list[tuple[Path, dict[str, Any]]] = []
    for receipt_path in sorted(root.glob("packages/*/acquisition_receipt.json")):
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("artifact_path") == artifact_name:
            matches.append((receipt_path.parent, receipt))
    if len(matches) != 1:
        raise RuntimeError(
            f"artifact {artifact_name!r} must resolve to exactly one acquisition "
            f"package; found {len(matches)}"
        )
    return matches[0]


def _authenticated_artifact(
    root: Path, artifact_name: str
) -> tuple[bytes, bytes, dict[str, Any]]:
    package, receipt = _package_for_artifact(root, artifact_name)
    evidence_bytes = (package / artifact_name).read_bytes()
    metadata_bytes = (package / "source_metadata.json").read_bytes()
    manifest_bytes = (package / "acquisition_manifest.json").read_bytes()
    declaration_bytes = (package / "acquisition_declaration.json").read_bytes()
    authenticated = authenticate_acquisition_record_binding(
        evidence_bytes=evidence_bytes,
        acquisition_manifest_bytes=manifest_bytes,
        acquisition_declaration_bytes=declaration_bytes,
    )
    if authenticated["recorded_acquisition_provenance_authenticated"] is not True:
        raise RuntimeError(f"acquisition package failed authentication: {artifact_name}")
    if _sha256(evidence_bytes) != receipt["artifact_sha256"]:
        raise RuntimeError(f"receipt SHA mismatch: {artifact_name}")
    if len(evidence_bytes) != receipt["artifact_size_bytes"]:
        raise RuntimeError(f"receipt size mismatch: {artifact_name}")
    if _sha256(metadata_bytes) != receipt["metadata_sha256"]:
        raise RuntimeError(f"metadata SHA mismatch: {artifact_name}")
    return evidence_bytes, metadata_bytes, receipt


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit authenticated NIST mds2-2923 workbook bytes into bounded IN625 "
            "scientific intake."
        )
    )
    parser.add_argument("--acquisition-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    root = args.acquisition_root.resolve(strict=True)
    workbook_bytes, workbook_metadata, workbook_receipt = _authenticated_artifact(
        root, "Master_TrackList_Measurements.xlsx"
    )
    readme_bytes, readme_metadata, readme_receipt = _authenticated_artifact(
        root, "2923_README.txt"
    )
    if workbook_metadata != readme_metadata:
        raise RuntimeError(
            "README and workbook packages are not bound to identical NERDm metadata"
        )

    report = audit_mds2_2923(
        workbook_bytes=workbook_bytes,
        readme_bytes=readme_bytes,
        nerdm_metadata_bytes=workbook_metadata,
    )
    micrograph_manifest = compact_micrograph_manifest(report)

    semantic_contract = {
        "schema_version": "1.0",
        "candidate_id": "nist-mds2-2923-in625-cross-sections",
        "source_product_id": "mds2-2923",
        "source_workbook_sha256": report["source"]["workbook_sha256"],
        "status": "source_bound_pending_human_scientific_review",
        "row_level_authority": "Data",
        "summary_role": "derived_convenience_view_with_detected_omissions",
        "measurement_semantics": report["measurement_semantics"],
        "allowed_before_human_review": [
            "provenance_audit",
            "schema_audit",
            "replicate_structure_audit",
            "review_preparation",
        ],
        "requested_after_human_review": [
            "scientific_intake",
            "descriptive_analysis",
        ],
        "forbidden_promotions": [
            "cross_machine_pooling_without_comparability_review",
            "machine_setting_power_to_calibrated_actual_power_relabeling",
            "causal_inference",
            "optimization",
            "issue_76_satisfaction",
        ],
        "source_anomaly_count": len(report["source"]["source_anomalies"]),
        "summary_missing_group_count": report["in625_inventory"][
            "summary_missing_group_count"
        ],
        "scientific_status_changed": False,
    }
    lineage = {
        "schema_version": "1.0",
        "candidate_id": "nist-mds2-2923-in625-cross-sections",
        "source_workbook_sha256": report["source"]["workbook_sha256"],
        "measurement_row_count": report["in625_inventory"]["measurement_row_count"],
        "physical_track_count": report["in625_inventory"]["physical_track_count"],
        "physical_track_identity_basis": ["Machine", "Sample Name", "Track No."],
        "measurement_to_track_mapping": [
            {
                "measurement_id": item["measurement_id"],
                "physical_track_id": item["physical_track_id"],
                "workbook_excel_row": item["workbook_excel_row"],
                "micrograph_filepath": item["nerdm_micrograph_filepath"],
                "micrograph_sha256": item["nerdm_micrograph_sha256"],
            }
            for item in report["measurements"]
        ],
        "repeated_measurement_handling": (
            "rows sharing Machine + Sample Name + Track No. remain separate "
            "measurements but contribute one physical-track unit to independence counts"
        ),
        "physical_track_distinctness_source_bound": True,
        "statistical_independence_beyond_source_track_identity_established": False,
        "source_track_metadata_conflicts": report["in625_inventory"][
            "source_track_metadata_conflicts"
        ],
        "scientific_status_changed": False,
    }

    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    report_bytes = _canonical_bytes(report)
    micrograph_manifest_bytes = _canonical_bytes(micrograph_manifest)
    semantic_bytes = _canonical_bytes(semantic_contract)
    lineage_bytes = _canonical_bytes(lineage)

    review_request = build_review_request(
        candidate_id="nist-mds2-2923-in625-cross-sections",
        evidence_artifact_sha256=report["source"]["workbook_sha256"],
        semantic_contract_sha256=_sha256(semantic_bytes),
        lineage_sha256=_sha256(lineage_bytes),
        intake_artifact_sha256=_sha256(report_bytes),
        requested_uses=["scientific_intake", "descriptive_analysis"],
    )

    (output / "scientific_intake_report.json").write_bytes(report_bytes)
    (output / "micrograph_manifest.json").write_bytes(micrograph_manifest_bytes)
    (output / "semantic_contract.json").write_bytes(semantic_bytes)
    (output / "experimental_lineage.json").write_bytes(lineage_bytes)
    (output / "scientific_review_request.json").write_bytes(
        _canonical_bytes(review_request)
    )

    summary = {
        "schema_version": "1.0",
        "workbook_sha256": report["source"]["workbook_sha256"],
        "readme_sha256": report["source"]["readme_sha256"],
        "metadata_sha256": report["source"]["nerdm_metadata_sha256"],
        "workbook_acquisition_manifest_sha256": workbook_receipt[
            "acquisition_manifest_sha256"
        ],
        "readme_acquisition_manifest_sha256": readme_receipt[
            "acquisition_manifest_sha256"
        ],
        "in625_measurement_rows": report["in625_inventory"]["measurement_row_count"],
        "in625_physical_tracks": report["in625_inventory"]["physical_track_count"],
        "data_process_spot_groups": report["in625_inventory"][
            "data_process_spot_group_count"
        ],
        "summary_process_spot_groups": report["in625_inventory"][
            "summary_process_spot_group_count"
        ],
        "summary_missing_groups": report["in625_inventory"][
            "summary_missing_group_count"
        ],
        "summary_missing_measurement_rows": report["in625_inventory"][
            "summary_missing_measurement_row_count"
        ],
        "source_track_metadata_conflicts": report["in625_inventory"][
            "source_track_metadata_conflict_count"
        ],
        "bound_micrographs": report["micrograph_binding"][
            "data_referenced_micrograph_count"
        ],
        "bound_micrograph_total_size_bytes": report["micrograph_binding"][
            "bound_micrograph_total_size_bytes"
        ],
        "issue_76_exact_target_cells_satisfied": report["issue_76"][
            "exact_target_cells_satisfied"
        ],
        "issue_76_eligible": False,
        "review_request_id": review_request["review_request_id"],
        "human_scientific_review_decision_created": False,
        "scientific_support_established": False,
        "scientific_status_changed": False,
    }
    (output / "scientific_intake_summary.json").write_bytes(
        _canonical_bytes(summary)
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
