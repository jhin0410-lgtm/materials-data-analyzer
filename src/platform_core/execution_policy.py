"""Explicit execution allowlist for controlled platform adapters."""

from __future__ import annotations

from dataclasses import dataclass, field


POLICY_VERSION = "v2.0.3"


@dataclass(frozen=True)
class AdapterPermission:
    adapter_id: str
    execution_allowed: bool
    allowed_modes: tuple[str, ...]
    allowed_read_artifact_ids: tuple[str, ...] = ()
    allowed_write_patterns: tuple[str, ...] = ("outputs/platform_runs/{run_id}/",)
    network_allowed: bool = False
    raw_data_allowed: bool = False
    model_training_allowed: bool = False
    process_spawn_allowed: bool = False
    canonical_overwrite_allowed: bool = False
    max_output_files: int = 8
    max_output_bytes: int = 1_000_000
    timeout_seconds: int = 30
    reason: str = ""
    policy_version: str = POLICY_VERSION

    def __post_init__(self) -> None:
        if not self.adapter_id:
            raise ValueError("adapter_id is required")
        unsupported_modes = sorted(set(self.allowed_modes) - {"verify", "isolated_run"})
        if unsupported_modes:
            raise ValueError(f"unsupported execution mode(s): {unsupported_modes}")
        if self.execution_allowed and not self.allowed_modes:
            raise ValueError("allowed executable adapters must declare allowed_modes")
        if self.execution_allowed:
            if self.network_allowed or self.raw_data_allowed or self.model_training_allowed:
                raise ValueError("v2.0.3 executable adapters cannot enable network, raw data, or model training")
            if self.process_spawn_allowed:
                raise ValueError("v2.0.3 executable adapters cannot spawn processes")
            if self.canonical_overwrite_allowed:
                raise ValueError("v2.0.3 executable adapters cannot overwrite canonical outputs")

    def permits_mode(self, mode: str) -> bool:
        return self.execution_allowed and mode in self.allowed_modes

    def to_dict(self) -> dict[str, object]:
        return {
            "adapter_id": self.adapter_id,
            "execution_allowed": self.execution_allowed,
            "allowed_modes": list(self.allowed_modes),
            "allowed_read_artifact_ids": list(self.allowed_read_artifact_ids),
            "allowed_write_patterns": list(self.allowed_write_patterns),
            "network_allowed": self.network_allowed,
            "raw_data_allowed": self.raw_data_allowed,
            "model_training_allowed": self.model_training_allowed,
            "process_spawn_allowed": self.process_spawn_allowed,
            "canonical_overwrite_allowed": self.canonical_overwrite_allowed,
            "max_output_files": self.max_output_files,
            "max_output_bytes": self.max_output_bytes,
            "timeout_seconds": self.timeout_seconds,
            "reason": self.reason,
            "policy_version": self.policy_version,
        }


@dataclass
class ExecutionPolicyRegistry:
    _permissions: dict[str, AdapterPermission] = field(default_factory=dict)

    def register(self, permission: AdapterPermission) -> None:
        if permission.adapter_id in self._permissions:
            raise ValueError(f"duplicate adapter execution policy: {permission.adapter_id}")
        self._permissions[permission.adapter_id] = permission

    def get(self, adapter_id: str) -> AdapterPermission:
        try:
            return self._permissions[adapter_id]
        except KeyError as exc:
            raise KeyError(f"unknown adapter execution policy: {adapter_id}") from exc

    def list_permissions(self) -> list[AdapterPermission]:
        return [self._permissions[key] for key in sorted(self._permissions)]

    def snapshot(self) -> list[dict[str, object]]:
        return [permission.to_dict() for permission in self.list_permissions()]


def build_default_execution_policy_registry() -> ExecutionPolicyRegistry:
    registry = ExecutionPolicyRegistry()
    reliability_reads = (
        "reliability_v1_5_classification_metrics",
        "reliability_v1_5_model_eligibility",
        "reliability_v1_5_validation_stability_summary",
        "reliability_v1_5_trust_summary",
        "reliability_v1_5_claim_boundary",
        "reliability_v1_5_closeout_conclusion",
    )
    registry.register(
        AdapterPermission(
            adapter_id="materials_project_trust_closeout",
            execution_allowed=False,
            allowed_modes=(),
            reason="v2.0.3 only approves reliability trust verify execution.",
        )
    )
    registry.register(
        AdapterPermission(
            adapter_id="smart_factory_trust_closeout",
            execution_allowed=False,
            allowed_modes=(),
            reason="v2.0.3 only approves reliability trust verify execution.",
        )
    )
    registry.register(
        AdapterPermission(
            adapter_id="reliability_trust_closeout",
            execution_allowed=True,
            allowed_modes=("verify",),
            allowed_read_artifact_ids=reliability_reads,
            network_allowed=False,
            raw_data_allowed=False,
            model_training_allowed=False,
            process_spawn_allowed=False,
            canonical_overwrite_allowed=False,
            max_output_files=4,
            max_output_bytes=750_000,
            timeout_seconds=30,
            reason="Read-only verification of existing tracked reliability trust artifacts.",
        )
    )
    return registry
