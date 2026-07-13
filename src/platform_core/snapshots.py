"""Deterministic registry snapshots for read-only platform reporting."""

from __future__ import annotations

from typing import Any

from .adapter_registry import AdapterRegistry
from .artifacts import ArtifactRegistry
from .case_study_registry import CaseStudyRegistry
from .execution_policy import ExecutionPolicyRegistry
from .registry import PluginRegistry
from .trust_registry import TrustPolicyRegistry
from .validation_registry import ValidationPolicyRegistry


def build_registry_snapshot(
    *,
    case_study_registry: CaseStudyRegistry,
    plugin_registry: PluginRegistry,
    adapter_registry: AdapterRegistry,
    artifact_registry: ArtifactRegistry,
    validation_registry: ValidationPolicyRegistry,
    trust_registry: TrustPolicyRegistry,
    execution_policy_registry: ExecutionPolicyRegistry,
) -> dict[str, Any]:
    """Return deterministic registry metadata without timestamps or local paths."""

    return {
        "case_studies": case_study_registry.snapshot(),
        "plugins": plugin_registry.snapshot(),
        "adapters": adapter_registry.snapshot(),
        "artifacts": artifact_registry.snapshot(),
        "validation_policies": validation_registry.snapshot(),
        "trust_policies": trust_registry.snapshot(),
        "execution_policies": execution_policy_registry.snapshot(),
    }


def summarize_registry_snapshot(snapshot: dict[str, Any]) -> dict[str, int]:
    """Compact count summary used by report manifests and CLI previews."""

    return {
        "case_study_count": len(snapshot.get("case_studies", [])),
        "plugin_count": len(snapshot.get("plugins", [])),
        "adapter_count": len(snapshot.get("adapters", [])),
        "artifact_count": len(snapshot.get("artifacts", [])),
        "validation_policy_count": len(snapshot.get("validation_policies", [])),
        "trust_policy_count": len(snapshot.get("trust_policies", [])),
        "execution_policy_count": len(snapshot.get("execution_policies", [])),
    }
