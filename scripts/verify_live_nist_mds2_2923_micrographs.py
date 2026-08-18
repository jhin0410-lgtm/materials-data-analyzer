from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from materials_data_analyzer.research_loop.nist_pdr_acquisition import (
    discover_nist_pdr_candidates,
)
from materials_data_analyzer.research_loop.public_data_acquisition import (
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Acquire and checksum-verify every Data-referenced IN625 mds2-2923 "
            "micrograph from the exact NERDm metadata used for workbook intake."
        )
    )
    parser.add_argument("--acquisition-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--max-auto-mib", type=int, default=16)
    args = parser.parse_args()

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
    verified = []
    for index, candidate in enumerate(candidates):
        key = hashlib.sha256(candidate["candidate_id"].encode("utf-8")).hexdigest()[:16]
        package = root / "packages" / f"{index:04d}-{key}"
        receipt = acquire_public_artifact(
            candidate=candidate,
            metadata_bytes=metadata_bytes,
            output_dir=package,
            timeout_seconds=args.timeout_seconds,
            max_auto_bytes=max_auto_bytes,
        )
        expected = declared[candidate["artifact_path"]]
        if receipt["artifact_sha256"] != expected["sha256"]:
            raise RuntimeError(
                "verified receipt SHA differs from intake manifest: "
                f"{candidate['artifact_path']}"
            )
        if receipt["artifact_size_bytes"] != expected["size_bytes"]:
            raise RuntimeError(
                "verified receipt size differs from intake manifest: "
                f"{candidate['artifact_path']}"
            )
        if receipt["recorded_acquisition_provenance_authenticated"] is not True:
            raise RuntimeError("micrograph acquisition provenance did not authenticate")
        verified.append(
            {
                "filepath": candidate["artifact_path"],
                "sha256": receipt["artifact_sha256"],
                "size_bytes": receipt["artifact_size_bytes"],
                "physical_track_id": expected["physical_track_id"],
                "measurement_id": expected["measurement_id"],
                "recorded_acquisition_provenance_authenticated": True,
            }
        )

    summary = {
        "schema_version": "1.0",
        "product_id": "mds2-2923",
        "workbook_sha256": manifest["workbook_sha256"],
        "nerdm_metadata_sha256": manifest["nerdm_metadata_sha256"],
        "requested_file_count": len(files),
        "verified_file_count": len(verified),
        "verified_total_size_bytes": sum(item["size_bytes"] for item in verified),
        "all_workbook_bound_micrographs_verified": len(verified) == len(files),
        "files": verified,
        "raw_bytes_persisted_in_job_workspace": True,
        "raw_bytes_committed_to_repository": False,
        "scientific_status_changed": False,
        "scientific_support_established": False,
        "issue_76_eligible": False,
    }
    _write_json(root / "micrograph_live_verification_summary.json", summary)
    print(
        json.dumps(
            {key: value for key, value in summary.items() if key != "files"},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
