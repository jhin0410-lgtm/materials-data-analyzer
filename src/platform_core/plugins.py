"""Case-study plugin metadata contracts.

The v2 platform layer is intentionally additive. Plugins describe existing
case-study workflows without importing or executing their scripts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


ALLOWED_STAGES = (
    "acquisition",
    "normalization",
    "readiness",
    "feature_build",
    "validation",
    "trust",
    "closeout",
)

ALLOWED_PLUGIN_STATUSES = (
    "metadata_only",
    "scaffolded",
    "adapter_mapped",
    "dry_run_ready",
    "executable_disabled",
    "runnable",
    "deprecated",
)


@dataclass(frozen=True)
class PluginMetadata:
    """Metadata-only contract for a case-study plugin."""

    plugin_id: str
    case_study_id: str
    description: str
    supported_stages: tuple[str, ...]
    config_schema_version: str = "2.0"
    entrypoints: Mapping[str, str] = field(default_factory=dict)
    required_artifacts: tuple[str, ...] = ()
    produced_artifacts: tuple[str, ...] = ()
    local_only_artifacts: tuple[str, ...] = ()
    tracked_artifacts: tuple[str, ...] = ()
    validation_policy_id: str | None = None
    trust_policy_id: str | None = None
    status: str = "metadata_only"
    adapter_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.plugin_id:
            raise ValueError("plugin_id is required")
        if not self.case_study_id:
            raise ValueError("case_study_id is required")
        if self.status not in ALLOWED_PLUGIN_STATUSES:
            raise ValueError(f"unsupported plugin status: {self.status}")
        unsupported = sorted(set(self.supported_stages) - set(ALLOWED_STAGES))
        if unsupported:
            raise ValueError(f"unsupported stages for {self.plugin_id}: {unsupported}")
        if len(set(self.supported_stages)) != len(self.supported_stages):
            raise ValueError(f"duplicate stages for {self.plugin_id}")
        if len(set(self.adapter_ids)) != len(self.adapter_ids):
            raise ValueError(f"duplicate adapter_ids for {self.plugin_id}")

    def supports_stage(self, stage: str) -> bool:
        return stage in self.supported_stages

    def to_dict(self) -> dict[str, object]:
        return {
            "plugin_id": self.plugin_id,
            "case_study_id": self.case_study_id,
            "description": self.description,
            "supported_stages": list(self.supported_stages),
            "config_schema_version": self.config_schema_version,
            "entrypoints": dict(self.entrypoints),
            "required_artifacts": list(self.required_artifacts),
            "produced_artifacts": list(self.produced_artifacts),
            "local_only_artifacts": list(self.local_only_artifacts),
            "tracked_artifacts": list(self.tracked_artifacts),
            "validation_policy_id": self.validation_policy_id,
            "trust_policy_id": self.trust_policy_id,
            "status": self.status,
            "adapter_ids": list(self.adapter_ids),
        }
