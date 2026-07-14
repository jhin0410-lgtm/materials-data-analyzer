"""Controlled adapter execution runtime."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .adapter_registry import AdapterRegistry
from .artifact_resolver import ArtifactResolver
from .artifacts import ArtifactRegistry, validate_relative_path
from .config import ConfigValidationResult
from .execution_policy import AdapterPermission, ExecutionPolicyRegistry
from .manifests import (
    build_run_id,
    calculate_config_sha256,
    read_git_commit,
    validate_run_manifest,
    write_run_manifest,
)
from .planner import DryRunPlan
from .registry import PluginRegistry
from .side_effects import (
    create_side_effect_snapshot,
    evaluate_side_effects,
    write_side_effect_report,
)
from .trust_registry import TrustPolicyRegistry


EXECUTION_STATUSES = (
    "planned",
    "preflight_validated",
    "execution_started",
    "execution_completed",
    "verification_completed",
    "blocked",
    "failed",
    "side_effect_violation",
)


class PlatformExecutionError(RuntimeError):
    exit_code = 8


class AdapterExecutionDisabled(PlatformExecutionError):
    exit_code = 4


class MissingArtifactError(PlatformExecutionError):
    exit_code = 5


class SideEffectViolationError(PlatformExecutionError):
    exit_code = 6


class VerificationMismatchError(PlatformExecutionError):
    exit_code = 7


class PathPolicyError(PlatformExecutionError):
    exit_code = 9


@dataclass(frozen=True)
class ExecutionContext:
    adapter_id: str
    plugin_id: str
    stage: str
    execution_mode: str
    run_id: str
    repository_root: Path
    isolated_output_dir: Path
    artifacts_dir: Path
    logs_dir: Path
    artifact_resolver: ArtifactResolver
    config: dict[str, Any]
    execution_policy: AdapterPermission
    dry_run: bool
    verification_only: bool


@dataclass(frozen=True)
class AdapterExecutionResult:
    status: str
    produced_files: tuple[str, ...]
    warnings: tuple[str, ...]
    metrics_summary: dict[str, Any]
    claim_boundary: dict[str, Any]
    input_checksums: dict[str, str]
    output_checksums: dict[str, str]
    side_effect_summary: dict[str, Any]
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "produced_files": list(self.produced_files),
            "warnings": list(self.warnings),
            "metrics_summary": self.metrics_summary,
            "claim_boundary": self.claim_boundary,
            "input_checksums": self.input_checksums,
            "output_checksums": self.output_checksums,
            "side_effect_summary": self.side_effect_summary,
            "errors": list(self.errors),
        }


AdapterCallable = Callable[[ExecutionContext], AdapterExecutionResult]


def resolve_output_directory(repository_root: str | Path, output_directory: str) -> Path:
    validate_relative_path(output_directory)
    root = Path(repository_root).resolve()
    target = (root / output_directory).resolve()
    if root != target and root not in target.parents:
        raise PathPolicyError("output directory must stay inside repository root")
    if "outputs/platform_runs" not in target.as_posix().replace("\\", "/"):
        raise PathPolicyError("output directory must be under outputs/platform_runs")
    return target


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def build_execution_manifest(
    *,
    config: dict[str, Any],
    validation: ConfigValidationResult,
    plan: DryRunPlan,
    permission: AdapterPermission | None,
    artifact_registry: ArtifactRegistry,
    trust_registry: TrustPolicyRegistry,
    repository_root: str | Path,
    run_id: str,
    output_directory: str,
    status: str,
    execution_mode: str,
    started_at: str | None = None,
    completed_at: str | None = None,
    duration_seconds: float | None = None,
    result: AdapterExecutionResult | None = None,
    side_effect_report: str | None = None,
    errors: tuple[str, ...] = (),
) -> dict[str, Any]:
    from .manifests import _artifact_reference, _claim_boundary, _utc_now_iso

    if status not in EXECUTION_STATUSES:
        raise ValueError(f"unsupported execution manifest status: {status}")
    root = Path(repository_root)
    now = _utc_now_iso()
    started = started_at or now
    completed = completed_at or now
    lifecycle = ["planned", "preflight_validated", "execution_started"]
    if status == "verification_completed":
        lifecycle.extend(["execution_completed", "verification_completed"])
    elif status in {"failed", "side_effect_violation", "blocked"}:
        lifecycle.append(status)
    manifest = {
        "run_id": run_id,
        "pipeline_id": config.get("pipeline_id"),
        "plugin_id": config.get("plugin_id"),
        "adapter_id": plan.adapter_id,
        "stage": config.get("stage"),
        "config_sha256": calculate_config_sha256(config),
        "source_artifacts": [
            _artifact_reference(artifact_id, artifact_registry, root) for artifact_id in plan.required_inputs
        ],
        "output_artifacts": [
            _artifact_reference(artifact_id, artifact_registry, root) for artifact_id in plan.expected_outputs
        ],
        "code_commit": read_git_commit(root),
        "started_at": started,
        "completed_at": completed,
        "duration_seconds": duration_seconds,
        "status": status,
        "lifecycle_events": lifecycle,
        "dry_run": False,
        "test_mode": False,
        "execution_mode": execution_mode,
        "adapter_policy_version": permission.policy_version if permission is not None else None,
        "environment": {"python_implementation": sys.implementation.name, "platform_scaffold": "v2.0.3"},
        "python_version": sys.version.split()[0],
        "dependency_summary": {"external_execution_dependency": "none"},
        "random_state": config.get("random_state"),
        "warnings": list(validation.warnings) + (list(result.warnings) if result else []),
        "errors": list(validation.errors) + list(plan.blocked_reasons) + list(errors) + (list(result.errors) if result else []),
        "claim_boundary": result.claim_boundary if result else _claim_boundary(plan.trust_policy, trust_registry),
        "execution_boundary": {
            "execution_allowed": bool(permission.execution_allowed) if permission else False,
            "execution_mode": execution_mode,
            "network_allowed": bool(permission.network_allowed) if permission else False,
            "raw_data_allowed": bool(permission.raw_data_allowed) if permission else False,
            "model_training_allowed": bool(permission.model_training_allowed) if permission else False,
            "process_spawn_allowed": bool(permission.process_spawn_allowed) if permission else False,
            "canonical_overwrite_allowed": bool(permission.canonical_overwrite_allowed) if permission else False,
        },
        "input_checksums": result.input_checksums if result else {},
        "produced_artifacts": list(result.produced_files) if result else [],
        "output_checksums": result.output_checksums if result else {},
        "side_effect_status": result.side_effect_summary.get("status") if result else None,
        "side_effect_report": side_effect_report,
        "canonical_comparison": result.metrics_summary.get("canonical_comparison") if result else None,
        "exit_status": status,
        "exception_type": None,
        "error_summary": "; ".join(errors),
        "local_only_outputs": [
            _artifact_reference(artifact_id, artifact_registry, root) for artifact_id in plan.expected_local_only_outputs
        ],
        "tracked_outputs": [
            _artifact_reference(artifact_id, artifact_registry, root) for artifact_id in plan.expected_tracked_outputs
        ],
        "output_directory": output_directory,
    }
    validate_run_manifest(manifest)
    return manifest


def execute_adapter_runtime(
    *,
    config: dict[str, Any],
    validation: ConfigValidationResult,
    plan: DryRunPlan,
    plugin_registry: PluginRegistry,
    adapter_registry: AdapterRegistry,
    artifact_registry: ArtifactRegistry,
    trust_registry: TrustPolicyRegistry,
    execution_policy_registry: ExecutionPolicyRegistry,
    callables: dict[str, AdapterCallable],
    repository_root: str | Path,
    execution_mode: str,
    output_directory: str | None = None,
    run_id_override: str | None = None,
    overwrite_manifest: bool = False,
) -> tuple[dict[str, Any], AdapterExecutionResult | None]:
    root = Path(repository_root).resolve()
    if not validation.valid:
        raise PlatformExecutionError("invalid config")
    if not plan.adapter_id:
        raise AdapterExecutionDisabled("adapter is not registered")
    adapter = adapter_registry.get(plan.adapter_id)
    plugin_registry.validate_stage_support(adapter.plugin_id, adapter.stage)
    permission = execution_policy_registry.get(adapter.adapter_id)
    if not permission.permits_mode(execution_mode):
        raise AdapterExecutionDisabled(f"adapter execution disabled for mode {execution_mode}: {adapter.adapter_id}")
    if execution_mode != "verify":
        raise AdapterExecutionDisabled("isolated_run is deferred in v2.0.3")
    for artifact_id in permission.allowed_read_artifact_ids:
        if artifact_registry.get(artifact_id).local_only:
            raise AdapterExecutionDisabled(f"local-only artifact cannot be executable input: {artifact_id}")
    config_hash = calculate_config_sha256(config)
    run_id = run_id_override or build_run_id({**config, "run_id": config.get("run_id")}, config_hash)
    output_dir = resolve_output_directory(
        root,
        output_directory or str(config.get("output_directory") or f"outputs/platform_runs/{run_id}"),
    )
    manifest_path = output_dir / "run_manifest.json"
    if manifest_path.exists() and not overwrite_manifest:
        raise PathPolicyError(f"manifest already exists: {_relative(manifest_path, root)}")
    artifacts_dir = output_dir / "artifacts"
    logs_dir = output_dir / "logs"
    resolver = ArtifactResolver(root, artifact_registry)
    protected = {
        artifact_id: resolver.resolve(artifact_id, allow_local_only=False, allow_raw=False).path
        for artifact_id in permission.allowed_read_artifact_ids
    }
    snapshot = create_side_effect_snapshot(root, protected, output_dir)
    if snapshot.tracked_status and bool(config.get("require_clean_tree", True)):
        raise SideEffectViolationError("tracked working tree has modified or deleted files")
    start = time.monotonic()
    started_iso = None
    result: AdapterExecutionResult | None = None
    side_effect_report_path: str | None = None
    try:
        context = ExecutionContext(
            adapter_id=adapter.adapter_id,
            plugin_id=adapter.plugin_id,
            stage=adapter.stage,
            execution_mode=execution_mode,
            run_id=run_id,
            repository_root=root,
            isolated_output_dir=output_dir,
            artifacts_dir=artifacts_dir,
            logs_dir=logs_dir,
            artifact_resolver=resolver,
            config=config,
            execution_policy=permission,
            dry_run=False,
            verification_only=True,
        )
        callable_fn = callables.get(adapter.adapter_id)
        if callable_fn is None:
            raise AdapterExecutionDisabled(f"adapter callable not approved: {adapter.adapter_id}")
        result = callable_fn(context)
        side_effect_report = evaluate_side_effects(
            root,
            snapshot,
            protected,
            output_dir,
            max_output_files=permission.max_output_files,
            max_output_bytes=permission.max_output_bytes,
        )
        side_effect_report_path = _relative(output_dir / "side_effect_report.json", root)
        write_side_effect_report(side_effect_report, output_dir / "side_effect_report.json")
        result = AdapterExecutionResult(
            status=result.status,
            produced_files=result.produced_files,
            warnings=result.warnings,
            metrics_summary=result.metrics_summary,
            claim_boundary=result.claim_boundary,
            input_checksums=result.input_checksums,
            output_checksums=result.output_checksums,
            side_effect_summary=side_effect_report.to_dict(),
            errors=result.errors,
        )
        if side_effect_report.status not in {"allowed_outputs_only"}:
            status = "side_effect_violation"
        elif result.status != "success":
            status = "failed"
        else:
            status = "verification_completed"
        duration = time.monotonic() - start
        manifest = build_execution_manifest(
            config=config,
            validation=validation,
            plan=plan,
            permission=permission,
            artifact_registry=artifact_registry,
            trust_registry=trust_registry,
            repository_root=root,
            run_id=run_id,
            output_directory=_relative(output_dir, root),
            status=status,
            execution_mode=execution_mode,
            started_at=started_iso,
            duration_seconds=round(duration, 6),
            result=result,
            side_effect_report=side_effect_report_path,
        )
        write_run_manifest(
            manifest,
            repo_root=root,
            manifest_output=_relative(manifest_path, root),
            overwrite=overwrite_manifest,
        )
        if status == "side_effect_violation":
            raise SideEffectViolationError("side-effect guard detected prohibited changes")
        if status == "failed":
            raise VerificationMismatchError("adapter verification failed")
        return manifest, result
    except Exception as exc:
        duration = time.monotonic() - start
        terminal_status = "side_effect_violation" if isinstance(exc, SideEffectViolationError) else "failed"
        error_result = result or AdapterExecutionResult(
            status="failed",
            produced_files=(),
            warnings=(),
            metrics_summary={},
            claim_boundary={},
            input_checksums={},
            output_checksums={},
            side_effect_summary={},
            errors=(str(exc),),
        )
        manifest = build_execution_manifest(
            config=config,
            validation=validation,
            plan=plan,
            permission=permission,
            artifact_registry=artifact_registry,
            trust_registry=trust_registry,
            repository_root=root,
            run_id=run_id,
            output_directory=_relative(output_dir, root),
            status=terminal_status,
            execution_mode=execution_mode,
            started_at=started_iso,
            duration_seconds=round(duration, 6),
            result=error_result,
            side_effect_report=side_effect_report_path,
            errors=(str(exc),),
        )
        write_run_manifest(
            manifest,
            repo_root=root,
            manifest_output=_relative(manifest_path, root),
            overwrite=True,
        )
        raise
