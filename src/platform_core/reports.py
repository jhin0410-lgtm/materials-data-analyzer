"""Read-only platform report data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _dict_without_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class ReportWarning:
    code: str
    message: str
    severity: str = "warning"
    case_study_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _dict_without_none(
            {
                "code": self.code,
                "message": self.message,
                "severity": self.severity,
                "case_study_id": self.case_study_id,
            }
        )


@dataclass(frozen=True)
class ArtifactReport:
    artifact_id: str
    relative_path: str
    tracked_policy: str
    local_only: bool
    exists: bool
    size_bytes: int | None = None
    sha256: str | None = None
    status: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "relative_path": self.relative_path,
            "tracked_policy": self.tracked_policy,
            "local_only": self.local_only,
            "exists": self.exists,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "status": self.status,
        }


@dataclass(frozen=True)
class StageReport:
    stage: str
    status: str
    adapter_id: str | None = None
    required_artifacts: tuple[str, ...] = ()
    produced_artifacts: tuple[str, ...] = ()
    execution_boundary: str = "unknown"
    missing_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _dict_without_none(
            {
                "stage": self.stage,
                "status": self.status,
                "adapter_id": self.adapter_id,
                "required_artifacts": list(self.required_artifacts),
                "produced_artifacts": list(self.produced_artifacts),
                "execution_boundary": self.execution_boundary,
                "missing_reason": self.missing_reason,
            }
        )


@dataclass(frozen=True)
class ValidationReport:
    policy_id: str | None
    validation_type: str | None
    primary_evidence: tuple[str, ...] = ()
    optimistic_reference: str | None = None
    claim_scope: str | None = None
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "validation_type": self.validation_type,
            "primary_evidence": list(self.primary_evidence),
            "optimistic_reference": self.optimistic_reference,
            "claim_scope": self.claim_scope,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class TrustReport:
    policy_id: str | None
    representative_model_status: str
    production_claim_allowed: bool
    calibration_boundary: str
    explainability_boundary: str
    allowed_claims: tuple[str, ...] = ()
    prohibited_claims: tuple[str, ...] = ()
    actual_closeout_status: str = "unknown"
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "representative_model_status": self.representative_model_status,
            "production_claim_allowed": self.production_claim_allowed,
            "calibration_boundary": self.calibration_boundary,
            "explainability_boundary": self.explainability_boundary,
            "allowed_claims": list(self.allowed_claims),
            "prohibited_claims": list(self.prohibited_claims),
            "actual_closeout_status": self.actual_closeout_status,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class ExecutionReport:
    adapter_id: str | None
    execution_allowed: bool
    allowed_modes: tuple[str, ...] = ()
    latest_manifest_status: str = "unavailable"
    latest_manifest_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _dict_without_none(
            {
                "adapter_id": self.adapter_id,
                "execution_allowed": self.execution_allowed,
                "allowed_modes": list(self.allowed_modes),
                "latest_manifest_status": self.latest_manifest_status,
                "latest_manifest_path": self.latest_manifest_path,
            }
        )


@dataclass(frozen=True)
class CaseStudyReport:
    case_study_id: str
    display_name: str
    domain: str
    onboarding_status: str
    plugin_status: str
    supported_stages: tuple[str, ...]
    mapped_stages: tuple[str, ...]
    executable_stages: tuple[str, ...]
    release_tag: str | None
    primary_unit: str
    target_type: str
    validation_policy: str | None
    trust_policy: str | None
    representative_model_status: str
    claim_boundary: dict[str, Any]
    tracked_artifact_count: int
    local_only_artifact_count: int
    latest_manifest_status: str
    documentation_status: str
    limitations: tuple[str, ...]
    purpose: str
    dataset_source: str
    analysis_task: str
    validation_type: str
    trust_result: str
    key_compact_results: dict[str, Any]
    stages: tuple[StageReport, ...]
    artifacts: tuple[ArtifactReport, ...]
    validation: ValidationReport
    trust: TrustReport
    execution: ExecutionReport
    warnings: tuple[ReportWarning, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_study_id": self.case_study_id,
            "display_name": self.display_name,
            "domain": self.domain,
            "onboarding_status": self.onboarding_status,
            "plugin_status": self.plugin_status,
            "supported_stages": list(self.supported_stages),
            "mapped_stages": list(self.mapped_stages),
            "executable_stages": list(self.executable_stages),
            "release_tag": self.release_tag,
            "primary_unit": self.primary_unit,
            "target_type": self.target_type,
            "validation_policy": self.validation_policy,
            "trust_policy": self.trust_policy,
            "representative_model_status": self.representative_model_status,
            "claim_boundary": self.claim_boundary,
            "tracked_artifact_count": self.tracked_artifact_count,
            "local_only_artifact_count": self.local_only_artifact_count,
            "latest_manifest_status": self.latest_manifest_status,
            "documentation_status": self.documentation_status,
            "limitations": list(self.limitations),
            "purpose": self.purpose,
            "dataset_source": self.dataset_source,
            "analysis_task": self.analysis_task,
            "validation_type": self.validation_type,
            "trust_result": self.trust_result,
            "key_compact_results": self.key_compact_results,
            "stages": [stage.to_dict() for stage in self.stages],
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "validation": self.validation.to_dict(),
            "trust": self.trust.to_dict(),
            "execution": self.execution.to_dict(),
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


@dataclass(frozen=True)
class PlatformReport:
    report_schema_version: str
    platform_version: str
    platform_status: str
    code_commit: str | None
    generated_formats: tuple[str, ...]
    case_studies: tuple[CaseStudyReport, ...]
    registry_snapshot: dict[str, Any]
    maturity_matrix: tuple[dict[str, Any], ...]
    execution_matrix: tuple[dict[str, Any], ...]
    artifact_policy_summary: dict[str, Any]
    validation_policy_summary: tuple[dict[str, Any], ...]
    trust_policy_summary: tuple[dict[str, Any], ...]
    registry_diagnostics_summary: dict[str, Any]
    scientific_trust_summary: dict[str, Any]
    pgir_governance_summary: dict[str, Any]
    pgir_conformance_summary: dict[str, Any]
    battery_pgir_summary: dict[str, Any]
    testing_summary: dict[str, Any]
    security_boundaries: tuple[str, ...]
    limitations: tuple[str, ...]
    technical_debt: tuple[str, ...]
    next_roadmap: tuple[str, ...]
    warnings: tuple[ReportWarning, ...] = ()
    scientific_recomputation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_schema_version": self.report_schema_version,
            "platform_version": self.platform_version,
            "platform_status": self.platform_status,
            "code_commit": self.code_commit,
            "generated_formats": list(self.generated_formats),
            "scientific_recomputation_performed": self.scientific_recomputation_performed,
            "case_studies": [case_study.to_dict() for case_study in self.case_studies],
            "registry_snapshot": self.registry_snapshot,
            "maturity_matrix": list(self.maturity_matrix),
            "execution_matrix": list(self.execution_matrix),
            "artifact_policy_summary": self.artifact_policy_summary,
            "validation_policy_summary": list(self.validation_policy_summary),
            "trust_policy_summary": list(self.trust_policy_summary),
            "registry_diagnostics_summary": self.registry_diagnostics_summary,
            "scientific_trust_summary": self.scientific_trust_summary,
            "pgir_governance_summary": self.pgir_governance_summary,
            "pgir_conformance_summary": self.pgir_conformance_summary,
            "battery_pgir_summary": self.battery_pgir_summary,
            "testing_summary": self.testing_summary,
            "security_boundaries": list(self.security_boundaries),
            "limitations": list(self.limitations),
            "technical_debt": list(self.technical_debt),
            "next_roadmap": list(self.next_roadmap),
            "warnings": [warning.to_dict() for warning in self.warnings],
        }
