"""Persistent local run and artifact registry for platform manifests.

The registry stores metadata only. It never reads raw datasets, executes
adapters, recomputes scientific results, or stores absolute local paths.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .artifact_resolver import calculate_sha256
from .artifacts import ArtifactRegistry, build_default_artifact_registry, validate_relative_path
from .manifests import validate_run_manifest
from .report_generator import validate_report_manifest


REGISTRY_SCHEMA_VERSION = 1
DEFAULT_REGISTRY_PATH = "outputs/platform_registry/platform_registry.sqlite3"
DEFAULT_EXPORT_DIR = "outputs/platform_registry/exports"

REPRODUCIBILITY_STATUSES = (
    "reproducible_verified",
    "reproducible_partial",
    "unverifiable_missing_input",
    "unverifiable_checksum_mismatch",
    "unverifiable_code_commit",
    "unverifiable_config",
    "blocked_policy_violation",
)

COMPARISON_STATUSES = (
    "identical_metadata",
    "reproducible_equivalent",
    "configuration_changed",
    "inputs_changed",
    "code_changed",
    "outputs_changed",
    "incomparable",
)


class RunRegistryError(RuntimeError):
    """Base error for persistent registry operations."""


class RegistryPathError(RunRegistryError):
    """Raised when a registry path violates local-only path policy."""


class RegistryConflictError(RunRegistryError):
    """Raised when a run_id already maps to different manifest content."""


class UnsupportedRegistryVersion(RunRegistryError):
    """Raised when a database uses a newer unsupported schema."""


class RegistryValidationError(RunRegistryError):
    """Raised when registry integrity checks fail."""


@dataclass(frozen=True)
class IngestionResult:
    run_id: str
    status: str
    manifest_kind: str
    artifact_records: int
    lineage_records: int
    warning_records: int
    manifest_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "manifest_kind": self.manifest_kind,
            "artifact_records": self.artifact_records,
            "lineage_records": self.lineage_records,
            "warning_records": self.warning_records,
            "manifest_sha256": self.manifest_sha256,
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json_sha256(payload: dict[str, Any]) -> str:
    content = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _safe_identifier(value: str, fallback: str = "record") -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.lower())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or fallback


def _record_id(*parts: object) -> str:
    payload = "|".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


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


def assert_no_sensitive_strings(payload: Any) -> None:
    for text in _iter_strings(payload):
        lowered = text.lower()
        if any(marker in lowered for marker in ("password", "secret", "token", "api_key", "kaggle_key")):
            raise RegistryValidationError("registry payload contains credential-like text")
        if ":/" in text or ":\\" in text or lowered.startswith("/users/") or "\\users\\" in lowered:
            raise RegistryValidationError("registry payload contains an absolute local path")


def resolve_registry_path(repo_root: str | Path = ".", registry_path: str = DEFAULT_REGISTRY_PATH) -> Path:
    try:
        validate_relative_path(registry_path)
    except ValueError as exc:
        raise RegistryPathError(str(exc)) from exc
    normalized = registry_path.replace("\\", "/")
    if not normalized.startswith("outputs/platform_registry/"):
        raise RegistryPathError("registry path must be under outputs/platform_registry")
    root = Path(repo_root).resolve()
    target = (root / registry_path).resolve()
    if root != target and root not in target.parents:
        raise RegistryPathError("registry path must stay inside repository root")
    existing_parent = target.parent
    while not existing_parent.exists() and existing_parent != root:
        existing_parent = existing_parent.parent
    if existing_parent.exists():
        resolved_parent = existing_parent.resolve()
        if root != resolved_parent and root not in resolved_parent.parents:
            raise RegistryPathError("registry path parent resolves outside repository root")
    return target


def resolve_manifest_path(repo_root: str | Path, manifest_path: str | Path) -> tuple[Path, str]:
    root = Path(repo_root).resolve()
    candidate = Path(manifest_path)
    target = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if root != target and root not in target.parents:
        raise RegistryPathError("manifest path must stay inside repository root")
    relative = target.relative_to(root).as_posix()
    validate_relative_path(relative)
    return target, relative


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_registry(
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> Path:
    path = resolve_registry_path(repo_root, registry_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as connection:
        _initialize_schema(connection)
    return path


def _initialize_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS registry_metadata (
            metadata_id INTEGER PRIMARY KEY CHECK (metadata_id = 1),
            schema_version INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            manifest_kind TEXT NOT NULL,
            manifest_sha256 TEXT NOT NULL,
            pipeline_id TEXT,
            plugin_id TEXT NOT NULL,
            adapter_id TEXT,
            case_study_id TEXT,
            stage TEXT NOT NULL,
            config_sha256 TEXT,
            code_commit TEXT,
            status TEXT NOT NULL,
            execution_mode TEXT,
            dry_run INTEGER NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            duration_seconds REAL,
            manifest_relative_path TEXT NOT NULL,
            verification_status TEXT,
            side_effect_status TEXT,
            claim_boundary_ref TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS artifacts (
            artifact_record_id TEXT PRIMARY KEY,
            artifact_id TEXT NOT NULL,
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('input', 'output')),
            relative_path TEXT NOT NULL,
            artifact_type TEXT,
            format TEXT,
            checksum_sha256 TEXT,
            size_bytes INTEGER,
            tracked_policy TEXT,
            local_only INTEGER NOT NULL,
            producer TEXT,
            provenance_status TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS lineage (
            parent_artifact_record_id TEXT NOT NULL REFERENCES artifacts(artifact_record_id) ON DELETE CASCADE,
            child_artifact_record_id TEXT NOT NULL REFERENCES artifacts(artifact_record_id) ON DELETE CASCADE,
            relationship TEXT NOT NULL,
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            PRIMARY KEY (parent_artifact_record_id, child_artifact_record_id, relationship)
        );

        CREATE TABLE IF NOT EXISTS warnings (
            warning_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            warning_code TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_artifacts_run_role ON artifacts(run_id, role, artifact_id);
        CREATE INDEX IF NOT EXISTS idx_runs_plugin_stage ON runs(plugin_id, stage, run_id);
        """
    )
    row = connection.execute("SELECT schema_version FROM registry_metadata WHERE metadata_id = 1").fetchone()
    now = utc_now_iso()
    if row is None:
        connection.execute(
            "INSERT INTO registry_metadata(metadata_id, schema_version, created_at, updated_at) VALUES (1, ?, ?, ?)",
            (REGISTRY_SCHEMA_VERSION, now, now),
        )
    elif int(row["schema_version"]) > REGISTRY_SCHEMA_VERSION:
        raise UnsupportedRegistryVersion(
            f"unsupported registry schema version: {row['schema_version']}"
        )
    elif int(row["schema_version"]) < REGISTRY_SCHEMA_VERSION:
        _migrate_schema(connection, int(row["schema_version"]), REGISTRY_SCHEMA_VERSION)
    connection.execute(
        "UPDATE registry_metadata SET updated_at = ? WHERE metadata_id = 1",
        (now,),
    )


def _migrate_schema(connection: sqlite3.Connection, current_version: int, target_version: int) -> None:
    if current_version == 0 and target_version == 1:
        connection.execute(
            "UPDATE registry_metadata SET schema_version = ?, updated_at = ? WHERE metadata_id = 1",
            (REGISTRY_SCHEMA_VERSION, utc_now_iso()),
        )
        return
    raise UnsupportedRegistryVersion(f"no migration path from {current_version} to {target_version}")


def get_schema_version(
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> int:
    path = initialize_registry(repo_root, registry_path)
    with _connect(path) as connection:
        row = connection.execute("SELECT schema_version FROM registry_metadata WHERE metadata_id = 1").fetchone()
        return int(row["schema_version"])


def _infer_manifest_kind(manifest: dict[str, Any]) -> str:
    if "run_id" in manifest:
        validate_run_manifest(manifest)
        return "run"
    if "report_id" in manifest and "report_schema_version" in manifest:
        validate_report_manifest(manifest)
        return "report"
    raise ValueError("unsupported manifest type")


def _claim_boundary_ref(claim_boundary: Any) -> str | None:
    if not claim_boundary:
        return None
    return canonical_json_sha256({"claim_boundary": claim_boundary})


def _artifact_registry_by_path(artifact_registry: ArtifactRegistry) -> dict[str, Any]:
    return {
        artifact.relative_path.replace("\\", "/"): artifact
        for artifact in artifact_registry.list_artifacts()
    }


def _artifact_metadata(artifact_id: str, artifact_registry: ArtifactRegistry) -> Any | None:
    try:
        return artifact_registry.get(artifact_id)
    except KeyError:
        return None


def _safe_artifact_record(
    *,
    run_id: str,
    role: str,
    artifact_id: str,
    relative_path: str,
    artifact_type: str | None,
    format_name: str | None,
    checksum_sha256: str | None,
    tracked_policy: str | None,
    local_only: bool,
    producer: str | None,
    repo_root: Path,
    created_at: str,
) -> dict[str, Any]:
    validate_relative_path(relative_path)
    normalized = relative_path.replace("\\", "/")
    if normalized.startswith("data/raw/") and tracked_policy in {"tracked", "generated_compact"}:
        raise RegistryValidationError(f"raw artifact cannot be tracked: {artifact_id}")
    if local_only and tracked_policy in {"tracked", "generated_compact"}:
        raise RegistryValidationError(f"tracked/local_only conflict: {artifact_id}")
    target = (repo_root / normalized).resolve()
    if repo_root != target and repo_root not in target.parents:
        raise RegistryPathError("artifact path escapes repository root")
    size_bytes = target.stat().st_size if target.exists() else None
    return {
        "artifact_record_id": _record_id(run_id, role, artifact_id, normalized),
        "artifact_id": artifact_id,
        "run_id": run_id,
        "role": role,
        "relative_path": normalized,
        "artifact_type": artifact_type,
        "format": format_name,
        "checksum_sha256": checksum_sha256,
        "size_bytes": size_bytes,
        "tracked_policy": tracked_policy,
        "local_only": int(local_only),
        "producer": producer,
        "provenance_status": "checksum_recorded" if checksum_sha256 else "checksum_missing",
        "created_at": created_at,
    }


def _records_from_run_manifest(
    manifest: dict[str, Any],
    artifact_registry: ArtifactRegistry,
    repo_root: Path,
    created_at: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    input_checksums = manifest.get("input_checksums", {}) if isinstance(manifest.get("input_checksums"), dict) else {}
    output_checksums = manifest.get("output_checksums", {}) if isinstance(manifest.get("output_checksums"), dict) else {}
    for role, field in (("input", "source_artifacts"), ("output", "output_artifacts")):
        for index, item in enumerate(manifest.get(field, [])):
            if not isinstance(item, dict):
                continue
            artifact_id = str(item.get("artifact_id") or f"{role}_{index}")
            relative_path = str(item.get("relative_path") or f"outputs/platform_registry/unknown/{artifact_id}")
            metadata = _artifact_metadata(artifact_id, artifact_registry)
            if metadata is not None:
                relative_path = metadata.relative_path
                tracked_policy = metadata.tracked_policy
                local_only = metadata.local_only
                artifact_type = metadata.artifact_type
                format_name = metadata.format
                producer = metadata.producer
            else:
                tracked_policy = str(item.get("tracked_policy") or "optional")
                local_only = bool(item.get("local_only", tracked_policy == "local_only"))
                artifact_type = None
                format_name = None
                producer = None
            checksum = (
                input_checksums.get(artifact_id)
                or input_checksums.get(relative_path)
                or output_checksums.get(artifact_id)
                or output_checksums.get(relative_path)
            )
            key = (role, artifact_id, relative_path)
            if key in seen:
                continue
            seen.add(key)
            records.append(
                _safe_artifact_record(
                    run_id=str(manifest["run_id"]),
                    role=role,
                    artifact_id=artifact_id,
                    relative_path=relative_path,
                    artifact_type=artifact_type,
                    format_name=format_name,
                    checksum_sha256=checksum,
                    tracked_policy=tracked_policy,
                    local_only=local_only,
                    producer=producer,
                    repo_root=repo_root,
                    created_at=created_at,
                )
            )
    known_output_paths = {record["relative_path"] for record in records if record["role"] == "output"}
    for relative_path in manifest.get("produced_artifacts", []):
        if not isinstance(relative_path, str) or relative_path in known_output_paths:
            continue
        artifact_id = f"produced_{_safe_identifier(Path(relative_path).stem)}"
        checksum = output_checksums.get(relative_path)
        records.append(
            _safe_artifact_record(
                run_id=str(manifest["run_id"]),
                role="output",
                artifact_id=artifact_id,
                relative_path=relative_path,
                artifact_type="produced_file",
                format_name=Path(relative_path).suffix.lstrip(".") or None,
                checksum_sha256=checksum,
                tracked_policy="local_only",
                local_only=True,
                producer=str(manifest.get("adapter_id") or "platform"),
                repo_root=repo_root,
                created_at=created_at,
            )
        )
    return records


def _records_from_report_manifest(
    manifest: dict[str, Any],
    artifact_registry: ArtifactRegistry,
    repo_root: Path,
    run_id: str,
    created_at: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    by_path = _artifact_registry_by_path(artifact_registry)
    source_checksums = manifest.get("source_artifact_checksums", {})
    output_checksums = manifest.get("output_checksums", {})
    for relative_path in manifest.get("source_artifacts", []):
        if not isinstance(relative_path, str):
            continue
        metadata = by_path.get(relative_path.replace("\\", "/"))
        artifact_id = metadata.artifact_id if metadata else f"source_{_safe_identifier(Path(relative_path).stem)}"
        records.append(
            _safe_artifact_record(
                run_id=run_id,
                role="input",
                artifact_id=artifact_id,
                relative_path=relative_path,
                artifact_type=metadata.artifact_type if metadata else "source_artifact",
                format_name=metadata.format if metadata else Path(relative_path).suffix.lstrip(".") or None,
                checksum_sha256=source_checksums.get(relative_path),
                tracked_policy=metadata.tracked_policy if metadata else "generated_compact",
                local_only=metadata.local_only if metadata else False,
                producer=metadata.producer if metadata else "platform_report",
                repo_root=repo_root,
                created_at=created_at,
            )
        )
    for relative_path in manifest.get("output_files", []):
        if not isinstance(relative_path, str):
            continue
        artifact_id = f"report_{_safe_identifier(Path(relative_path).stem)}"
        records.append(
            _safe_artifact_record(
                run_id=run_id,
                role="output",
                artifact_id=artifact_id,
                relative_path=relative_path,
                artifact_type="platform_report",
                format_name=Path(relative_path).suffix.lstrip(".") or None,
                checksum_sha256=output_checksums.get(relative_path),
                tracked_policy="local_only",
                local_only=True,
                producer="platform_report_generator",
                repo_root=repo_root,
                created_at=created_at,
            )
        )
    return records


def _run_row_from_manifest(
    manifest: dict[str, Any],
    manifest_kind: str,
    manifest_sha256: str,
    manifest_relative_path: str,
    created_at: str,
) -> dict[str, Any]:
    if manifest_kind == "run":
        return {
            "run_id": str(manifest["run_id"]),
            "manifest_kind": manifest_kind,
            "manifest_sha256": manifest_sha256,
            "pipeline_id": manifest.get("pipeline_id"),
            "plugin_id": str(manifest.get("plugin_id")),
            "adapter_id": manifest.get("adapter_id"),
            "case_study_id": manifest.get("case_study_id") or manifest.get("plugin_id"),
            "stage": str(manifest.get("stage")),
            "config_sha256": manifest.get("config_sha256"),
            "code_commit": manifest.get("code_commit"),
            "status": str(manifest.get("status")),
            "execution_mode": manifest.get("execution_mode"),
            "dry_run": int(bool(manifest.get("dry_run"))),
            "started_at": manifest.get("started_at"),
            "completed_at": manifest.get("completed_at"),
            "duration_seconds": manifest.get("duration_seconds"),
            "manifest_relative_path": manifest_relative_path,
            "verification_status": "verified" if manifest.get("status") == "verification_completed" else None,
            "side_effect_status": manifest.get("side_effect_status"),
            "claim_boundary_ref": _claim_boundary_ref(manifest.get("claim_boundary")),
            "created_at": created_at,
        }
    run_id = f"report-{_safe_identifier(str(manifest['report_id']))}"
    return {
        "run_id": run_id,
        "manifest_kind": manifest_kind,
        "manifest_sha256": manifest_sha256,
        "pipeline_id": manifest.get("report_id"),
        "plugin_id": "platform",
        "adapter_id": "platform_report_generator",
        "case_study_id": ",".join(str(item) for item in manifest.get("case_study_ids", [])),
        "stage": "report",
        "config_sha256": manifest_sha256,
        "code_commit": manifest.get("code_commit"),
        "status": str(manifest.get("generation_status")),
        "execution_mode": "report_generation",
        "dry_run": 0,
        "started_at": None,
        "completed_at": None,
        "duration_seconds": None,
        "manifest_relative_path": manifest_relative_path,
        "verification_status": "report_manifest_valid",
        "side_effect_status": "local_only_report_generated",
        "claim_boundary_ref": _claim_boundary_ref(
            {"scientific_recomputation_performed": manifest.get("scientific_recomputation_performed")}
        ),
        "created_at": created_at,
    }


def _warning_rows(manifest: dict[str, Any], run_id: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for severity, field in (("warning", "warnings"), ("error", "errors")):
        for index, item in enumerate(manifest.get(field, [])):
            if isinstance(item, dict):
                message = json.dumps(item, sort_keys=True)
                warning_code = str(item.get("code") or f"{field}_{index}")
                severity_value = str(item.get("severity") or severity)
            else:
                message = str(item)
                warning_code = f"{field}_{index}"
                severity_value = severity
            rows.append(
                {
                    "warning_id": _record_id(run_id, field, index, message),
                    "run_id": run_id,
                    "warning_code": warning_code,
                    "severity": severity_value,
                    "message": message,
                }
            )
    return rows


def ingest_manifest(
    manifest_path: str | Path,
    *,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
    artifact_registry: ArtifactRegistry | None = None,
) -> IngestionResult:
    repo = Path(repo_root).resolve()
    registry_file = initialize_registry(repo, registry_path)
    manifest_file, manifest_relative_path = resolve_manifest_path(repo, manifest_path)
    with manifest_file.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    assert_no_sensitive_strings(manifest)
    manifest_kind = _infer_manifest_kind(manifest)
    manifest_sha = canonical_json_sha256(manifest)
    artifact_registry = artifact_registry or build_default_artifact_registry()
    created_at = utc_now_iso()
    run_row = _run_row_from_manifest(manifest, manifest_kind, manifest_sha, manifest_relative_path, created_at)
    run_id = str(run_row["run_id"])
    records = (
        _records_from_run_manifest(manifest, artifact_registry, repo, created_at)
        if manifest_kind == "run"
        else _records_from_report_manifest(manifest, artifact_registry, repo, run_id, created_at)
    )
    warnings = _warning_rows(manifest, run_id)
    assert_no_sensitive_strings(run_row)
    assert_no_sensitive_strings(records)
    assert_no_sensitive_strings(warnings)
    with _connect(registry_file) as connection:
        _initialize_schema(connection)
        existing = connection.execute(
            "SELECT manifest_sha256 FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if existing is not None:
            if existing["manifest_sha256"] == manifest_sha:
                return IngestionResult(run_id, "idempotent", manifest_kind, len(records), 0, len(warnings), manifest_sha)
            raise RegistryConflictError(f"run_id already registered with different manifest content: {run_id}")
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO runs(
                        run_id, manifest_kind, manifest_sha256, pipeline_id, plugin_id, adapter_id,
                        case_study_id, stage, config_sha256, code_commit, status, execution_mode,
                        dry_run, started_at, completed_at, duration_seconds, manifest_relative_path,
                        verification_status, side_effect_status, claim_boundary_ref, created_at
                    )
                    VALUES (
                        :run_id, :manifest_kind, :manifest_sha256, :pipeline_id, :plugin_id, :adapter_id,
                        :case_study_id, :stage, :config_sha256, :code_commit, :status, :execution_mode,
                        :dry_run, :started_at, :completed_at, :duration_seconds, :manifest_relative_path,
                        :verification_status, :side_effect_status, :claim_boundary_ref, :created_at
                    )
                    """,
                    run_row,
                )
                for record in records:
                    connection.execute(
                        """
                        INSERT INTO artifacts(
                            artifact_record_id, artifact_id, run_id, role, relative_path, artifact_type,
                            format, checksum_sha256, size_bytes, tracked_policy, local_only, producer,
                            provenance_status, created_at
                        )
                        VALUES (
                            :artifact_record_id, :artifact_id, :run_id, :role, :relative_path, :artifact_type,
                            :format, :checksum_sha256, :size_bytes, :tracked_policy, :local_only, :producer,
                            :provenance_status, :created_at
                        )
                        """,
                        record,
                    )
                inputs = [record for record in records if record["role"] == "input"]
                outputs = [record for record in records if record["role"] == "output"]
                lineage_count = 0
                for parent in inputs:
                    for child in outputs:
                        connection.execute(
                            """
                            INSERT INTO lineage(parent_artifact_record_id, child_artifact_record_id, relationship, run_id)
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                parent["artifact_record_id"],
                                child["artifact_record_id"],
                                "manifest_declared_input_to_output",
                                run_id,
                            ),
                        )
                        lineage_count += 1
                for warning in warnings:
                    connection.execute(
                        """
                        INSERT INTO warnings(warning_id, run_id, warning_code, severity, message)
                        VALUES (:warning_id, :run_id, :warning_code, :severity, :message)
                        """,
                        warning,
                    )
        except Exception:
            raise
    return IngestionResult(run_id, "ingested", manifest_kind, len(records), lineage_count, len(warnings), manifest_sha)


def _dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def list_runs(
    *,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> list[dict[str, Any]]:
    path = initialize_registry(repo_root, registry_path)
    with _connect(path) as connection:
        return _dicts(
            connection.execute(
                """
                SELECT run_id, manifest_kind, pipeline_id, plugin_id, adapter_id, stage, status,
                       execution_mode, dry_run, code_commit, manifest_relative_path, created_at
                FROM runs
                ORDER BY created_at, run_id
                """
            )
        )


def get_run(
    run_id: str,
    *,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any]:
    path = initialize_registry(repo_root, registry_path)
    with _connect(path) as connection:
        run = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if run is None:
            raise KeyError(f"unknown run_id: {run_id}")
        artifacts = _dicts(
            connection.execute(
                "SELECT * FROM artifacts WHERE run_id = ? ORDER BY role, artifact_id, relative_path",
                (run_id,),
            )
        )
        warnings = _dicts(
            connection.execute(
                "SELECT warning_code, severity, message FROM warnings WHERE run_id = ? ORDER BY severity, warning_code",
                (run_id,),
            )
        )
    return {"run": dict(run), "artifacts": artifacts, "warnings": warnings}


def list_artifact_records(
    *,
    run_id: str | None = None,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> list[dict[str, Any]]:
    path = initialize_registry(repo_root, registry_path)
    query = "SELECT * FROM artifacts"
    params: tuple[Any, ...] = ()
    if run_id:
        query += " WHERE run_id = ?"
        params = (run_id,)
    query += " ORDER BY run_id, role, artifact_id, relative_path"
    with _connect(path) as connection:
        return _dicts(connection.execute(query, params))


def get_lineage(
    artifact_record_id: str,
    *,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any]:
    path = initialize_registry(repo_root, registry_path)
    with _connect(path) as connection:
        artifact = connection.execute(
            "SELECT * FROM artifacts WHERE artifact_record_id = ?",
            (artifact_record_id,),
        ).fetchone()
        if artifact is None:
            raise KeyError(f"unknown artifact_record_id: {artifact_record_id}")
        parents = _dicts(
            connection.execute(
                """
                SELECT a.*, l.relationship FROM lineage l
                JOIN artifacts a ON a.artifact_record_id = l.parent_artifact_record_id
                WHERE l.child_artifact_record_id = ?
                ORDER BY a.artifact_id, a.relative_path
                """,
                (artifact_record_id,),
            )
        )
        children = _dicts(
            connection.execute(
                """
                SELECT a.*, l.relationship FROM lineage l
                JOIN artifacts a ON a.artifact_record_id = l.child_artifact_record_id
                WHERE l.parent_artifact_record_id = ?
                ORDER BY a.artifact_id, a.relative_path
                """,
                (artifact_record_id,),
            )
        )
    return {"artifact": dict(artifact), "parents": parents, "children": children}


def reproducibility_status(
    run_id: str,
    *,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
    check_files: bool = True,
) -> dict[str, Any]:
    payload = get_run(run_id, repo_root=repo_root, registry_path=registry_path)
    run = payload["run"]
    artifacts = payload["artifacts"]
    reasons: list[str] = []
    if not run.get("config_sha256"):
        return {"run_id": run_id, "status": "unverifiable_config", "reasons": ["missing config_sha256"]}
    if not run.get("code_commit"):
        return {"run_id": run_id, "status": "unverifiable_code_commit", "reasons": ["missing code_commit"]}
    if run.get("side_effect_status") not in {None, "", "allowed_outputs_only", "local_only_report_generated"}:
        return {
            "run_id": run_id,
            "status": "blocked_policy_violation",
            "reasons": [f"side_effect_status={run.get('side_effect_status')}"],
        }
    if not run.get("claim_boundary_ref"):
        reasons.append("missing claim_boundary_ref")
    input_records = [artifact for artifact in artifacts if artifact["role"] == "input"]
    output_records = [artifact for artifact in artifacts if artifact["role"] == "output"]
    if input_records and any(not artifact.get("checksum_sha256") for artifact in input_records):
        return {
            "run_id": run_id,
            "status": "unverifiable_missing_input",
            "reasons": ["one or more input checksums are missing"],
        }
    if output_records and any(not artifact.get("checksum_sha256") for artifact in output_records):
        reasons.append("one or more output checksums are missing")
    if check_files:
        root = Path(repo_root).resolve()
        mismatches: list[str] = []
        for artifact in artifacts:
            checksum = artifact.get("checksum_sha256")
            if not checksum or artifact.get("local_only"):
                continue
            path = (root / str(artifact["relative_path"])).resolve()
            if root != path and root not in path.parents:
                return {
                    "run_id": run_id,
                    "status": "blocked_policy_violation",
                    "reasons": ["artifact path escapes repository root"],
                }
            if path.exists() and calculate_sha256(path) != checksum:
                mismatches.append(str(artifact["artifact_id"]))
        if mismatches:
            return {
                "run_id": run_id,
                "status": "unverifiable_checksum_mismatch",
                "reasons": [f"checksum mismatch: {', '.join(sorted(mismatches))}"],
            }
    status = "reproducible_partial" if reasons else "reproducible_verified"
    return {
        "run_id": run_id,
        "status": status,
        "reasons": reasons,
        "input_artifact_count": len(input_records),
        "output_artifact_count": len(output_records),
    }


def _checksum_signature(artifacts: list[dict[str, Any]], role: str) -> tuple[tuple[str, str | None], ...]:
    return tuple(
        sorted(
            (str(artifact["artifact_id"]), artifact.get("checksum_sha256"))
            for artifact in artifacts
            if artifact["role"] == role
        )
    )


def compare_runs(
    run_a: str,
    run_b: str,
    *,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any]:
    left = get_run(run_a, repo_root=repo_root, registry_path=registry_path)
    right = get_run(run_b, repo_root=repo_root, registry_path=registry_path)
    a = left["run"]
    b = right["run"]
    if (a["plugin_id"], a["adapter_id"], a["stage"]) != (b["plugin_id"], b["adapter_id"], b["stage"]):
        status = "incomparable"
        reasons = ["plugin/adapter/stage differ"]
    elif a["manifest_sha256"] == b["manifest_sha256"]:
        status = "identical_metadata"
        reasons = []
    elif a["config_sha256"] != b["config_sha256"]:
        status = "configuration_changed"
        reasons = ["config_sha256 differs"]
    elif _checksum_signature(left["artifacts"], "input") != _checksum_signature(right["artifacts"], "input"):
        status = "inputs_changed"
        reasons = ["input artifact checksums differ"]
    elif a["code_commit"] != b["code_commit"]:
        status = "code_changed"
        reasons = ["code_commit differs"]
    elif _checksum_signature(left["artifacts"], "output") != _checksum_signature(right["artifacts"], "output"):
        status = "outputs_changed"
        reasons = ["output artifact checksums differ"]
    elif a["status"] != b["status"]:
        status = "reproducible_equivalent"
        reasons = ["run status differs but core reproducibility metadata matches"]
    else:
        status = "reproducible_equivalent"
        reasons = []
    return {
        "run_a": run_a,
        "run_b": run_b,
        "status": status,
        "reasons": reasons,
        "same_plugin_adapter_stage": status != "incomparable",
    }


def validate_registry(
    *,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any]:
    path = initialize_registry(repo_root, registry_path)
    errors: list[str] = []
    with _connect(path) as connection:
        fk_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
        errors.extend(f"foreign_key:{dict(row)}" for row in fk_rows)
        version = connection.execute("SELECT schema_version FROM registry_metadata WHERE metadata_id = 1").fetchone()
        if version is None:
            errors.append("missing registry_metadata")
        elif int(version["schema_version"]) > REGISTRY_SCHEMA_VERSION:
            errors.append("unsupported schema version")
        for row in connection.execute("SELECT manifest_relative_path FROM runs ORDER BY run_id"):
            try:
                validate_relative_path(row["manifest_relative_path"])
            except ValueError as exc:
                errors.append(str(exc))
        for row in connection.execute("SELECT artifact_id, relative_path, tracked_policy, local_only FROM artifacts ORDER BY artifact_id"):
            try:
                validate_relative_path(row["relative_path"])
            except ValueError as exc:
                errors.append(str(exc))
            if int(row["local_only"]) and row["tracked_policy"] in {"tracked", "generated_compact"}:
                errors.append(f"tracked/local_only conflict: {row['artifact_id']}")
            if row["relative_path"].replace("\\", "/").startswith("data/raw/") and row["tracked_policy"] in {
                "tracked",
                "generated_compact",
            }:
                errors.append(f"raw tracked artifact: {row['artifact_id']}")
        orphan_lineage = connection.execute(
            """
            SELECT COUNT(*) AS count FROM lineage l
            LEFT JOIN artifacts p ON p.artifact_record_id = l.parent_artifact_record_id
            LEFT JOIN artifacts c ON c.artifact_record_id = l.child_artifact_record_id
            WHERE p.artifact_record_id IS NULL OR c.artifact_record_id IS NULL
            """
        ).fetchone()["count"]
        if orphan_lineage:
            errors.append(f"orphan lineage rows: {orphan_lineage}")
    return {"valid": not errors, "errors": errors, "schema_version": REGISTRY_SCHEMA_VERSION}


def export_registry_snapshot(
    *,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
    export_dir: str = DEFAULT_EXPORT_DIR,
    overwrite: bool = False,
) -> dict[str, Any]:
    validate_relative_path(export_dir)
    if not export_dir.replace("\\", "/").startswith("outputs/platform_registry/exports"):
        raise RegistryPathError("registry export must be under outputs/platform_registry/exports")
    root = Path(repo_root).resolve()
    output_dir = (root / export_dir).resolve()
    if root != output_dir and root not in output_dir.parents:
        raise RegistryPathError("export directory must stay inside repository root")
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "exported_at": utc_now_iso(),
        "runs": list_runs(repo_root=root, registry_path=registry_path),
        "artifacts": list_artifact_records(repo_root=root, registry_path=registry_path),
        "validation": validate_registry(repo_root=root, registry_path=registry_path),
    }
    assert_no_sensitive_strings(snapshot)
    json_path = output_dir / "registry_snapshot.json"
    if json_path.exists() and not overwrite:
        raise FileExistsError(f"export already exists: {json_path.relative_to(root).as_posix()}")
    temp = json_path.with_name(f".{json_path.name}.tmp")
    try:
        temp.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(json_path)
    finally:
        if temp.exists():
            temp.unlink()
    csv_path = output_dir / "runs.csv"
    if csv_path.exists() and not overwrite:
        raise FileExistsError(f"export already exists: {csv_path.relative_to(root).as_posix()}")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "run_id",
            "manifest_kind",
            "pipeline_id",
            "plugin_id",
            "adapter_id",
            "stage",
            "status",
            "execution_mode",
            "dry_run",
            "code_commit",
            "manifest_relative_path",
            "created_at",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in snapshot["runs"]:
            writer.writerow({key: row.get(key) for key in fieldnames})
    return {
        "status": "exported",
        "json_path": json_path.relative_to(root).as_posix(),
        "csv_path": csv_path.relative_to(root).as_posix(),
        "run_count": len(snapshot["runs"]),
        "artifact_count": len(snapshot["artifacts"]),
    }
