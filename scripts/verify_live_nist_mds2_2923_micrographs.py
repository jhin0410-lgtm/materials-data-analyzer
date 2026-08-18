from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from materials_data_analyzer.research_loop.nist_pdr_acquisition import (
    discover_nist_pdr_candidates,
)
from materials_data_analyzer.research_loop.public_data_acquisition import (
    PublicAcquisitionError,
    acquire_public_artifact,
    plan_public_acquisition_queue,
)

_MIB = 1024 * 1024


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _pinned_metadata(acquisition_root: Path, expected_sha256: str) -> bytes:
    matches = []
    for path in sorted(acquisition_root.glob("packages/*/source_metadata.json")):
        body = path.read_bytes()
        if _sha256(body) == expected_sha256:
            matches.append(body)
    unique = {body for body in matches}
    if len(unique) != 1:
        raise RuntimeError(
            "exact intake NERDm metadata must resolve from acquisition packages"
        )
    return unique.pop()


def _load_report(manifest_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    report_path = manifest_path.parent / "scientific_intake_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    source = report.get("source", {})
    if source.get("product_id") != "mds2-2923":
        raise RuntimeError("scientific intake report is not mds2-2923")
    if source.get("workbook_sha256") != manifest["workbook_sha256"]:
        raise RuntimeError("manifest/report workbook SHA-256 differs")
    if source.get("nerdm_metadata_sha256") != manifest["nerdm_metadata_sha256"]:
        raise RuntimeError("manifest/report NERDm metadata SHA-256 differs")
    boundary = report.get("scientific_boundary", {})
    if boundary.get("scientific_status_changed") is not False:
        raise RuntimeError("scientific intake report cannot change scientific status")
    return report


def _explicit_sample_blocks(
    *,
    files: list[dict[str, Any]],
    report: dict[str, Any],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    measurements = report.get("measurements")
    if not isinstance(measurements, list) or not measurements:
        raise RuntimeError("scientific intake report contains no measurements")
    by_measurement = {
        item["measurement_id"]: item
        for item in measurements
        if isinstance(item, dict) and isinstance(item.get("measurement_id"), str)
    }
    if len(by_measurement) != len(measurements):
        raise RuntimeError("scientific intake report repeats measurement ids")

    blocks: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for declared in files:
        measurement = by_measurement.get(declared["measurement_id"])
        if measurement is None:
            raise RuntimeError(
                f"manifest measurement missing from intake report: {declared['measurement_id']}"
            )
        if measurement["physical_track_id"] != declared["physical_track_id"]:
            raise RuntimeError("manifest/report physical-track identity differs")
        if measurement["nerdm_micrograph_filepath"] != declared["filepath"]:
            raise RuntimeError("manifest/report micrograph filepath differs")
        source_identity = measurement.get("source_track_identity")
        if not isinstance(source_identity, dict):
            raise RuntimeError("measurement lacks explicit source-track identity")
        machine = source_identity.get("machine")
        sample = source_identity.get("sample_name")
        if not isinstance(machine, str) or not machine or not isinstance(sample, str) or not sample:
            raise RuntimeError("measurement lacks explicit machine/sample block identity")
        blocks[(machine, sample)].append(
            {
                **declared,
                "machine": machine,
                "sample_name": sample,
                "workbook_excel_row": measurement["workbook_excel_row"],
            }
        )
    for values in blocks.values():
        values.sort(key=lambda item: (item["workbook_excel_row"], item["filepath"]))
    return dict(sorted(blocks.items()))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Checksum-verify a bounded, explicit sample-block representative set of "
            "Data-referenced IN625 mds2-2923 micrographs. All workbook rows remain "
            "metadata-bound; full raw-image acquisition is reserved for image "
            "remeasurement rather than required for published workbook values."
        )
    )
    parser.add_argument("--acquisition-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--max-auto-mib", type=int, default=16)
    parser.add_argument(
        "--max-attempts-per-block",
        type=int,
        default=4,
        help="Fail closed only after this many authoritative candidates in one block fail.",
    )
    args = parser.parse_args()
    if args.max_attempts_per_block <= 0:
        raise RuntimeError("--max-attempts-per-block must be positive")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest["product_id"] != "mds2-2923":
        raise RuntimeError("micrograph manifest is not bound to mds2-2923")
    if manifest["scientific_status_changed"] is not False:
        raise RuntimeError("micrograph manifest cannot change scientific status")
    if manifest["issue_76_eligible"] is not False:
        raise RuntimeError("micrograph manifest cannot make Issue #76 eligible")

    files = manifest["files"]
    if not isinstance(files, list) or not files:
        raise RuntimeError("micrograph manifest contains no files")
    paths = [item["filepath"] for item in files]
    if len(paths) != len(set(paths)):
        raise RuntimeError("micrograph manifest repeats filepaths")

    report = _load_report(args.manifest, manifest)
    blocks = _explicit_sample_blocks(files=files, report=report)
    if not blocks:
        raise RuntimeError("no explicit machine/sample blocks were resolved")

    metadata_bytes = _pinned_metadata(
        args.acquisition_root, manifest["nerdm_metadata_sha256"]
    )
    candidates = discover_nist_pdr_candidates(
        metadata_bytes=metadata_bytes,
        product_id="mds2-2923",
        filepaths=paths,
        evidence_role="source_micrograph",
    )
    by_path = {candidate["artifact_path"]: candidate for candidate in candidates}
    declared = {item["filepath"]: item for item in files}
    if set(by_path) != set(declared):
        raise RuntimeError("manifest and exact NERDm candidate sets differ")
    for path, candidate in by_path.items():
        item = declared[path]
        if candidate["expected_sha256"] != item["sha256"]:
            raise RuntimeError(f"NERDm SHA changed for {path}")
        if candidate["expected_size_bytes"] != item["size_bytes"]:
            raise RuntimeError(f"NERDm size changed for {path}")

    max_auto_bytes = args.max_auto_mib * _MIB
    queue = plan_public_acquisition_queue(
        candidates,
        max_auto_bytes=max_auto_bytes,
    )
    if queue["auto_count"] != len(candidates):
        raise RuntimeError(
            "not every workbook-bound micrograph is eligible for automatic acquisition"
        )
    if queue["review_required_count"] or queue["blocked_count"]:
        raise RuntimeError("micrograph acquisition queue contains non-AUTO entries")

    root = args.output_root
    root.mkdir(parents=True, exist_ok=True)
    verified: list[dict[str, Any]] = []
    source_failures: list[dict[str, Any]] = []
    block_results: list[dict[str, Any]] = []

    for block_index, ((machine, sample_name), block_files) in enumerate(blocks.items()):
        success: dict[str, Any] | None = None
        attempts = 0
        for item in block_files[: args.max_attempts_per_block]:
            attempts += 1
            candidate = by_path[item["filepath"]]
            key = hashlib.sha256(candidate["candidate_id"].encode("utf-8")).hexdigest()[:16]
            package = root / "packages" / f"{block_index:02d}-{attempts:02d}-{key}"
            try:
                receipt = acquire_public_artifact(
                    candidate=candidate,
                    metadata_bytes=metadata_bytes,
                    output_dir=package,
                    timeout_seconds=args.timeout_seconds,
                    max_auto_bytes=max_auto_bytes,
                )
            except PublicAcquisitionError as exc:
                source_failures.append(
                    {
                        "machine": machine,
                        "sample_name": sample_name,
                        "workbook_excel_row": item["workbook_excel_row"],
                        "filepath": candidate["artifact_path"],
                        "expected_sha256": candidate["expected_sha256"],
                        "expected_size_bytes": candidate["expected_size_bytes"],
                        "error": str(exc),
                        "scientific_status_changed": False,
                    }
                )
                continue
            if receipt["artifact_sha256"] != item["sha256"]:
                raise RuntimeError("verified receipt SHA differs from intake manifest")
            if receipt["artifact_size_bytes"] != item["size_bytes"]:
                raise RuntimeError("verified receipt size differs from intake manifest")
            if receipt["recorded_acquisition_provenance_authenticated"] is not True:
                raise RuntimeError("micrograph acquisition provenance did not authenticate")
            success = {
                "machine": machine,
                "sample_name": sample_name,
                "workbook_excel_row": item["workbook_excel_row"],
                "filepath": candidate["artifact_path"],
                "sha256": receipt["artifact_sha256"],
                "size_bytes": receipt["artifact_size_bytes"],
                "physical_track_id": item["physical_track_id"],
                "measurement_id": item["measurement_id"],
                "recorded_acquisition_provenance_authenticated": True,
            }
            verified.append(success)
            break
        block_results.append(
            {
                "machine": machine,
                "sample_name": sample_name,
                "candidate_measurement_count": len(block_files),
                "attempt_count": attempts,
                "live_verified": success is not None,
                "verified_filepath": None if success is None else success["filepath"],
            }
        )

    uncovered = [item for item in block_results if not item["live_verified"]]
    summary = {
        "schema_version": "1.0",
        "product_id": "mds2-2923",
        "workbook_sha256": manifest["workbook_sha256"],
        "nerdm_metadata_sha256": manifest["nerdm_metadata_sha256"],
        "metadata_bound_file_count": len(files),
        "metadata_bound_total_size_bytes": manifest["total_size_bytes"],
        "explicit_sample_block_count": len(blocks),
        "live_verified_sample_block_count": len(blocks) - len(uncovered),
        "representative_sample_blocks_live_verified": not uncovered,
        "live_verified_file_count": len(verified),
        "live_verified_total_size_bytes": sum(item["size_bytes"] for item in verified),
        "source_live_verification_failure_count": len(source_failures),
        "source_live_verification_failures": source_failures,
        "sample_blocks": block_results,
        "files": verified,
        "all_workbook_bound_micrographs_metadata_bound": len(by_path) == len(files),
        "all_workbook_bound_micrographs_live_verified": False,
        "full_raw_acquisition_required_for_workbook_published_width_depth_use": False,
        "full_raw_acquisition_required_for_image_remeasurement": True,
        "raw_bytes_persisted_in_job_workspace": True,
        "raw_bytes_committed_to_repository": False,
        "scientific_status_changed": False,
        "scientific_support_established": False,
        "issue_76_eligible": False,
    }
    _write_json(root / "micrograph_live_verification_summary.json", summary)
    print(
        json.dumps(
            {key: value for key, value in summary.items() if key not in {"files", "source_live_verification_failures"}},
            indent=2,
            sort_keys=True,
        )
    )
    if uncovered:
        raise RuntimeError(
            "no checksum-valid live micrograph could be acquired for explicit sample blocks: "
            + ", ".join(f"{item['machine']}/{item['sample_name']}" for item in uncovered)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
