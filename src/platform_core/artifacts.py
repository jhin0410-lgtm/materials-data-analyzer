"""Artifact metadata registry for the v2 platform scaffold."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath


ALLOWED_TRACKED_POLICIES = (
    "tracked",
    "local_only",
    "generated_compact",
    "external_raw",
    "optional",
)


def validate_relative_path(relative_path: str) -> None:
    """Reject absolute paths and traversal without touching the filesystem."""

    if not relative_path:
        raise ValueError("relative_path is required")
    normalized = relative_path.replace("\\", "/")
    posix_path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(relative_path)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError(f"absolute paths are not allowed: {relative_path}")
    if ".." in posix_path.parts:
        raise ValueError(f"path traversal is not allowed: {relative_path}")


@dataclass(frozen=True)
class ArtifactMetadata:
    artifact_id: str
    case_study_id: str
    stage: str
    relative_path: str
    artifact_type: str
    format: str
    tracked_policy: str
    local_only: bool
    required: bool = False
    producer: str | None = None
    consumers: tuple[str, ...] = ()
    provenance_required: bool = True
    checksum_required: bool = False
    status: str = "defined"

    def __post_init__(self) -> None:
        if not self.artifact_id:
            raise ValueError("artifact_id is required")
        validate_relative_path(self.relative_path)
        if self.tracked_policy not in ALLOWED_TRACKED_POLICIES:
            raise ValueError(f"unsupported tracked_policy: {self.tracked_policy}")
        if self.local_only and self.tracked_policy in {"tracked", "generated_compact"}:
            raise ValueError(f"tracked/local_only conflict for {self.artifact_id}")
        if (self.relative_path.replace("\\", "/").startswith("data/raw/") or self.artifact_type == "raw") and self.tracked_policy in {
            "tracked",
            "generated_compact",
        }:
            raise ValueError(f"raw artifacts cannot be tracked: {self.artifact_id}")

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "case_study_id": self.case_study_id,
            "stage": self.stage,
            "relative_path": self.relative_path,
            "artifact_type": self.artifact_type,
            "format": self.format,
            "tracked_policy": self.tracked_policy,
            "local_only": self.local_only,
            "required": self.required,
            "producer": self.producer,
            "consumers": list(self.consumers),
            "provenance_required": self.provenance_required,
            "checksum_required": self.checksum_required,
            "status": self.status,
        }


@dataclass
class ArtifactRegistry:
    _artifacts: dict[str, ArtifactMetadata] = field(default_factory=dict)

    def register(self, artifact: ArtifactMetadata) -> None:
        if artifact.artifact_id in self._artifacts:
            raise ValueError(f"duplicate artifact_id: {artifact.artifact_id}")
        self._artifacts[artifact.artifact_id] = artifact

    def get(self, artifact_id: str) -> ArtifactMetadata:
        try:
            return self._artifacts[artifact_id]
        except KeyError as exc:
            raise KeyError(f"unknown artifact_id: {artifact_id}") from exc

    def list_artifacts(self, case_study_id: str | None = None) -> list[ArtifactMetadata]:
        artifacts = self._artifacts.values()
        if case_study_id is not None:
            artifacts = [artifact for artifact in artifacts if artifact.case_study_id == case_study_id]
        return sorted(artifacts, key=lambda artifact: artifact.artifact_id)

    def snapshot(self, case_study_id: str | None = None) -> list[dict[str, object]]:
        return [artifact.to_dict() for artifact in self.list_artifacts(case_study_id)]


def build_default_artifact_registry() -> ArtifactRegistry:
    registry = ArtifactRegistry()
    for artifact in [
        ArtifactMetadata(
            "battery_archive_cycle_file_inventory",
            "battery_archive",
            "acquisition",
            "data/processed/battery_archive_cycle_file_inventory.csv",
            "inventory",
            "csv",
            "generated_compact",
            False,
            True,
            "scripts/build_battery_archive_cycle_inventory.py",
        ),
        ArtifactMetadata(
            "battery_archive_analysis_ready",
            "battery_archive",
            "normalization",
            "data/processed/battery_archive_cycle_analysis_ready.csv",
            "analysis_ready_table",
            "csv",
            "local_only",
            True,
            False,
            "scripts/build_battery_archive_analysis_ready.py",
        ),
        ArtifactMetadata(
            "battery_archive_reliability_group_summary",
            "battery_archive",
            "closeout",
            "data/processed/battery_archive_reliability_group_summary.csv",
            "summary",
            "csv",
            "generated_compact",
            False,
        ),
        ArtifactMetadata(
            "materials_project_v1_3_validation_metrics",
            "materials_project",
            "validation",
            "data/processed/materials_project_v1_3_validation_metrics.csv",
            "metrics_summary",
            "csv",
            "generated_compact",
            False,
        ),
        ArtifactMetadata(
            "materials_project_v1_3_validation_predictions",
            "materials_project",
            "validation",
            "data/processed/materials_project_v1_3_validation_predictions.csv",
            "row_predictions",
            "csv",
            "local_only",
            True,
        ),
        ArtifactMetadata(
            "materials_project_v1_3_trust_conclusion",
            "materials_project",
            "trust",
            "data/processed/materials_project_v1_3_trust_conclusion.csv",
            "trust_summary",
            "csv",
            "generated_compact",
            False,
        ),
        ArtifactMetadata(
            "smart_factory_v1_4_classification_metrics",
            "smart_factory",
            "validation",
            "data/processed/smart_factory_v1_4_classification_metrics.csv",
            "metrics_summary",
            "csv",
            "generated_compact",
            False,
        ),
        ArtifactMetadata(
            "smart_factory_v1_4_classification_predictions",
            "smart_factory",
            "validation",
            "data/processed/smart_factory_v1_4_classification_predictions.csv",
            "row_predictions",
            "csv",
            "local_only",
            True,
        ),
        ArtifactMetadata(
            "smart_factory_v1_4_trust_summary",
            "smart_factory",
            "trust",
            "data/processed/smart_factory_v1_4_trust_summary.csv",
            "trust_summary",
            "csv",
            "generated_compact",
            False,
        ),
        ArtifactMetadata(
            "reliability_v1_5_classification_metrics",
            "reliability",
            "validation",
            "data/processed/reliability_v1_5_classification_metrics.csv",
            "metrics_summary",
            "csv",
            "generated_compact",
            False,
        ),
        ArtifactMetadata(
            "reliability_v1_5_backblaze_analysis_ready",
            "reliability",
            "normalization",
            "data/processed/reliability_v1_5_backblaze_analysis_ready.csv",
            "analysis_ready_table",
            "csv",
            "local_only",
            True,
        ),
        ArtifactMetadata(
            "reliability_v1_5_horizon_7d_lookback_7d_dataset",
            "reliability",
            "feature_build",
            "data/processed/reliability_v1_5_horizon_7d_lookback_7d_dataset.csv",
            "feature_table",
            "csv",
            "local_only",
            True,
        ),
        ArtifactMetadata(
            "reliability_v1_5_classification_predictions",
            "reliability",
            "validation",
            "data/processed/reliability_v1_5_classification_predictions.csv",
            "row_predictions",
            "csv",
            "local_only",
            True,
        ),
        ArtifactMetadata(
            "reliability_v1_5_trust_summary",
            "reliability",
            "trust",
            "data/processed/reliability_v1_5_trust_summary.csv",
            "trust_summary",
            "csv",
            "generated_compact",
            False,
        ),
    ]:
        registry.register(artifact)
    return registry
