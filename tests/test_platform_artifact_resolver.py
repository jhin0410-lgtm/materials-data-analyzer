from pathlib import Path

import pytest

from src.platform_core.artifact_resolver import ArtifactResolver
from src.platform_core.artifacts import ArtifactMetadata, ArtifactRegistry


def _registry():
    registry = ArtifactRegistry()
    registry.register(
        ArtifactMetadata(
            artifact_id="compact",
            case_study_id="demo",
            stage="trust",
            relative_path="data/processed/compact.csv",
            artifact_type="summary",
            format="csv",
            tracked_policy="generated_compact",
            local_only=False,
        )
    )
    registry.register(
        ArtifactMetadata(
            artifact_id="local",
            case_study_id="demo",
            stage="validation",
            relative_path="data/processed/local.csv",
            artifact_type="row_predictions",
            format="csv",
            tracked_policy="local_only",
            local_only=True,
        )
    )
    return registry


def test_artifact_resolver_resolves_registered_compact_file(tmp_path):
    path = tmp_path / "data" / "processed" / "compact.csv"
    path.parent.mkdir(parents=True)
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    resolver = ArtifactResolver(tmp_path, _registry())

    resolved = resolver.resolve("compact")

    assert resolved.exists is True
    assert resolved.size_bytes == path.stat().st_size
    assert resolved.sha256 is not None
    assert resolved.relative_path == "data/processed/compact.csv"


def test_artifact_resolver_rejects_local_only_by_default(tmp_path):
    resolver = ArtifactResolver(tmp_path, _registry())

    with pytest.raises(PermissionError, match="local-only"):
        resolver.resolve("local", require_exists=False)


def test_artifact_resolver_rejects_symlink_escape(tmp_path):
    if not hasattr(Path, "symlink_to"):
        pytest.skip("symlink unsupported")
    outside = tmp_path.parent / "outside.csv"
    outside.write_text("x\n", encoding="utf-8")
    path = tmp_path / "data" / "processed" / "compact.csv"
    path.parent.mkdir(parents=True)
    try:
        path.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable")
    resolver = ArtifactResolver(tmp_path, _registry())

    with pytest.raises(ValueError, match="escapes"):
        resolver.resolve("compact")
