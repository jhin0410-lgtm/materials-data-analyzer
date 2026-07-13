"""Safe artifact resolution for controlled platform execution."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .artifacts import ArtifactMetadata, ArtifactRegistry


@dataclass(frozen=True)
class ResolvedArtifact:
    artifact: ArtifactMetadata
    path: Path
    relative_path: str
    exists: bool
    size_bytes: int | None
    sha256: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact.artifact_id,
            "relative_path": self.relative_path,
            "tracked_policy": self.artifact.tracked_policy,
            "local_only": self.artifact.local_only,
            "exists": self.exists,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


def calculate_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ArtifactResolver:
    """Resolve registry artifact IDs to safe repository-relative files."""

    def __init__(self, repository_root: str | Path, artifact_registry: ArtifactRegistry):
        self.repository_root = Path(repository_root).resolve()
        self.artifact_registry = artifact_registry

    def resolve(
        self,
        artifact_id: str,
        *,
        require_exists: bool = True,
        allow_local_only: bool = False,
        allow_raw: bool = False,
        checksum: bool = True,
    ) -> ResolvedArtifact:
        artifact = self.artifact_registry.get(artifact_id)
        if artifact.local_only and not allow_local_only:
            raise PermissionError(f"local-only artifact access is not allowed: {artifact_id}")
        if artifact.tracked_policy == "external_raw" and not allow_raw:
            raise PermissionError(f"raw artifact access is not allowed: {artifact_id}")
        target = (self.repository_root / artifact.relative_path).resolve()
        if self.repository_root != target and self.repository_root not in target.parents:
            raise ValueError(f"artifact path escapes repository root: {artifact_id}")
        if target.is_symlink():
            resolved = target.resolve()
            if self.repository_root != resolved and self.repository_root not in resolved.parents:
                raise ValueError(f"artifact symlink escapes repository root: {artifact_id}")
        exists = target.exists()
        if require_exists and not exists:
            raise FileNotFoundError(f"required artifact missing: {artifact_id}")
        size = target.stat().st_size if exists and target.is_file() else None
        file_sha = calculate_sha256(target) if exists and target.is_file() and checksum else None
        return ResolvedArtifact(
            artifact=artifact,
            path=target,
            relative_path=artifact.relative_path,
            exists=exists,
            size_bytes=size,
            sha256=file_sha,
        )

    def resolve_many(
        self,
        artifact_ids: tuple[str, ...] | list[str],
        *,
        require_exists: bool = True,
        allow_local_only: bool = False,
        allow_raw: bool = False,
    ) -> list[ResolvedArtifact]:
        return [
            self.resolve(
                artifact_id,
                require_exists=require_exists,
                allow_local_only=allow_local_only,
                allow_raw=allow_raw,
            )
            for artifact_id in artifact_ids
        ]
