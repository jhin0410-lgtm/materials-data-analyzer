"""Read-only platform report generation."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapter_registry import AdapterRegistry, build_default_adapter_registry
from .artifact_resolver import ArtifactResolver, calculate_sha256
from .artifacts import ArtifactRegistry, build_default_artifact_registry, validate_relative_path
from .case_study_registry import CaseStudyRegistry, build_default_case_study_registry
from .execution_policy import ExecutionPolicyRegistry, build_default_execution_policy_registry
from .registry import PluginRegistry, build_default_plugin_registry
from .report_extractors import extract_case_study_results
from .reports import (
    ArtifactReport,
    CaseStudyReport,
    ExecutionReport,
    PlatformReport,
    ReportWarning,
    StageReport,
    TrustReport,
    ValidationReport,
)
from .snapshots import build_registry_snapshot, summarize_registry_snapshot
from .trust_registry import TrustPolicyRegistry, build_default_trust_policy_registry
from .validation_registry import ValidationPolicyRegistry, build_default_validation_policy_registry
from .version import PLATFORM_VERSION


REPORT_SCHEMA_VERSION = "2.0"
ALLOWED_REPORT_FORMATS = ("json", "markdown")
DEFAULT_REPORT_OUTPUT_DIR = "outputs/platform_reports/platform_v2_report"
MAX_REPORT_FILE_BYTES = 5_000_000


@dataclass(frozen=True)
class ReportGenerationResult:
    report: PlatformReport
    manifest: dict[str, Any]
    output_dir: str | None
    written_files: tuple[str, ...]

    def summary(self) -> dict[str, Any]:
        return {
            "report_id": self.manifest["report_id"],
            "generation_status": self.manifest["generation_status"],
            "platform_version": self.report.platform_version,
            "case_study_ids": list(self.manifest["case_study_ids"]),
            "generated_formats": list(self.manifest["generated_formats"]),
            "scientific_recomputation_performed": self.report.scientific_recomputation_performed,
            "output_dir": self.output_dir,
            "written_files": list(self.written_files),
            "warning_count": len(self.report.warnings),
        }


@dataclass(frozen=True)
class _RegistryBundle:
    plugin_registry: PluginRegistry
    artifact_registry: ArtifactRegistry
    validation_registry: ValidationPolicyRegistry
    trust_registry: TrustPolicyRegistry
    adapter_registry: AdapterRegistry
    execution_policy_registry: ExecutionPolicyRegistry
    case_study_registry: CaseStudyRegistry


def build_default_report_registries() -> _RegistryBundle:
    plugin_registry = build_default_plugin_registry()
    artifact_registry = build_default_artifact_registry()
    validation_registry = build_default_validation_policy_registry()
    trust_registry = build_default_trust_policy_registry()
    adapter_registry = build_default_adapter_registry(plugin_registry, artifact_registry)
    execution_policy_registry = build_default_execution_policy_registry()
    case_study_registry = build_default_case_study_registry(
        plugin_registry,
        artifact_registry,
        validation_registry,
        trust_registry,
        adapter_registry,
    )
    return _RegistryBundle(
        plugin_registry=plugin_registry,
        artifact_registry=artifact_registry,
        validation_registry=validation_registry,
        trust_registry=trust_registry,
        adapter_registry=adapter_registry,
        execution_policy_registry=execution_policy_registry,
        case_study_registry=case_study_registry,
    )


def load_report_config(config_path: str | Path) -> dict[str, Any]:
    with Path(config_path).open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise ValueError("report config must be a JSON object")
    validate_report_config(config)
    return config


def validate_report_config(config: dict[str, Any]) -> None:
    if config.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ValueError(f"unsupported report schema_version: {config.get('schema_version')}")
    report_id = config.get("report_id")
    if not isinstance(report_id, str) or not report_id:
        raise ValueError("report_id is required")
    _validate_safe_identifier(report_id, "report_id")
    formats = config.get("formats", ["json", "markdown"])
    if not isinstance(formats, list) or not formats:
        raise ValueError("formats must be a non-empty list")
    unsupported = sorted(set(formats) - set(ALLOWED_REPORT_FORMATS))
    if unsupported:
        raise ValueError(f"unsupported report format(s): {unsupported}")
    selected = config.get("selected_case_studies", [])
    if selected and (not isinstance(selected, list) or not all(isinstance(item, str) for item in selected)):
        raise ValueError("selected_case_studies must be a list of strings")
    output_dir = config.get("output_dir", DEFAULT_REPORT_OUTPUT_DIR)
    if not isinstance(output_dir, str):
        raise ValueError("output_dir must be a repository-relative path")
    _validate_output_dir_string(output_dir)
    testing_summary = config.get("testing_summary", {})
    if testing_summary and not isinstance(testing_summary, dict):
        raise ValueError("testing_summary must be an object")
    credential_policy = config.get("credential_policy", {})
    if credential_policy and not isinstance(credential_policy, dict):
        raise ValueError("credential_policy must be an object")
    if credential_policy.get("store_credentials") is True:
        raise ValueError("report configs cannot store credentials")
    if "include_registry_diagnostics" in config and not isinstance(config["include_registry_diagnostics"], bool):
        raise ValueError("include_registry_diagnostics must be a boolean")
    registry_path = config.get("registry_path")
    if registry_path is not None:
        if not isinstance(registry_path, str):
            raise ValueError("registry_path must be a repository-relative path")
        validate_relative_path(registry_path)
        if not registry_path.replace("\\", "/").startswith("outputs/platform_registry/"):
            raise ValueError("registry_path must be under outputs/platform_registry")


def _validate_safe_identifier(value: str, field_name: str) -> None:
    if "/" in value or "\\" in value or ".." in value or ":" in value:
        raise ValueError(f"{field_name} must not contain path characters")


def _validate_output_dir_string(output_dir: str) -> None:
    validate_relative_path(output_dir)
    normalized = output_dir.replace("\\", "/")
    if not normalized.startswith("outputs/platform_reports/"):
        raise ValueError("report output_dir must be under outputs/platform_reports/")


def _read_git_commit(repo_root: Path) -> str | None:
    git_dir = repo_root / ".git"
    head_path = git_dir / "HEAD"
    try:
        head = head_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if head.startswith("ref: "):
        ref_name = head[5:].strip()
        if ".." in ref_name or ref_name.startswith("/") or "\\" in ref_name:
            return None
        ref_path = (git_dir / ref_name).resolve()
        if git_dir.resolve() != ref_path and git_dir.resolve() not in ref_path.parents:
            return None
        try:
            value = ref_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return value or None
    return head or None


def _artifact_report(resolved) -> ArtifactReport:
    status = "available" if resolved.exists else "missing"
    return ArtifactReport(
        artifact_id=resolved.artifact.artifact_id,
        relative_path=resolved.relative_path,
        tracked_policy=resolved.artifact.tracked_policy,
        local_only=resolved.artifact.local_only,
        exists=resolved.exists,
        size_bytes=resolved.size_bytes,
        sha256=resolved.sha256,
        status=status,
    )


def _build_stage_reports(case_study, adapter_registry: AdapterRegistry) -> tuple[StageReport, ...]:
    reports: list[StageReport] = []
    for stage in case_study.supported_stages:
        metadata = case_study.stage(stage)
        if metadata is None:
            reports.append(
                StageReport(
                    stage=stage,
                    status="unavailable",
                    execution_boundary="not_mapped",
                    missing_reason="stage is supported but not mapped in the v2 registry",
                )
            )
            continue
        execution_boundary = metadata.execution_status
        if metadata.adapter_id:
            adapter = adapter_registry.get(metadata.adapter_id)
            execution_boundary = "execution_disabled" if not adapter.execution_allowed else "controlled_execution"
        reports.append(
            StageReport(
                stage=stage,
                status=metadata.execution_status,
                adapter_id=metadata.adapter_id,
                required_artifacts=metadata.required_artifact_ids,
                produced_artifacts=metadata.produced_artifact_ids,
                execution_boundary=execution_boundary,
                missing_reason=metadata.missing_reason,
            )
        )
    return tuple(reports)


def _build_validation_report(case_study, validation_registry: ValidationPolicyRegistry) -> ValidationReport:
    if case_study.validation_policy_id is None:
        return ValidationReport(
            policy_id=None,
            validation_type=None,
            summary={"status": "unavailable"},
        )
    policy = validation_registry.get(case_study.validation_policy_id)
    return ValidationReport(
        policy_id=policy.policy_id,
        validation_type=policy.validation_type,
        primary_evidence=policy.primary_evidence,
        optimistic_reference=policy.optimistic_reference,
        claim_scope=policy.claim_scope,
        summary={
            "overlap_rules": list(policy.overlap_rules),
            "preprocessing_scope": policy.preprocessing_scope,
            "metric_family": list(policy.metric_family),
        },
    )


def _build_trust_report(case_study, trust_registry: TrustPolicyRegistry, actual_status: str, summary: dict[str, Any]) -> TrustReport:
    if case_study.trust_policy_id is None:
        return TrustReport(
            policy_id=None,
            representative_model_status=summary.get("representative_model", "unavailable"),
            production_claim_allowed=False,
            calibration_boundary="unavailable",
            explainability_boundary="unavailable",
            actual_closeout_status=actual_status,
            summary=summary,
        )
    policy = trust_registry.get(case_study.trust_policy_id)
    return TrustReport(
        policy_id=policy.policy_id,
        representative_model_status=summary.get("representative_model", summary.get("representative_model_decision", "unavailable")),
        production_claim_allowed=policy.production_claim_allowed,
        calibration_boundary=policy.calibration_boundary,
        explainability_boundary=policy.explainability_boundary,
        allowed_claims=policy.allowed_claims,
        prohibited_claims=policy.prohibited_claims,
        actual_closeout_status=actual_status,
        summary=summary,
    )


def _build_execution_report(case_study, adapter_registry: AdapterRegistry, execution_policy_registry: ExecutionPolicyRegistry) -> ExecutionReport:
    trust_stage = case_study.stage("trust")
    adapter_id = trust_stage.adapter_id if trust_stage else None
    if adapter_id is None:
        return ExecutionReport(adapter_id=None, execution_allowed=False)
    try:
        permission = execution_policy_registry.get(adapter_id)
        return ExecutionReport(
            adapter_id=adapter_id,
            execution_allowed=permission.execution_allowed,
            allowed_modes=permission.allowed_modes,
            latest_manifest_status="not_inspected",
        )
    except KeyError:
        return ExecutionReport(
            adapter_id=adapter_id,
            execution_allowed=False,
            latest_manifest_status="execution_policy_missing",
        )


def _build_case_study_report(
    case_study_id: str,
    *,
    registries: _RegistryBundle,
    resolver: ArtifactResolver,
) -> CaseStudyReport:
    case_study = registries.case_study_registry.get(case_study_id)
    plugin = registries.plugin_registry.get(case_study.plugin_id)
    extracted = extract_case_study_results(case_study_id, resolver)
    case_artifacts = registries.artifact_registry.list_artifacts(case_study_id)
    tracked_count = sum(not artifact.local_only for artifact in case_artifacts)
    local_count = sum(artifact.local_only for artifact in case_artifacts)
    mapped_stages = tuple(stage.stage for stage in case_study.stage_metadata if stage.adapter_id is not None)
    artifacts = tuple(_artifact_report(resolved) for resolved in extracted.artifacts)
    return CaseStudyReport(
        case_study_id=case_study.case_study_id,
        display_name=case_study.display_name,
        domain=case_study.domain,
        onboarding_status=case_study.onboarding_status(),
        plugin_status=plugin.status,
        supported_stages=case_study.supported_stages,
        mapped_stages=mapped_stages,
        executable_stages=case_study.executable_stages,
        release_tag=case_study.release_tag,
        primary_unit=case_study.primary_unit,
        target_type=case_study.target_type,
        validation_policy=case_study.validation_policy_id,
        trust_policy=case_study.trust_policy_id,
        representative_model_status=extracted.representative_model_status,
        claim_boundary=extracted.claim_boundary,
        tracked_artifact_count=tracked_count,
        local_only_artifact_count=local_count,
        latest_manifest_status="not_inspected",
        documentation_status="documented" if case_study.documentation_path else "missing",
        limitations=case_study.limitations,
        purpose=extracted.purpose,
        dataset_source=extracted.dataset_source,
        analysis_task=extracted.analysis_task,
        validation_type=extracted.validation_type,
        trust_result=extracted.trust_result,
        key_compact_results=extracted.key_compact_results,
        stages=_build_stage_reports(case_study, registries.adapter_registry),
        artifacts=artifacts,
        validation=_build_validation_report(case_study, registries.validation_registry),
        trust=_build_trust_report(
            case_study,
            registries.trust_registry,
            extracted.trust_result,
            extracted.key_compact_results,
        ),
        execution=_build_execution_report(case_study, registries.adapter_registry, registries.execution_policy_registry),
        warnings=extracted.warnings,
    )


def _maturity_matrix(case_reports: tuple[CaseStudyReport, ...]) -> tuple[dict[str, Any], ...]:
    stages = ("contract", "acquisition", "normalization", "readiness", "feature_build", "validation", "trust", "closeout", "report")
    rows: list[dict[str, Any]] = []
    for report in case_reports:
        stage_status = {stage.stage: stage.status for stage in report.stages}
        row = {
            "case_study_id": report.case_study_id,
            "release_tag": report.release_tag,
            "dry_run_ready": report.onboarding_status in {"dry_run_ready", "execution_candidate"},
            "executable": bool(report.executable_stages),
        }
        for stage in stages:
            if stage == "report":
                row[stage] = "mapped"
            else:
                row[stage] = stage_status.get(stage, "unavailable")
        rows.append(row)
    return tuple(rows)


def _execution_matrix(adapter_registry: AdapterRegistry, execution_policy_registry: ExecutionPolicyRegistry) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for adapter in adapter_registry.list_adapters():
        permission = None
        try:
            permission = execution_policy_registry.get(adapter.adapter_id)
        except KeyError:
            pass
        rows.append(
            {
                "adapter_id": adapter.adapter_id,
                "plugin_id": adapter.plugin_id,
                "stage": adapter.stage,
                "dry_run_status": "dry_run_safe" if adapter.execution_policy.safe_for_dry_run else "not_dry_run_safe",
                "execution_allowed": bool(permission.execution_allowed) if permission else False,
                "allowed_mode": list(permission.allowed_modes) if permission else [],
                "network_required": adapter.execution_policy.network_required,
                "raw_required": adapter.execution_policy.raw_data_required,
                "model_training_required": adapter.execution_policy.model_training_required,
                "side_effect_class": "manifest_or_controlled_output" if adapter.execution_policy.writes_outputs else "none",
                "latest_verified_run": "not_inspected",
                "latest_run_status": "not_inspected",
            }
        )
    return tuple(rows)


def _artifact_policy_summary(artifact_registry: ArtifactRegistry) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for artifact in artifact_registry.list_artifacts():
        counts[artifact.tracked_policy] = counts.get(artifact.tracked_policy, 0) + 1
    return {
        "tracked_policy_counts": counts,
        "raw_data_policy": "external raw and data/raw artifacts stay local-only",
        "row_level_policy": "large analysis-ready tables and prediction outputs stay local-only",
        "report_output_policy": "platform reports are generated under ignored outputs/platform_reports",
    }


def _registry_diagnostics_summary(config: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    if config.get("include_registry_diagnostics") is not True:
        return {"status": "not_requested"}
    from .run_registry import DEFAULT_REGISTRY_PATH, resolve_registry_path

    registry_path = str(config.get("registry_path") or DEFAULT_REGISTRY_PATH)
    target = resolve_registry_path(repo_root, registry_path)
    if not target.exists():
        return {"status": "registry_not_found", "registry_path": registry_path}
    with sqlite3.connect(target) as connection:
        connection.row_factory = sqlite3.Row
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('diagnostic_evaluations', 'diagnostic_findings', 'evidence_gaps')"
            )
        }
        if "diagnostic_evaluations" not in tables:
            return {"status": "diagnostic_tables_missing", "registry_path": registry_path}
        evaluation_count = connection.execute("SELECT COUNT(*) AS count FROM diagnostic_evaluations").fetchone()["count"]
        finding_count = connection.execute("SELECT COUNT(*) AS count FROM diagnostic_findings").fetchone()["count"] if "diagnostic_findings" in tables else 0
        blocker_count = connection.execute(
            "SELECT COUNT(*) AS count FROM diagnostic_findings WHERE severity = 'blocker' AND status = 'violated'"
        ).fetchone()["count"] if "diagnostic_findings" in tables else 0
        gap_count = connection.execute("SELECT COUNT(*) AS count FROM evidence_gaps").fetchone()["count"] if "evidence_gaps" in tables else 0
        latest = connection.execute(
            "SELECT evaluation_id, run_id, overall_status, promotion_status FROM diagnostic_evaluations ORDER BY evaluated_at DESC, evaluation_id DESC LIMIT 1"
        ).fetchone()
    return {
        "status": "available",
        "registry_path": registry_path,
        "evaluation_count": int(evaluation_count),
        "finding_count": int(finding_count),
        "blocker_count": int(blocker_count),
        "evidence_gap_count": int(gap_count),
        "latest_evaluation": dict(latest) if latest is not None else None,
    }


def build_platform_report(config: dict[str, Any], *, repo_root: str | Path = ".") -> PlatformReport:
    validate_report_config(config)
    root = Path(repo_root).resolve()
    registries = build_default_report_registries()
    selected_case_studies = tuple(config.get("selected_case_studies") or [case.case_study_id for case in registries.case_study_registry.list_case_studies()])
    available_case_studies = {case.case_study_id for case in registries.case_study_registry.list_case_studies()}
    unknown = sorted(set(selected_case_studies) - available_case_studies)
    if unknown:
        raise KeyError(f"unknown case_study_id(s): {unknown}")
    resolver = ArtifactResolver(root, registries.artifact_registry)
    case_reports = tuple(
        _build_case_study_report(case_study_id, registries=registries, resolver=resolver)
        for case_study_id in selected_case_studies
    )
    registry_snapshot = build_registry_snapshot(
        case_study_registry=registries.case_study_registry,
        plugin_registry=registries.plugin_registry,
        adapter_registry=registries.adapter_registry,
        artifact_registry=registries.artifact_registry,
        validation_registry=registries.validation_registry,
        trust_registry=registries.trust_registry,
        execution_policy_registry=registries.execution_policy_registry,
    )
    warnings = tuple(warning for report in case_reports for warning in report.warnings)
    testing_summary = {
        "current_report_generation_executed_tests": False,
        "source": "report_config_or_known_release_context",
        **dict(config.get("testing_summary", {})),
    }
    return PlatformReport(
        report_schema_version=REPORT_SCHEMA_VERSION,
        platform_version=PLATFORM_VERSION,
        platform_status="v2.0_closeout_candidate",
        code_commit=_read_git_commit(root),
        generated_formats=tuple(config.get("formats", ["json", "markdown"])),
        case_studies=case_reports,
        registry_snapshot=registry_snapshot,
        maturity_matrix=_maturity_matrix(case_reports),
        execution_matrix=_execution_matrix(registries.adapter_registry, registries.execution_policy_registry),
        artifact_policy_summary=_artifact_policy_summary(registries.artifact_registry),
        validation_policy_summary=tuple(registries.validation_registry.snapshot()),
        trust_policy_summary=tuple(registries.trust_registry.snapshot()),
        registry_diagnostics_summary=_registry_diagnostics_summary(config, root),
        testing_summary=testing_summary,
        security_boundaries=(
            "no acquisition, normalization, feature engineering, model training, or trust rerun",
            "no raw/local-only dataset or row-level prediction reads",
            "no arbitrary template execution, subprocess, network, or shell execution",
            "report outputs are local-only under outputs/platform_reports",
        ),
        limitations=(
            "report summarizes existing compact artifacts and registry metadata only",
            "Battery Archive does not yet have a standardized v2 trust adapter",
            "latest CI status is supplied as metadata, not executed by the report engine",
        ),
        technical_debt=(
            "registry snapshot is generated from code and should be refreshed when registry metadata changes",
            "HTML/PDF/dashboard reporting remains out of scope",
            "future v2.1 work can add richer report templates after more adapters become executable",
        ),
        next_roadmap=(
            "v2.0 release audit",
            "v2.1 executable pipeline orchestration for selected safe stages",
            "optional unified report generation improvements without changing scientific results",
        ),
        warnings=warnings,
        scientific_recomputation_performed=False,
    )


def render_report_json(report: PlatformReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"


def _markdown_table(headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return lines


def render_report_markdown(report: PlatformReport) -> str:
    lines: list[str] = [
        "# Platform Report",
        "",
        "## Executive Summary",
        f"- Platform version: `{report.platform_version}`",
        f"- Platform status: `{report.platform_status}`",
        f"- Case studies represented: `{len(report.case_studies)}`",
        "- Scientific recomputation performed: `false`",
        "- This report is a read-only summary of registries and tracked compact artifacts.",
        "",
        "## Registered Case Studies",
    ]
    lines.extend(
        _markdown_table(
            ("Case Study", "Release", "Validation", "Trust Result", "Representative Model"),
            [
                (
                    case.display_name,
                    case.release_tag or "unavailable",
                    case.validation_type,
                    case.trust_result,
                    case.representative_model_status,
                )
                for case in report.case_studies
            ],
        )
    )
    lines.extend(["", "## Case-Study Onboarding Matrix"])
    lines.extend(
        _markdown_table(
            ("Case Study", "Onboarding", "Plugin", "Mapped Stages", "Executable Stages"),
            [
                (
                    case.case_study_id,
                    case.onboarding_status,
                    case.plugin_status,
                    ", ".join(case.mapped_stages) or "none",
                    ", ".join(case.executable_stages) or "none",
                )
                for case in report.case_studies
            ],
        )
    )
    lines.extend(["", "## Lifecycle-Stage Coverage"])
    maturity_rows = [
        (
            row["case_study_id"],
            row["contract"],
            row["acquisition"],
            row["normalization"],
            row["validation"],
            row["trust"],
            row["closeout"],
            row["report"],
        )
        for row in report.maturity_matrix
    ]
    lines.extend(
        _markdown_table(
            ("Case Study", "Contract", "Acquisition", "Normalization", "Validation", "Trust", "Closeout", "Report"),
            maturity_rows,
        )
    )
    lines.extend(["", "## Plugin/Adapter Execution Matrix"])
    lines.extend(
        _markdown_table(
            ("Adapter", "Plugin", "Stage", "Dry Run", "Execution Allowed", "Modes"),
            [
                (
                    row["adapter_id"],
                    row["plugin_id"],
                    row["stage"],
                    row["dry_run_status"],
                    row["execution_allowed"],
                    ", ".join(row["allowed_mode"]) or "none",
                )
                for row in report.execution_matrix
            ],
        )
    )
    lines.extend(["", "## Artifact Policy Summary"])
    for key, value in report.artifact_policy_summary.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Validation Policy Summary"])
    lines.extend(
        _markdown_table(
            ("Policy", "Type", "Primary Evidence", "Optimistic Reference", "Claim Scope"),
            [
                (
                    policy["policy_id"],
                    policy["validation_type"],
                    ", ".join(policy["primary_evidence"]) or "none",
                    policy["optimistic_reference"] or "none",
                    policy["claim_scope"],
                )
                for policy in report.validation_policy_summary
            ],
        )
    )
    lines.extend(["", "## Trust Policy Summary"])
    lines.extend(
        _markdown_table(
            ("Policy", "Production Claim", "Calibration Boundary", "Explainability Boundary"),
            [
                (
                    policy["policy_id"],
                    policy["production_claim_allowed"],
                    policy["calibration_boundary"],
                    policy["explainability_boundary"],
                )
                for policy in report.trust_policy_summary
            ],
        )
    )
    lines.extend(["", "## Registry Diagnostics Summary"])
    for key, value in sorted(report.registry_diagnostics_summary.items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Case-Study Result Summaries"])
    for case in report.case_studies:
        lines.extend(
            [
                "",
                f"### {case.display_name}",
                f"- Purpose: {case.purpose}",
                f"- Dataset/source: {case.dataset_source}",
                f"- Analysis task: {case.analysis_task}",
                f"- Validation type: {case.validation_type}",
                f"- Trust result: `{case.trust_result}`",
                f"- Representative model status: `{case.representative_model_status}`",
                f"- Documentation status: `{case.documentation_status}`",
                "- Key compact results:",
            ]
        )
        for key, value in sorted(case.key_compact_results.items()):
            lines.append(f"  - `{key}`: `{value}`")
        lines.append("- Limitations:")
        for limitation in case.limitations:
            lines.append(f"  - {limitation}")
    lines.extend(["", "## Scientific Claim Boundaries"])
    for case in report.case_studies:
        lines.append(f"- `{case.case_study_id}`: production claims allowed = `{case.trust.production_claim_allowed}`; representative model = `{case.representative_model_status}`")
    lines.extend(["", "## Data And Local-Only Policy"])
    lines.append("- Raw archives, large analysis-ready tables, row-level predictions, and report outputs remain local-only.")
    lines.append("- Tracked artifacts are compact summaries, manifests, contracts, schemas, tests, and documentation.")
    lines.extend(["", "## CI/Testing Summary"])
    for key, value in sorted(report.testing_summary.items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Security Boundaries"])
    for boundary in report.security_boundaries:
        lines.append(f"- {boundary}")
    lines.extend(["", "## Current Limitations"])
    for limitation in report.limitations:
        lines.append(f"- {limitation}")
    lines.extend(["", "## Technical Debt"])
    for debt in report.technical_debt:
        lines.append(f"- {debt}")
    lines.extend(["", "## Next Roadmap"])
    for item in report.next_roadmap:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _resolve_report_output_dir(repo_root: Path, output_dir: str) -> Path:
    _validate_output_dir_string(output_dir)
    target = (repo_root / output_dir).resolve()
    allowed_root = (repo_root / "outputs" / "platform_reports").resolve()
    if allowed_root != target and allowed_root not in target.parents:
        raise ValueError("report output escapes outputs/platform_reports")
    if target.exists() and target.is_symlink():
        raise ValueError("report output directory cannot be a symlink")
    return target


def _atomic_write_text(path: Path, content: str, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing report file: {path.name}")
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_REPORT_FILE_BYTES:
        raise ValueError(f"report file exceeds max bytes: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=path.parent, prefix=f".{path.name}.", suffix=".tmp") as handle:
        temp_path = Path(handle.name)
        handle.write(encoded)
    try:
        if overwrite:
            temp_path.replace(path)
        else:
            temp_path.rename(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _build_manifest(
    *,
    report: PlatformReport,
    report_id: str,
    repo_root: Path,
    written_files: tuple[str, ...],
    source_artifacts: tuple[ArtifactReport, ...],
) -> dict[str, Any]:
    output_checksums: dict[str, str] = {}
    for relative_file in written_files:
        if relative_file.endswith("report_manifest.json"):
            continue
        path = (repo_root / relative_file).resolve()
        try:
            path.relative_to(repo_root)
        except ValueError:
            raise ValueError(f"report output escapes repository root: {relative_file}") from None
        if path.exists():
            output_checksums[relative_file] = calculate_sha256(path)
    source_checksums = {
        artifact.relative_path: artifact.sha256
        for artifact in source_artifacts
        if artifact.sha256
    }
    return {
        "report_id": report_id,
        "report_schema_version": report.report_schema_version,
        "platform_version": report.platform_version,
        "code_commit": report.code_commit,
        "generated_formats": list(report.generated_formats),
        "source_registry_snapshot": summarize_registry_snapshot(report.registry_snapshot),
        "source_artifacts": [artifact.relative_path for artifact in source_artifacts],
        "source_artifact_checksums": source_checksums,
        "case_study_ids": [case.case_study_id for case in report.case_studies],
        "warnings": [warning.to_dict() for warning in report.warnings],
        "errors": [],
        "output_files": list(written_files),
        "output_checksums": output_checksums,
        "generation_status": "completed" if written_files else "preview_only",
        "local_only": True,
        "scientific_recomputation_performed": False,
    }


def generate_report(
    config: dict[str, Any],
    *,
    repo_root: str | Path = ".",
    write: bool = True,
    output_dir_override: str | None = None,
    report_id_override: str | None = None,
    formats_override: tuple[str, ...] | None = None,
    overwrite: bool | None = None,
) -> ReportGenerationResult:
    config = dict(config)
    if report_id_override is not None:
        config["report_id"] = report_id_override
    if output_dir_override is not None:
        config["output_dir"] = output_dir_override
    if formats_override is not None:
        config["formats"] = list(formats_override)
    validate_report_config(config)
    report = build_platform_report(config, repo_root=repo_root)
    repo = Path(repo_root).resolve()
    output_dir = config.get("output_dir", DEFAULT_REPORT_OUTPUT_DIR)
    generated_files: list[str] = []
    source_artifacts = tuple(artifact for case in report.case_studies for artifact in case.artifacts)
    manifest = _build_manifest(
        report=report,
        report_id=config["report_id"],
        repo_root=repo,
        written_files=(),
        source_artifacts=source_artifacts,
    )
    if write:
        target_dir = _resolve_report_output_dir(repo, output_dir)
        overwrite_flag = bool(config.get("overwrite") if overwrite is None else overwrite)
        formats = tuple(config.get("formats", ["json", "markdown"]))
        rendered: dict[str, str] = {}
        if "json" in formats:
            rendered["platform_report.json"] = render_report_json(report)
        if "markdown" in formats:
            rendered["platform_report.md"] = render_report_markdown(report)
        for filename, content in rendered.items():
            _atomic_write_text(target_dir / filename, content, overwrite=overwrite_flag)
            generated_files.append(str((target_dir / filename).relative_to(repo)).replace("\\", "/"))
        manifest = _build_manifest(
            report=report,
            report_id=config["report_id"],
            repo_root=repo,
            written_files=tuple(generated_files),
            source_artifacts=source_artifacts,
        )
        manifest_content = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        _atomic_write_text(target_dir / "report_manifest.json", manifest_content, overwrite=overwrite_flag)
        generated_files.append(str((target_dir / "report_manifest.json").relative_to(repo)).replace("\\", "/"))
        manifest = _build_manifest(
            report=report,
            report_id=config["report_id"],
            repo_root=repo,
            written_files=tuple(generated_files),
            source_artifacts=source_artifacts,
        )
        manifest_content = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        _atomic_write_text(target_dir / "report_manifest.json", manifest_content, overwrite=True)
    return ReportGenerationResult(
        report=report,
        manifest=manifest,
        output_dir=output_dir if write else None,
        written_files=tuple(generated_files),
    )


def load_report_manifest(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if target.is_dir():
        target = target / "report_manifest.json"
    with target.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    validate_report_manifest(manifest, manifest_path=target)
    return manifest


def validate_report_manifest(manifest: dict[str, Any], *, manifest_path: str | Path | None = None) -> None:
    required = (
        "report_id",
        "report_schema_version",
        "platform_version",
        "generated_formats",
        "source_registry_snapshot",
        "source_artifacts",
        "case_study_ids",
        "output_files",
        "output_checksums",
        "generation_status",
        "local_only",
        "scientific_recomputation_performed",
    )
    missing = [field for field in required if field not in manifest]
    if missing:
        raise ValueError(f"report manifest missing fields: {missing}")
    if manifest["report_schema_version"] != REPORT_SCHEMA_VERSION:
        raise ValueError("unsupported report manifest schema version")
    if manifest["local_only"] is not True:
        raise ValueError("report manifest must be local_only")
    if manifest["scientific_recomputation_performed"] is not False:
        raise ValueError("report manifest must record no scientific recomputation")
    for output_file in manifest.get("output_files", []):
        if not isinstance(output_file, str):
            raise ValueError("output_files entries must be strings")
        validate_relative_path(output_file)
        if not output_file.replace("\\", "/").startswith("outputs/platform_reports/"):
            raise ValueError(f"report output outside platform report area: {output_file}")
    if manifest_path is not None:
        root = Path.cwd().resolve()
        for output_file, expected_sha in manifest.get("output_checksums", {}).items():
            output_path = (root / output_file).resolve()
            if not output_path.exists():
                raise FileNotFoundError(f"report output missing: {output_file}")
            actual_sha = calculate_sha256(output_path)
            if actual_sha != expected_sha:
                raise ValueError(f"report checksum mismatch: {output_file}")


def load_report_json(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if target.is_dir():
        target = target / "platform_report.json"
    with target.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("scientific_recomputation_performed") is not False:
        raise ValueError("report must record no scientific recomputation")
    return payload
