"""Bridge between case-study metadata and existing platform registries."""

from __future__ import annotations

from dataclasses import dataclass

from .adapter_registry import AdapterRegistry
from .artifacts import ArtifactRegistry
from .case_study_registry import CaseStudyRegistry


@dataclass(frozen=True)
class CaseStudyStagePlan:
    case_study_id: str
    plugin_id: str
    stage: str
    adapter_id: str | None
    validation_policy_id: str | None
    trust_policy_id: str | None
    required_artifacts: tuple[str, ...]
    optional_artifacts: tuple[str, ...]
    produced_artifacts: tuple[str, ...]
    missing_stage_reason: str | None
    execution_status: str
    execution_boundary: str

    def to_dict(self) -> dict[str, object]:
        return {
            "case_study_id": self.case_study_id,
            "plugin_id": self.plugin_id,
            "stage": self.stage,
            "adapter_id": self.adapter_id,
            "validation_policy_id": self.validation_policy_id,
            "trust_policy_id": self.trust_policy_id,
            "required_artifacts": list(self.required_artifacts),
            "optional_artifacts": list(self.optional_artifacts),
            "produced_artifacts": list(self.produced_artifacts),
            "missing_stage_reason": self.missing_stage_reason,
            "execution_status": self.execution_status,
            "execution_boundary": self.execution_boundary,
        }


def build_case_study_stage_plan(
    *,
    case_study_id: str,
    stage: str,
    case_study_registry: CaseStudyRegistry,
    artifact_registry: ArtifactRegistry,
    adapter_registry: AdapterRegistry,
) -> CaseStudyStagePlan:
    """Build planner input metadata without executing or importing adapters."""

    case_study = case_study_registry.get(case_study_id)
    stage_metadata = case_study.stage(stage)
    if stage_metadata is None:
        return CaseStudyStagePlan(
            case_study_id=case_study.case_study_id,
            plugin_id=case_study.plugin_id,
            stage=stage,
            adapter_id=None,
            validation_policy_id=case_study.validation_policy_id,
            trust_policy_id=case_study.trust_policy_id,
            required_artifacts=(),
            optional_artifacts=(),
            produced_artifacts=(),
            missing_stage_reason="stage_not_mapped",
            execution_status="not_available",
            execution_boundary="no_stage_metadata",
        )
    for artifact_id in (
        stage_metadata.required_artifact_ids
        + stage_metadata.optional_artifact_ids
        + stage_metadata.produced_artifact_ids
    ):
        artifact_registry.get(artifact_id)
    execution_boundary = "script_only"
    if stage_metadata.adapter_id:
        adapter = adapter_registry.get(stage_metadata.adapter_id)
        execution_boundary = "adapter_mapped_execution_disabled"
        if stage_metadata.stage in case_study.executable_stages:
            execution_boundary = "adapter_mapped_verify_allowlisted"
        if adapter.stage != stage_metadata.stage:
            raise ValueError(f"adapter {adapter.adapter_id} is not mapped to stage {stage_metadata.stage}")
    return CaseStudyStagePlan(
        case_study_id=case_study.case_study_id,
        plugin_id=case_study.plugin_id,
        stage=stage_metadata.stage,
        adapter_id=stage_metadata.adapter_id,
        validation_policy_id=case_study.validation_policy_id,
        trust_policy_id=case_study.trust_policy_id,
        required_artifacts=stage_metadata.required_artifact_ids,
        optional_artifacts=stage_metadata.optional_artifact_ids,
        produced_artifacts=stage_metadata.produced_artifact_ids,
        missing_stage_reason=stage_metadata.missing_reason,
        execution_status=stage_metadata.execution_status,
        execution_boundary=execution_boundary,
    )
