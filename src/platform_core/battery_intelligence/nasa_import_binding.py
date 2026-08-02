"""Bind an official NASA import manifest to one protocol-audited analysis run."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .common import canonical_json, file_sha256

_IMPORT_ARTIFACTS = {
    "nasa_pcoe_protocol_summary.csv": "protocol_summary",
    "nasa_pcoe_source_inventory.csv": "source_inventory",
    "nasa_pcoe_excluded_operations.csv": "excluded_operations",
}
_ANALYSIS_ARTIFACTS = {
    "tables/nasa_protocol_battery_profile.csv": "battery_profile",
    "reports/nasa_protocol_audit.json": "protocol_audit",
}


def _verify(
    checksums: Mapping[str, Any],
    key: str,
    path: Path,
    *,
    context: str,
) -> str:
    expected = checksums.get(key)
    if not isinstance(expected, str) or not expected.strip():
        raise ValueError(f"{context} missing checksum: {key}")
    if not path.is_file():
        raise FileNotFoundError(f"{context} artifact not found: {path}")
    observed = file_sha256(path)
    if observed.lower() != expected.strip().lower():
        raise ValueError(f"{context} checksum mismatch: {key}")
    return observed


def bind_nasa_import_to_analysis(
    *,
    import_output: str | Path,
    analysis_output: str | Path,
) -> dict[str, Any]:
    """Record a fail-closed import identity after a protocol audit.

    Older synthetic or legacy audit fixtures without an import manifest remain
    auditable, but no binding is written and downstream exact evidence generation
    must reject them.
    """
    import_root = Path(import_output)
    analysis_root = Path(analysis_output)
    import_manifest_path = import_root / "nasa_pcoe_import_manifest.json"
    if not import_manifest_path.is_file():
        return {
            "binding_status": "unavailable_no_import_manifest",
            "binding_written": False,
        }

    analysis_manifest_path = analysis_root / "run_manifest.json"
    if not analysis_manifest_path.is_file():
        raise FileNotFoundError("NASA import binding requires analysis run_manifest.json")
    import_manifest = json.loads(import_manifest_path.read_text(encoding="utf-8"))
    analysis_manifest = json.loads(
        analysis_manifest_path.read_text(encoding="utf-8")
    )
    import_checksums = import_manifest.get("output_sha256")
    analysis_checksums = analysis_manifest.get("artifact_checksums")
    if not isinstance(import_checksums, Mapping):
        raise ValueError("NASA import manifest is missing output_sha256")
    if not isinstance(analysis_checksums, Mapping):
        raise ValueError("analysis run manifest is missing artifact_checksums")
    if not isinstance(
        analysis_manifest.get("nasa_protocol_aware_posthoc_audit"), Mapping
    ):
        raise ValueError("analysis run manifest is missing the protocol audit summary")

    verified_import = {
        name: _verify(
            import_checksums,
            key,
            import_root / name,
            context="NASA import manifest",
        )
        for name, key in _IMPORT_ARTIFACTS.items()
    }
    verified_analysis = {
        name: _verify(
            analysis_checksums,
            name,
            analysis_root / name,
            context="analysis run manifest",
        )
        for name in _ANALYSIS_ARTIFACTS
    }
    protocol_summary = json.loads(
        (analysis_root / "reports/nasa_protocol_audit.json").read_text(
            encoding="utf-8"
        )
    )
    if dict(analysis_manifest["nasa_protocol_aware_posthoc_audit"]) != dict(
        protocol_summary
    ):
        raise ValueError(
            "analysis run manifest protocol audit summary does not match its JSON"
        )

    binding = {
        "schema_version": "1.0",
        "binding_status": "verified",
        "import_manifest_sha256": file_sha256(import_manifest_path),
        "retrieval_receipt_verified": bool(
            import_manifest.get("retrieval_receipt_verified", False)
        ),
        "input": import_manifest.get("input"),
        "import_artifact_checksums": verified_import,
        "protocol_audit_artifact_checksums": verified_analysis,
        "scientific_boundary": (
            "This binding proves which manifest-verified NASA import artifacts were "
            "used by the protocol-audit CLI invocation. It does not establish "
            "mechanism, causality, predictive value, or external generalization."
        ),
    }
    analysis_manifest["nasa_import_artifact_binding"] = binding
    analysis_manifest_path.write_text(canonical_json(analysis_manifest), encoding="utf-8")
    return {**binding, "binding_written": True}
