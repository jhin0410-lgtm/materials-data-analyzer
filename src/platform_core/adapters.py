"""Thin case-study adapter metadata contracts.

Adapters connect platform dry-run metadata to existing case-study scripts
without importing or executing those scripts. v2.0.2 keeps actual execution
disabled and permits manifest-only planning.
"""

from __future__ import annotations

from dataclasses import dataclass

from .plugins import ALLOWED_STAGES


ALLOWED_EXECUTION_MODES = (
    "metadata_only",
    "manifest_only",
    "dry_run_safe",
    "executable_disabled",
    "executable_future",
)

ALLOWED_EXECUTABLE_STATUSES = (
    "metadata_only",
    "manifest_only",
    "dry_run_only",
    "executable_disabled",
    "executable_future",
)


@dataclass(frozen=True)
class AdapterExecutionPolicy:
    """Execution boundary for a registered adapter."""

    network_required: bool = False
    raw_data_required: bool = False
    model_training_required: bool = False
    writes_outputs: bool = False
    safe_for_dry_run: bool = True
    safe_for_manifest_only: bool = True
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.execution_allowed:
            raise ValueError("v2.0.2 adapters must not allow actual execution")
        if not self.safe_for_dry_run and self.safe_for_manifest_only:
            raise ValueError("manifest-only safety requires dry-run safety")

    def to_dict(self) -> dict[str, object]:
        return {
            "network_required": self.network_required,
            "raw_data_required": self.raw_data_required,
            "model_training_required": self.model_training_required,
            "writes_outputs": self.writes_outputs,
            "safe_for_dry_run": self.safe_for_dry_run,
            "safe_for_manifest_only": self.safe_for_manifest_only,
            "execution_allowed": self.execution_allowed,
        }


@dataclass(frozen=True)
class AdapterMetadata:
    """Metadata-only stage adapter contract."""

    adapter_id: str
    plugin_id: str
    case_study_id: str
    stage: str
    module_path: str
    callable_name: str | None
    execution_mode: str
    required_artifacts: tuple[str, ...] = ()
    optional_artifacts: tuple[str, ...] = ()
    produced_artifacts: tuple[str, ...] = ()
    execution_policy: AdapterExecutionPolicy = AdapterExecutionPolicy()
    executable_status: str = "executable_disabled"
    blocked_reasons: tuple[str, ...] = ("actual_execution_disabled",)
    description: str = ""

    def __post_init__(self) -> None:
        if not self.adapter_id:
            raise ValueError("adapter_id is required")
        if not self.plugin_id:
            raise ValueError("plugin_id is required")
        if self.stage not in ALLOWED_STAGES:
            raise ValueError(f"unsupported adapter stage: {self.stage}")
        if self.execution_mode not in ALLOWED_EXECUTION_MODES:
            raise ValueError(f"unsupported execution_mode: {self.execution_mode}")
        if self.executable_status not in ALLOWED_EXECUTABLE_STATUSES:
            raise ValueError(f"unsupported executable_status: {self.executable_status}")
        if self.execution_mode not in {"metadata_only", "manifest_only", "dry_run_safe", "executable_disabled"}:
            raise ValueError("v2.0.2 adapters cannot be executable")
        if len(set(self.required_artifacts)) != len(self.required_artifacts):
            raise ValueError(f"duplicate required_artifacts for {self.adapter_id}")
        if len(set(self.produced_artifacts)) != len(self.produced_artifacts):
            raise ValueError(f"duplicate produced_artifacts for {self.adapter_id}")

    @property
    def execution_allowed(self) -> bool:
        return self.execution_policy.execution_allowed

    def to_dict(self) -> dict[str, object]:
        return {
            "adapter_id": self.adapter_id,
            "plugin_id": self.plugin_id,
            "case_study_id": self.case_study_id,
            "stage": self.stage,
            "module_path": self.module_path,
            "callable_name": self.callable_name,
            "execution_mode": self.execution_mode,
            "required_artifacts": list(self.required_artifacts),
            "optional_artifacts": list(self.optional_artifacts),
            "produced_artifacts": list(self.produced_artifacts),
            "execution_policy": self.execution_policy.to_dict(),
            "network_required": self.execution_policy.network_required,
            "raw_data_required": self.execution_policy.raw_data_required,
            "model_training_required": self.execution_policy.model_training_required,
            "writes_outputs": self.execution_policy.writes_outputs,
            "safe_for_dry_run": self.execution_policy.safe_for_dry_run,
            "safe_for_manifest_only": self.execution_policy.safe_for_manifest_only,
            "execution_allowed": self.execution_allowed,
            "executable_status": self.executable_status,
            "blocked_reasons": list(self.blocked_reasons),
            "description": self.description,
        }
