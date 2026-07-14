"""Dry-run manifest construction and safe local writing."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifacts import ArtifactRegistry, validate_relative_path
from .config import ConfigValidationResult
from .planner import DryRunPlan
from .trust_registry import TrustPolicyRegistry


ALLOWED_MANIFEST_STATUSES = (
    "planned",
    "preflight_validated",
    "execution_started",
    "execution_completed",
    "verification_completed",
    "blocked",
    "dry_run_completed",
    "invalid_config",
    "adapter_disabled",
    "failed",
    "side_effect_violation",
)


def calculate_config_sha256(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sanitize_run_id(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value.lower())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "platform-dry-run"


def build_run_id(config: dict[str, Any], config_sha256: str) -> str:
    explicit = config.get("run_id")
    if isinstance(explicit, str) and explicit:
        return _sanitize_run_id(explicit)
    base = f"{config.get('pipeline_id', 'pipeline')}-{config.get('plugin_id', 'plugin')}-{config.get('stage', 'stage')}"
    return _sanitize_run_id(f"{base}-{config_sha256[:8]}")


def default_manifest_output(run_id: str) -> str:
    return f"outputs/platform_runs/{run_id}/run_manifest.json"


def read_git_commit(repo_root: str | Path = ".") -> str | None:
    git_dir = Path(repo_root) / ".git"
    head_path = git_dir / "HEAD"
    try:
        head = head_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if head.startswith("ref: "):
        ref_name = head.removeprefix("ref: ").strip()
        ref_path = git_dir / ref_name
        try:
            value = ref_path.read_text(encoding="utf-8").strip()
        except OSError:
            packed_refs = git_dir / "packed-refs"
            try:
                for line in packed_refs.read_text(encoding="utf-8").splitlines():
                    if line.startswith("#") or not line.strip():
                        continue
                    commit, _, ref = line.partition(" ")
                    if ref == ref_name:
                        return commit
            except OSError:
                return None
            return None
        return value
    return head or None


def _artifact_reference(
    artifact_id: str,
    artifact_registry: ArtifactRegistry,
    repo_root: str | Path,
) -> dict[str, object]:
    artifact = artifact_registry.get(artifact_id)
    return {
        "artifact_id": artifact.artifact_id,
        "relative_path": artifact.relative_path,
        "tracked_policy": artifact.tracked_policy,
        "local_only": artifact.local_only,
        "exists": (Path(repo_root) / artifact.relative_path).exists(),
    }


def _manifest_status(validation: ConfigValidationResult, plan: DryRunPlan) -> str:
    if not validation.valid:
        return "invalid_config"
    if plan.execution_status == "ready_for_dry_run_manifest":
        return "dry_run_completed"
    if "blocked_adapter_disabled" in plan.blocked_reasons:
        return "adapter_disabled"
    return "blocked"


def _claim_boundary(
    trust_policy_id: str | None,
    trust_registry: TrustPolicyRegistry,
) -> dict[str, object]:
    if not trust_policy_id:
        return {
            "trust_policy_id": None,
            "production_claim_allowed": False,
            "calibration_boundary": "not_declared",
            "explainability_boundary": "not_declared",
            "allowed_claims": [],
            "prohibited_claims": [],
        }
    policy = trust_registry.get(trust_policy_id)
    return {
        "trust_policy_id": policy.policy_id,
        "production_claim_allowed": policy.production_claim_allowed,
        "calibration_boundary": policy.calibration_boundary,
        "explainability_boundary": policy.explainability_boundary,
        "allowed_claims": list(policy.allowed_claims),
        "prohibited_claims": list(policy.prohibited_claims),
    }


def build_run_manifest(
    config: dict[str, Any],
    validation: ConfigValidationResult,
    plan: DryRunPlan,
    artifact_registry: ArtifactRegistry,
    trust_registry: TrustPolicyRegistry,
    repo_root: str | Path = ".",
    timestamp: str | None = None,
    code_commit: str | None = None,
) -> dict[str, Any]:
    config_hash = calculate_config_sha256(config)
    run_id = build_run_id(config, config_hash)
    now = timestamp or _utc_now_iso()
    source_artifacts = [
        _artifact_reference(artifact_id, artifact_registry, repo_root) for artifact_id in plan.required_inputs
    ]
    tracked_outputs = [
        _artifact_reference(artifact_id, artifact_registry, repo_root) for artifact_id in plan.expected_tracked_outputs
    ]
    local_outputs = [
        _artifact_reference(artifact_id, artifact_registry, repo_root) for artifact_id in plan.expected_local_only_outputs
    ]
    manifest = {
        "run_id": run_id,
        "pipeline_id": config.get("pipeline_id"),
        "plugin_id": config.get("plugin_id"),
        "adapter_id": plan.adapter_id,
        "stage": config.get("stage"),
        "config_sha256": config_hash,
        "source_artifacts": source_artifacts,
        "output_artifacts": tracked_outputs + local_outputs,
        "code_commit": code_commit or read_git_commit(repo_root),
        "started_at": now,
        "completed_at": now,
        "status": _manifest_status(validation, plan),
        "dry_run": bool(config.get("dry_run", False)),
        "test_mode": bool(config.get("parameters", {}).get("test_mode", False))
        if isinstance(config.get("parameters", {}), dict)
        else False,
        "environment": {
            "python_implementation": sys.implementation.name,
            "platform_scaffold": "v2.0.2",
        },
        "python_version": sys.version.split()[0],
        "dependency_summary": {"external_schema_dependency": "none"},
        "random_state": config.get("random_state"),
        "warnings": list(validation.warnings) + list(plan.warnings),
        "errors": list(validation.errors) + list(plan.blocked_reasons),
        "claim_boundary": _claim_boundary(plan.trust_policy, trust_registry),
        "execution_boundary": {
            "execution_allowed": plan.execution_allowed,
            "adapter_status": plan.adapter_status,
            "execution_boundary": plan.execution_boundary,
            "network_required": plan.network_requirement == "required",
            "raw_data_required": plan.raw_data_requirement == "required",
            "model_training_required": plan.model_training_requirement == "required",
            "writes_outputs": plan.writes_outputs,
        },
        "local_only_outputs": local_outputs,
        "tracked_outputs": tracked_outputs,
    }
    validate_run_manifest(manifest)
    return manifest


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def validate_run_manifest(manifest: dict[str, Any]) -> None:
    required = {
        "run_id",
        "pipeline_id",
        "plugin_id",
        "adapter_id",
        "stage",
        "config_sha256",
        "code_commit",
        "status",
        "dry_run",
        "warnings",
        "errors",
        "claim_boundary",
    }
    missing = sorted(field for field in required if field not in manifest)
    if missing:
        raise ValueError(f"missing manifest fields: {', '.join(missing)}")
    if manifest["status"] not in ALLOWED_MANIFEST_STATUSES:
        raise ValueError(f"unsupported manifest status: {manifest['status']}")
    if not isinstance(manifest["dry_run"], bool):
        raise ValueError("manifest dry_run must be a boolean")
    if not isinstance(manifest["warnings"], list) or not isinstance(manifest["errors"], list):
        raise ValueError("manifest warnings and errors must be lists")
    for text in _iter_strings(manifest):
        lowered = text.lower()
        if any(marker in lowered for marker in ("password", "secret", "token", "api_key", "kaggle_key")):
            raise ValueError("manifest contains credential-like text")
        if ":/" in text or ":\\" in text or lowered.startswith("/users/") or "\\users\\" in lowered:
            raise ValueError("manifest contains an absolute local path")


def resolve_manifest_output(
    repo_root: str | Path,
    manifest_output: str,
) -> Path:
    validate_relative_path(manifest_output)
    root = Path(repo_root).resolve()
    target = (root / manifest_output).resolve()
    if root != target and root not in target.parents:
        raise ValueError("manifest output must stay inside repository root")
    return target


def write_run_manifest(
    manifest: dict[str, Any],
    repo_root: str | Path,
    manifest_output: str,
    overwrite: bool = False,
) -> Path:
    validate_run_manifest(manifest)
    target = resolve_manifest_output(repo_root, manifest_output)
    if target.exists() and not overwrite:
        raise FileExistsError(f"manifest already exists: {manifest_output}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.tmp")
    if temp.exists():
        temp.unlink()
    try:
        temp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(target)
    finally:
        if temp.exists():
            temp.unlink()
    return target


def load_run_manifest(manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path)
    with path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict):
        raise ValueError("run manifest must be a JSON object")
    validate_run_manifest(manifest)
    return manifest
