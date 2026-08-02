"""Verify that one analysis run is explicitly bound to one NASA import."""
from __future__ import annotations

from typing import Any, Mapping

from ._nasa_review_evidence_manifest_checks import _QUEUE_SOURCE_PATHS
from .common import file_sha256


def verify_import_link(state: Mapping[str, Any]) -> dict[str, Any]:
    analysis_manifest = state["analysis_manifest"]
    import_manifest = state["import_manifest"]
    verified_analysis = state["verified_analysis"]
    verified_import = state["verified_import"]
    import_binding = analysis_manifest.get("nasa_import_artifact_binding")
    if not isinstance(import_binding, Mapping) or import_binding.get(
        "binding_status"
    ) != "verified":
        raise ValueError(
            "analysis run is not bound to a verified NASA import; rerun the protocol audit CLI"
        )
    observed_manifest_hash = file_sha256(state["import_manifest_path"])
    if str(import_binding.get("import_manifest_sha256", "")).lower() != (
        observed_manifest_hash.lower()
    ):
        raise ValueError("analysis/import manifest binding mismatch")
    if import_binding.get("input") != import_manifest.get("input"):
        raise ValueError("analysis/import input identity mismatch")

    bound_import = import_binding.get("import_artifact_checksums")
    bound_analysis = import_binding.get("protocol_audit_artifact_checksums")
    if not isinstance(bound_import, Mapping) or not isinstance(
        bound_analysis, Mapping
    ):
        raise ValueError("analysis/import binding is missing artifact checksums")
    if dict(bound_import) != dict(verified_import):
        raise ValueError("analysis/import artifact binding mismatch")
    expected_analysis = {
        name: verified_analysis[name] for name in _QUEUE_SOURCE_PATHS
    }
    if dict(bound_analysis) != expected_analysis:
        raise ValueError("import binding is stale relative to the protocol audit")
    return dict(import_binding)
