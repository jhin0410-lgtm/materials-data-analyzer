"""Typed executor and verifier for the existing Battery run audit action."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from platform_core.battery_intelligence import audit_battery_intelligence_run
from platform_core.battery_intelligence.influence_triage import (
    audit_battery_influence_run,
)
from platform_core.output_safety import transactional_output_directory

from .action_registry import describe_action, load_action_registry
from .kernel import ResearchLoopError, append_action, load_research_state

REQUEST_SCHEMA_VERSION = "1.0"
REPORT_SCHEMA_VERSION = "1.0"
ACTION_TYPE = "audit_existing_battery_run"
ACTION_REPORT_FILENAME = "action_result.json"
_REQUEST_KEYS = {
    "schema_version",
    "action_id",
    "action_type",
    "research_run",
    "analysis_run",
    "registry",
    "repository_root",
    "expected_registry_sha256",
}
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_IMMUTABLE_RELATIVE_PATHS = (
    "tables/validated_cycle_summary.csv",
    "tables/forecast_feature_table.csv",
    "tables/validation_predictions.csv",
    "config_snapshot.json",
)
_MUTABLE_RELATIVE_PATHS = (
    "tables/target_integrity_by_battery.csv",
    "tables/error_concentration_by_battery.csv",
    "tables/battery_influence_by_model.csv",
    "tables/battery_diagnostic_priority.csv",
    "tables/battery_condition_error_profile.csv",
    "reports/target_comparability_audit.json",
    "reports/target_comparability_audit.md",
    "reports/battery_influence_triage.json",
    "reports/battery_influence_triage.md",
    "reports/scientific_closeout.json",
    "reports/scientific_closeout.md",
    "run_manifest.json",
)
_REQUIRED_RUN_PATHS = (*_IMMUTABLE_RELATIVE_PATHS, "reports/scientific_closeout.json", "run_manifest.json")


class NasaAuditActionError(ResearchLoopError):
    """Raised when a typed NASA audit action fails its contract."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NasaAuditActionError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise NasaAuditActionError(f"invalid JSON in {path}: {exc}") from exc


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_record(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"required action file not found: {path}")
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _resolve_request_path(raw: Any, *, field: str, base: Path) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise NasaAuditActionError(f"{field} must be a non-empty path string")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve(strict=True)


def _validate_request(path: Path) -> dict[str, Any]:
    raw = _load_json(path)
    if not isinstance(raw, dict):
        raise NasaAuditActionError("action request must be a JSON object")
    missing = sorted(_REQUEST_KEYS - set(raw))
    unknown = sorted(set(raw) - _REQUEST_KEYS)
    if missing:
        raise NasaAuditActionError(
            "action request is missing required keys: " + ", ".join(missing)
        )
    if unknown:
        raise NasaAuditActionError(
            "action request has unknown keys: " + ", ".join(unknown)
        )
    if raw["schema_version"] != REQUEST_SCHEMA_VERSION:
        raise NasaAuditActionError(
            f"unsupported action request schema_version: {raw['schema_version']!r}"
        )
    action_id = raw["action_id"]
    if not isinstance(action_id, str) or not _SAFE_ID.fullmatch(action_id):
        raise NasaAuditActionError(
            "action_id must use only letters, digits, dot, underscore, or hyphen"
        )
    if raw["action_type"] != ACTION_TYPE:
        raise NasaAuditActionError(
            f"this executor accepts only action_type={ACTION_TYPE!r}"
        )
    expected_sha = raw["expected_registry_sha256"]
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise NasaAuditActionError(
            "expected_registry_sha256 must be a lowercase SHA-256 hex string"
        )
    base = path.parent
    resolved = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "action_id": action_id,
        "action_type": ACTION_TYPE,
        "research_run": _resolve_request_path(
            raw["research_run"], field="research_run", base=base
        ),
        "analysis_run": _resolve_request_path(
            raw["analysis_run"], field="analysis_run", base=base
        ),
        "registry": _resolve_request_path(raw["registry"], field="registry", base=base),
        "repository_root": _resolve_request_path(
            raw["repository_root"], field="repository_root", base=base
        ),
        "expected_registry_sha256": expected_sha,
    }
    return resolved


def _paths_overlap(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def _snapshot(paths: list[Path]) -> dict[Path, bytes | None]:
    return {path: path.read_bytes() if path.is_file() else None for path in paths}


def _restore(snapshot: dict[Path, bytes | None]) -> None:
    for path, content in snapshot.items():
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


def _snapshot_matches(snapshot: dict[Path, bytes | None]) -> bool:
    for path, content in snapshot.items():
        if content is None:
            if path.exists():
                return False
        elif not path.is_file() or path.read_bytes() != content:
            return False
    return True


def _evidence_level(analysis_run: Path) -> str | None:
    closeout_path = analysis_run / "reports/scientific_closeout.json"
    if closeout_path.is_file():
        payload = _load_json(closeout_path)
        if isinstance(payload, dict) and payload.get("evidence_level") is not None:
            return str(payload["evidence_level"])
    manifest_path = analysis_run / "run_manifest.json"
    if manifest_path.is_file():
        manifest = _load_json(manifest_path)
        if isinstance(manifest, dict) and manifest.get("scientific_validation") is not None:
            return str(manifest["scientific_validation"])
    return None


def _verify_required_outputs(
    analysis_run: Path,
    action_contract: dict[str, Any],
    immutable_before: dict[Path, bytes | None],
    evidence_level_before: str | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not _snapshot_matches(immutable_before):
        raise NasaAuditActionError(
            "audit action modified an immutable Battery run input"
        )
    evidence_level_after = _evidence_level(analysis_run)
    if evidence_level_after != evidence_level_before:
        raise NasaAuditActionError(
            "audit action changed the existing scientific evidence level"
        )

    manifest_path = analysis_run / "run_manifest.json"
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise NasaAuditActionError("run_manifest.json must contain a JSON object")
    artifact_paths = manifest.get("artifact_paths")
    artifact_checksums = manifest.get("artifact_checksums")
    if not isinstance(artifact_paths, list) or not isinstance(artifact_checksums, dict):
        raise NasaAuditActionError(
            "run manifest must contain artifact_paths and artifact_checksums"
        )

    outputs: list[dict[str, Any]] = []
    for expected in action_contract["expected_outputs"]:
        if not expected["required"]:
            continue
        relative = str(expected["path"])
        output_path = analysis_run / relative
        record = _file_record(output_path)
        if output_path.suffix.lower() == ".json":
            payload = _load_json(output_path)
            if not isinstance(payload, dict):
                raise NasaAuditActionError(
                    f"required JSON output must contain an object: {relative}"
                )
        elif output_path.suffix.lower() == ".csv":
            frame = pd.read_csv(output_path)
            if frame.empty or not len(frame.columns):
                raise NasaAuditActionError(
                    f"required CSV output is empty or has no columns: {relative}"
                )
        if relative not in artifact_paths:
            raise NasaAuditActionError(
                f"required action output is absent from manifest artifact_paths: {relative}"
            )
        if artifact_checksums.get(relative) != record["sha256"]:
            raise NasaAuditActionError(
                f"manifest checksum mismatch for required action output: {relative}"
            )
        outputs.append({"relative_path": relative, **record})

    target_summary = _load_json(
        analysis_run / "reports/target_comparability_audit.json"
    )
    influence_summary = _load_json(
        analysis_run / "reports/battery_influence_triage.json"
    )
    outcomes: list[str] = []
    if int(target_summary.get("target_comparability_flag_battery_count", 0)) > 0:
        outcomes.append("target_or_reference_flags_detected")
    if (
        target_summary.get("pooled_error_stability_status") != "not_flagged"
        or int(influence_summary.get("source_protocol_review_battery_count", 0)) > 0
    ):
        outcomes.append("pooled_error_instability_detected")
    if target_summary.get("component_status") == "Inconclusive":
        outcomes.append("partial_dimensions_inconclusive")
    if not outcomes:
        outcomes.append("no_audit_flag_with_complete_dimensions")
    allowed = set(action_contract["allowed_outcomes"])
    if not set(outcomes).issubset(allowed):
        raise NasaAuditActionError(
            "audit verifier produced an outcome not allowed by the registry"
        )
    return outputs, outcomes


def _write_action_report(
    *,
    research_run: Path,
    action_id: str,
    request_path: Path,
    report: dict[str, Any],
) -> Path:
    action_directory = research_run / "actions" / action_id
    with transactional_output_directory(
        action_directory,
        protected_paths=(request_path,),
        recognized_markers=(ACTION_REPORT_FILENAME,),
    ) as staging:
        _atomic_write_json(staging / ACTION_REPORT_FILENAME, report)
    return action_directory / ACTION_REPORT_FILENAME


def _preflight(request_path: Path) -> dict[str, Any]:
    request = _validate_request(request_path)
    research_run = request["research_run"]
    analysis_run = request["analysis_run"]
    repository_root = request["repository_root"]
    if not research_run.is_dir() or not analysis_run.is_dir() or not repository_root.is_dir():
        raise NasaAuditActionError(
            "research_run, analysis_run, and repository_root must be directories"
        )
    if _paths_overlap(research_run, analysis_run):
        raise NasaAuditActionError(
            "research_run and analysis_run must be separate non-overlapping directories"
        )
    state = load_research_state(research_run)
    if state["status"] != "active":
        raise NasaAuditActionError("research run is stopped")
    if any(action["action_id"] == request["action_id"] for action in state["actions"]):
        raise NasaAuditActionError(f"duplicate action_id: {request['action_id']}")
    action_directory = research_run / "actions" / request["action_id"]
    if action_directory.exists():
        raise FileExistsError(f"action output already exists: {action_directory}")

    registry = load_action_registry(request["registry"], repository_root=repository_root)
    if registry["registry_sha256"] != request["expected_registry_sha256"]:
        raise NasaAuditActionError("action registry SHA-256 does not match the request")
    action_contract = describe_action(registry, ACTION_TYPE)
    if action_contract["availability"] != "available":
        raise NasaAuditActionError("registered action is not currently executable")
    binding = action_contract["binding"]
    if binding["kind"] != "installed_command" or binding["name"] != "mda-battery-result-audit":
        raise NasaAuditActionError("audit action binding does not match the fixed executor")
    if state["budget"]["actions_remaining"] <= 0:
        raise NasaAuditActionError("research action budget is exhausted")
    if action_contract["cost_units"] > state["budget"]["cost_units_remaining"]:
        raise NasaAuditActionError("research cost budget would be exceeded")

    missing = [
        relative
        for relative in _REQUIRED_RUN_PATHS
        if not (analysis_run / relative).is_file()
    ]
    if missing:
        raise NasaAuditActionError(
            "analysis run is missing required action inputs: " + ", ".join(missing)
        )
    return {
        "request": request,
        "state": state,
        "registry": registry,
        "action_contract": action_contract,
    }


def execute_nasa_audit_action(request_file: str | Path) -> dict[str, Any]:
    """Execute, verify, and ledger-record one existing Battery run audit action."""
    request_path = Path(request_file).expanduser().resolve(strict=True)
    preflight = _preflight(request_path)
    request = preflight["request"]
    analysis_run: Path = request["analysis_run"]
    research_run: Path = request["research_run"]
    action_contract = preflight["action_contract"]
    action_id = request["action_id"]
    started_at = _utc_now()

    immutable_paths = [analysis_run / relative for relative in _IMMUTABLE_RELATIVE_PATHS]
    mutable_paths = [analysis_run / relative for relative in _MUTABLE_RELATIVE_PATHS]
    immutable_snapshot = _snapshot(immutable_paths)
    mutable_snapshot = _snapshot(mutable_paths)
    evidence_before = _evidence_level(analysis_run)
    input_records = [_file_record(path) for path in immutable_paths]
    request_record = _file_record(request_path)

    try:
        target_result = audit_battery_intelligence_run(analysis_run)
        influence_result = audit_battery_influence_run(analysis_run)
        output_records, outcomes = _verify_required_outputs(
            analysis_run,
            action_contract,
            immutable_snapshot,
            evidence_before,
        )
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "execution_status": "completed",
            "action_id": action_id,
            "action_type": ACTION_TYPE,
            "action_version": action_contract["version"],
            "cost_units": action_contract["cost_units"],
            "started_at_utc": started_at,
            "completed_at_utc": _utc_now(),
            "request": request_record,
            "registry": {
                "registry_id": preflight["registry"]["registry_id"],
                "registry_path": preflight["registry"]["registry_path"],
                "registry_sha256": preflight["registry"]["registry_sha256"],
            },
            "research_run": str(research_run),
            "analysis_run": str(analysis_run),
            "immutable_inputs": input_records,
            "evidence_level_before": evidence_before,
            "evidence_level_after": _evidence_level(analysis_run),
            "outcomes": outcomes,
            "outputs": output_records,
            "target_reference_summary": target_result["summary"],
            "influence_summary": influence_result["summary"],
            "verification": {
                "immutable_inputs_unchanged": True,
                "evidence_level_preserved": True,
                "manifest_outputs_verified": True,
                "allowed_outcomes_only": True,
            },
        }
        report_path = _write_action_report(
            research_run=research_run,
            action_id=action_id,
            request_path=request_path,
            report=report,
        )
        state = append_action(
            research_run,
            action_id=action_id,
            action_type=ACTION_TYPE,
            status="completed",
            summary=(
                "Existing Battery run target/reference and influence audits completed "
                f"with outcomes: {', '.join(outcomes)}."
            ),
            cost_units=action_contract["cost_units"],
            artifact_paths=[report_path, *(Path(item["path"]) for item in output_records)],
        )
        return {
            "execution_status": "completed",
            "action_id": action_id,
            "outcomes": outcomes,
            "action_report": str(report_path),
            "research_state": state,
        }
    except Exception as exc:
        _restore({**mutable_snapshot, **immutable_snapshot})
        rollback_verified = _snapshot_matches(
            {**mutable_snapshot, **immutable_snapshot}
        )
        failure_report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "execution_status": "failed",
            "action_id": action_id,
            "action_type": ACTION_TYPE,
            "action_version": action_contract["version"],
            "cost_units": action_contract["cost_units"],
            "started_at_utc": started_at,
            "completed_at_utc": _utc_now(),
            "request": request_record,
            "registry": {
                "registry_id": preflight["registry"]["registry_id"],
                "registry_path": preflight["registry"]["registry_path"],
                "registry_sha256": preflight["registry"]["registry_sha256"],
            },
            "research_run": str(research_run),
            "analysis_run": str(analysis_run),
            "immutable_inputs": input_records,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "rollback_verified": rollback_verified,
        }
        report_path = _write_action_report(
            research_run=research_run,
            action_id=action_id,
            request_path=request_path,
            report=failure_report,
        )
        state = append_action(
            research_run,
            action_id=action_id,
            action_type=ACTION_TYPE,
            status="failed",
            summary=(
                f"Battery run audit failed and rollback_verified={rollback_verified}: "
                f"{type(exc).__name__}: {exc}"
            ),
            cost_units=action_contract["cost_units"],
            artifact_paths=[report_path],
        )
        return {
            "execution_status": "failed",
            "action_id": action_id,
            "error": str(exc),
            "rollback_verified": rollback_verified,
            "action_report": str(report_path),
            "research_state": state,
        }


def verify_nasa_audit_action_report(report_file: str | Path) -> dict[str, Any]:
    """Re-verify one completed or failed action report against current files and ledger."""
    report_path = Path(report_file).expanduser().resolve(strict=True)
    report = _load_json(report_path)
    if not isinstance(report, dict) or report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise NasaAuditActionError("invalid NASA audit action report schema")
    if report.get("action_type") != ACTION_TYPE:
        raise NasaAuditActionError("action report has the wrong action_type")
    status = report.get("execution_status")
    if status not in {"completed", "failed"}:
        raise NasaAuditActionError("action report has an invalid execution_status")

    request_record = report.get("request")
    if not isinstance(request_record, dict):
        raise NasaAuditActionError("action report request record is invalid")
    if _file_record(Path(request_record["path"])) != request_record:
        raise NasaAuditActionError("action request file no longer matches the report")

    for record in report.get("immutable_inputs", []):
        if _file_record(Path(record["path"])) != record:
            raise NasaAuditActionError(
                f"immutable input no longer matches the action report: {record['path']}"
            )
    for record in report.get("outputs", []):
        current = _file_record(Path(record["path"]))
        expected = {key: record[key] for key in ("path", "bytes", "sha256")}
        if current != expected:
            raise NasaAuditActionError(
                f"action output no longer matches the report: {record['path']}"
            )

    research_run = Path(report["research_run"])
    state = load_research_state(research_run)
    matching = [
        action
        for action in state["actions"]
        if action["action_id"] == report["action_id"]
    ]
    if len(matching) != 1 or matching[0]["status"] != status:
        raise NasaAuditActionError(
            "research ledger does not contain the matching action status"
        )
    report_record = _file_record(report_path)
    if not any(
        artifact["path"] == report_record["path"]
        and artifact["sha256"] == report_record["sha256"]
        and artifact["bytes"] == report_record["bytes"]
        for artifact in matching[0]["artifacts"]
    ):
        raise NasaAuditActionError(
            "research ledger does not checksum-bind the current action report"
        )
    return {
        "valid": True,
        "execution_status": status,
        "action_id": report["action_id"],
        "action_report": str(report_path),
        "research_id": state["research_id"],
        "ledger_sha256": state["ledger_sha256"],
    }
