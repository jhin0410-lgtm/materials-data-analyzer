"""Service wrapper for the local platform run registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import ArtifactRegistry, build_default_artifact_registry
from .run_registry import (
    DEFAULT_EXPORT_DIR,
    DEFAULT_REGISTRY_PATH,
    compare_runs,
    export_registry_snapshot,
    get_lineage,
    get_run,
    get_schema_version,
    ingest_manifest,
    initialize_registry,
    list_artifact_records,
    list_runs,
    reproducibility_status,
    validate_registry,
)


@dataclass(frozen=True)
class RegistryService:
    repo_root: Path
    registry_path: str = DEFAULT_REGISTRY_PATH
    artifact_registry: ArtifactRegistry | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "repo_root", Path(self.repo_root).resolve())
        if self.artifact_registry is None:
            object.__setattr__(self, "artifact_registry", build_default_artifact_registry())

    def initialize(self) -> dict[str, Any]:
        path = initialize_registry(self.repo_root, self.registry_path)
        return {
            "status": "initialized",
            "registry_path": path.relative_to(self.repo_root).as_posix(),
            "schema_version": get_schema_version(self.repo_root, self.registry_path),
        }

    def ingest(self, manifest_path: str | Path) -> dict[str, Any]:
        result = ingest_manifest(
            manifest_path,
            repo_root=self.repo_root,
            registry_path=self.registry_path,
            artifact_registry=self.artifact_registry,
        )
        return result.to_dict()

    def list_runs(self) -> list[dict[str, Any]]:
        return list_runs(repo_root=self.repo_root, registry_path=self.registry_path)

    def get_run(self, run_id: str) -> dict[str, Any]:
        return get_run(run_id, repo_root=self.repo_root, registry_path=self.registry_path)

    def list_artifacts(self, run_id: str | None = None) -> list[dict[str, Any]]:
        return list_artifact_records(run_id=run_id, repo_root=self.repo_root, registry_path=self.registry_path)

    def lineage(self, artifact_record_id: str) -> dict[str, Any]:
        return get_lineage(artifact_record_id, repo_root=self.repo_root, registry_path=self.registry_path)

    def reproducibility(self, run_id: str) -> dict[str, Any]:
        return reproducibility_status(run_id, repo_root=self.repo_root, registry_path=self.registry_path)

    def compare(self, run_a: str, run_b: str) -> dict[str, Any]:
        return compare_runs(run_a, run_b, repo_root=self.repo_root, registry_path=self.registry_path)

    def validate(self) -> dict[str, Any]:
        return validate_registry(repo_root=self.repo_root, registry_path=self.registry_path)

    def export(self, export_dir: str = DEFAULT_EXPORT_DIR, *, overwrite: bool = False) -> dict[str, Any]:
        return export_registry_snapshot(
            repo_root=self.repo_root,
            registry_path=self.registry_path,
            export_dir=export_dir,
            overwrite=overwrite,
        )
