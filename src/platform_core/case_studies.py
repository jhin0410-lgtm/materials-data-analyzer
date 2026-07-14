"""Generic case-study interface metadata for the v2 platform scaffold.

This layer describes domain and lifecycle coverage. It does not replace the
plugin, adapter, artifact, validation, or trust registries, and it never
executes case-study code.
"""

from __future__ import annotations

from dataclasses import dataclass, field


CASE_STUDY_LIFECYCLE_STAGES = (
    "contract",
    "acquisition",
    "normalization",
    "readiness",
    "feature_build",
    "validation",
    "trust",
    "closeout",
    "report",
)

ALLOWED_CASE_STUDY_STATUSES = (
    "legacy_case_study",
    "interface_mapped",
    "partially_onboarded",
    "fully_onboarded",
    "deprecated_candidate",
)

ALLOWED_SIDE_EFFECT_CLASSES = (
    "none",
    "metadata_only",
    "manifest_only",
    "local_only_outputs",
    "tracked_compact_outputs",
    "external_raw",
)


@dataclass(frozen=True)
class CaseStudyStageMetadata:
    """Lifecycle-stage metadata for one case study."""

    stage: str
    adapter_id: str | None = None
    required_artifact_ids: tuple[str, ...] = ()
    optional_artifact_ids: tuple[str, ...] = ()
    produced_artifact_ids: tuple[str, ...] = ()
    execution_status: str = "not_executable"
    network_required: bool = False
    raw_data_required: bool = False
    model_training_required: bool = False
    side_effect_class: str = "metadata_only"
    description: str = ""
    missing_reason: str | None = None

    def __post_init__(self) -> None:
        if self.stage not in CASE_STUDY_LIFECYCLE_STAGES:
            raise ValueError(f"unsupported case-study stage: {self.stage}")
        if self.side_effect_class not in ALLOWED_SIDE_EFFECT_CLASSES:
            raise ValueError(f"unsupported side_effect_class: {self.side_effect_class}")
        for name, values in {
            "required_artifact_ids": self.required_artifact_ids,
            "optional_artifact_ids": self.optional_artifact_ids,
            "produced_artifact_ids": self.produced_artifact_ids,
        }.items():
            if len(set(values)) != len(values):
                raise ValueError(f"duplicate {name} for stage {self.stage}")

    def to_dict(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "adapter_id": self.adapter_id,
            "required_artifact_ids": list(self.required_artifact_ids),
            "optional_artifact_ids": list(self.optional_artifact_ids),
            "produced_artifact_ids": list(self.produced_artifact_ids),
            "execution_status": self.execution_status,
            "network_required": self.network_required,
            "raw_data_required": self.raw_data_required,
            "model_training_required": self.model_training_required,
            "side_effect_class": self.side_effect_class,
            "description": self.description,
            "missing_reason": self.missing_reason,
        }


@dataclass(frozen=True)
class CaseStudyMetadata:
    """Domain-facing case-study contract metadata."""

    case_study_id: str
    display_name: str
    domain: str
    description: str
    status: str
    plugin_id: str
    config_schema_version: str
    data_contract_id: str | None
    validation_policy_id: str | None
    trust_policy_id: str | None
    primary_unit: str
    time_key: str | None
    group_keys: tuple[str, ...]
    target_type: str
    supported_stages: tuple[str, ...]
    available_stages: tuple[str, ...]
    executable_stages: tuple[str, ...]
    local_only_policy: tuple[str, ...]
    documentation_path: str
    release_tag: str | None
    limitations: tuple[str, ...]
    stage_metadata: tuple[CaseStudyStageMetadata, ...] = ()
    interface_status: str = "interface_partial"

    def __post_init__(self) -> None:
        if not self.case_study_id:
            raise ValueError("case_study_id is required")
        if self.status not in ALLOWED_CASE_STUDY_STATUSES:
            raise ValueError(f"unsupported case-study status: {self.status}")
        for field_name, stages in {
            "supported_stages": self.supported_stages,
            "available_stages": self.available_stages,
            "executable_stages": self.executable_stages,
        }.items():
            unsupported = sorted(set(stages) - set(CASE_STUDY_LIFECYCLE_STAGES))
            if unsupported:
                raise ValueError(f"unsupported {field_name}: {unsupported}")
            if len(set(stages)) != len(stages):
                raise ValueError(f"duplicate {field_name} for {self.case_study_id}")
        available = set(self.available_stages)
        executable = set(self.executable_stages)
        if not executable.issubset(available):
            raise ValueError("executable_stages must be a subset of available_stages")
        stage_names = [stage.stage for stage in self.stage_metadata]
        if len(set(stage_names)) != len(stage_names):
            raise ValueError(f"duplicate stage_metadata for {self.case_study_id}")
        if set(stage_names) - set(self.supported_stages):
            raise ValueError("stage_metadata cannot reference unsupported stages")
        if self.status == "fully_onboarded" and set(self.supported_stages) - available:
            raise ValueError("fully_onboarded requires all supported stages to be available")

    def stage(self, stage: str) -> CaseStudyStageMetadata | None:
        for metadata in self.stage_metadata:
            if metadata.stage == stage:
                return metadata
        return None

    def missing_stages(self) -> tuple[str, ...]:
        return tuple(stage for stage in self.supported_stages if stage not in self.available_stages)

    def completeness_flags(self) -> dict[str, bool]:
        return {
            "identity_defined": bool(self.case_study_id and self.display_name and self.domain),
            "time_structure_defined": self.time_key is not None,
            "group_structure_defined": bool(self.group_keys),
            "target_defined": bool(self.target_type),
            "leakage_policy_defined": self.data_contract_id is not None,
            "validation_policy_defined": self.validation_policy_id is not None,
            "trust_policy_defined": self.trust_policy_id is not None,
            "artifacts_defined": any(
                stage.required_artifact_ids or stage.produced_artifact_ids for stage in self.stage_metadata
            ),
            "local_only_policy_defined": bool(self.local_only_policy),
            "provenance_defined": self.data_contract_id is not None,
            "tests_defined": True,
            "docs_defined": bool(self.documentation_path),
            "adapter_mapped": any(stage.adapter_id for stage in self.stage_metadata),
            "executable_allowed": bool(self.executable_stages),
        }

    def onboarding_status(self) -> str:
        flags = self.completeness_flags()
        if self.executable_stages:
            return "execution_candidate"
        if flags["adapter_mapped"]:
            return "dry_run_ready"
        if flags["identity_defined"] and flags["artifacts_defined"] and flags["docs_defined"]:
            return "metadata_ready"
        return "not_ready"

    def to_dict(self) -> dict[str, object]:
        return {
            "case_study_id": self.case_study_id,
            "display_name": self.display_name,
            "domain": self.domain,
            "description": self.description,
            "status": self.status,
            "plugin_id": self.plugin_id,
            "config_schema_version": self.config_schema_version,
            "data_contract_id": self.data_contract_id,
            "validation_policy_id": self.validation_policy_id,
            "trust_policy_id": self.trust_policy_id,
            "primary_unit": self.primary_unit,
            "time_key": self.time_key,
            "group_keys": list(self.group_keys),
            "target_type": self.target_type,
            "supported_stages": list(self.supported_stages),
            "available_stages": list(self.available_stages),
            "executable_stages": list(self.executable_stages),
            "missing_stages": list(self.missing_stages()),
            "local_only_policy": list(self.local_only_policy),
            "documentation_path": self.documentation_path,
            "release_tag": self.release_tag,
            "limitations": list(self.limitations),
            "stage_metadata": [stage.to_dict() for stage in self.stage_metadata],
            "interface_status": self.interface_status,
            "readiness_matrix": self.completeness_flags(),
            "onboarding_status": self.onboarding_status(),
        }


@dataclass(frozen=True)
class CaseStudyContract:
    """Small wrapper for exporting a stable case-study contract snapshot."""

    schema_version: str
    case_studies: tuple[CaseStudyMetadata, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "case_studies": [case_study.to_dict() for case_study in self.case_studies],
        }
