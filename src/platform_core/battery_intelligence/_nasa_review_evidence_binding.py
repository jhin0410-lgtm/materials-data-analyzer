"""Orchestrate manifest and import-identity checks for review evidence."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ._nasa_review_evidence_import_checks import verify_import_link
from ._nasa_review_evidence_manifest_checks import verify_current_manifests


def _bindings(
    import_root: Path,
    analysis_root: Path,
    analysis_paths: Mapping[str, Path],
    import_paths: Mapping[str, Path],
) -> dict[str, Any]:
    state = verify_current_manifests(
        import_root, analysis_root, analysis_paths, import_paths
    )
    state["import_binding"] = verify_import_link(state)
    return state
