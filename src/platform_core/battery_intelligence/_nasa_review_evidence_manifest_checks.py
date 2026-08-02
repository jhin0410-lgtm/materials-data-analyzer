"""Current-file and manifest checksum checks for NASA review evidence."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .common import file_sha256

_IMPORT_KEYS = {
    "nasa_pcoe_protocol_summary.csv": "protocol_summary",
    "nasa_pcoe_source_inventory.csv": "source_inventory",
    "nasa_pcoe_excluded_operations.csv": "excluded_operations",
}
_QUEUE_SOURCE_PATHS = {
    "tables/nasa_protocol_battery_profile.csv",
    "reports/nasa_protocol_audit.json",
}


def _verify(checksums: Mapping[str, Any], key: str, path: Path, context: str) -> str:
    expected = checksums.get(key)
    if not isinstance(expected, str) or not expected.strip():
        raise ValueError(f"{context} missing checksum: {key}")
    observed = file_sha256(path)
    if observed.lower() != expected.strip().lower():
        raise ValueError(f"{context} checksum mismatch: {key}")
    return observed


def verify_current_manifests(
    import_root: Path,
    analysis_root: Path,
    analysis_paths: Mapping[str, Path],
    import_paths: Mapping[str, Path],
) -> dict[str, Any]:
    analysis_manifest_path = analysis_root / "run_manifest.json"
    import_manifest_path = import_root / "nasa_pcoe_import_manifest.json"
    if not analysis_manifest_path.is_file():
        raise FileNotFoundError("review evidence requires analysis run_manifest.json")
    if not import_manifest_path.is_file():
        raise FileNotFoundError("review evidence requires nasa_pcoe_import_manifest.json")

    analysis_manifest = json.loads(analysis_manifest_path.read_text(encoding="utf-8"))
    import_manifest = json.loads(import_manifest_path.read_text(encoding="utf-8"))
    queue_summary = json.loads(
        analysis_paths["reports/nasa_protocol_review_queue.json"].read_text(
            encoding="utf-8"
        )
    )
    protocol_summary = json.loads(
        analysis_paths["reports/nasa_protocol_audit.json"].read_text(encoding="utf-8")
    )
    if analysis_manifest.get("nasa_focused_review_queue") != queue_summary:
        raise ValueError("analysis manifest review-queue summary does not match its JSON")
    if analysis_manifest.get("nasa_protocol_aware_posthoc_audit") != protocol_summary:
        raise ValueError("analysis manifest protocol audit summary does not match its JSON")

    analysis_checksums = analysis_manifest.get("artifact_checksums")
    import_checksums = import_manifest.get("output_sha256")
    if not isinstance(analysis_checksums, Mapping):
        raise ValueError("analysis manifest is missing artifact_checksums")
    if not isinstance(import_checksums, Mapping):
        raise ValueError("NASA import manifest is missing output_sha256")
    verified_analysis = {
        name: _verify(analysis_checksums, name, path, "analysis manifest")
        for name, path in analysis_paths.items()
    }
    verified_import = {
        name: _verify(
            import_checksums, _IMPORT_KEYS[name], path, "NASA import manifest"
        )
        for name, path in import_paths.items()
    }

    queue_sources = queue_summary.get("source_artifact_checksums")
    if not isinstance(queue_sources, Mapping):
        raise ValueError("review queue summary is missing source_artifact_checksums")
    for name in _QUEUE_SOURCE_PATHS:
        if str(queue_sources.get(name, "")).lower() != verified_analysis[name].lower():
            raise ValueError(
                "review queue is stale relative to the current protocol audit: " + name
            )
    if queue_summary.get("predictive_evidence_level") != protocol_summary.get(
        "predictive_evidence_level"
    ):
        raise ValueError("review queue predictive evidence is stale")

    return {
        "analysis_manifest": analysis_manifest,
        "import_manifest": import_manifest,
        "queue_summary": queue_summary,
        "protocol_summary": protocol_summary,
        "verified_analysis": verified_analysis,
        "verified_import": verified_import,
        "import_manifest_path": import_manifest_path,
    }
