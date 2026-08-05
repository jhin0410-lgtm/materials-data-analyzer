"""Typed executor and verifier for NASA target-reference sensitivity."""

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

from platform_core.output_safety import transactional_output_directory

from .action_registry import describe_action, load_action_registry
from .kernel import ResearchLoopError, append_action, load_research_state
from .nasa_audit_executor import verify_nasa_audit_action_report
from .target_reference_sensitivity import build_target_reference_sensitivity

REQUEST_SCHEMA_VERSION = "1.0"
REPORT_SCHEMA_VERSION = "1.0"
ACTION_TYPE = "target_reference_sensitivity"
ACTION_REPORT_FILENAME = "action_result.json"
OUTPUT_DIRECTORY_NAME = "target_reference_sensitivity"
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
_REQUIRED_ANALYSIS_PATHS = (
    "tables/validated_cycle_summary.csv",
    "tables/validation_predictions.csv",
    "config_snapshot.json",
    "reports/target_comparability_audit.json",
    "reports/scientific_closeout.json",
    "run_manifest.json",
)
_OUTPUT_RELATIVE_PATHS = (
    "target_reference_sensitivity/reference_definitions.json",
    "target_reference_sensitivity/target_reference_by_battery.csv",
    "target_reference_sensitivity/model_metrics_by_reference.csv",
    "target_reference_sensitivity/battery_metrics_by_reference.csv",
    "target_reference_sensitivity/target_reference_sensitivity.json",
)


class NasaTargetReferenceActionError(ResearchLoopError):
    """Raised when the typed target-reference action violates its contract."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NasaTargetReferenceActionError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise NasaTargetReferenceActionError(f"invalid JSON in {path}: {exc}") from exc


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
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _resolve_path(raw: Any, *, field: str, base: Path) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise NasaTargetReferenceActionError(
            f"{field} must be a non-empty path string"
        )
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve(strict=True)


def _validate_request(path: Path) -> dict[str, Any]:
    raw = _load_json(path)
    if not isinstance(raw, dict):
        raise NasaTargetReferenceActionError("action request must be a JSON object")
    missing = sorted(_REQUEST_KEYS - set(raw))
    unknown = sorted(set(raw) - _REQUEST_KEYS)
    if missing:
        raise NasaTargetReferenceActionError(
            "action request is missing required keys: " + ", ".join(missing)
        )
    if unknown:
        raise NasaTargetReferenceActionError(
            "action request has unknown keys: " + ", ".join(unknown)
        )
    if raw["schema_version"] != REQUEST_SCHEMA_VERSION:
        raise NasaTargetReferenceActionError(
            f"unsupported action request schema_version: {raw['schema_version']!r}"
        )
    action_id = raw["action_id"]
    if not isinstance(action_id, str) or not _SAFE_ID.fullmatch(action_id):
        raise NasaTargetReferenceActionError(
            "action_id must use only letters, digits, dot, underscore, or hyphen"
        )
    if raw["action_type"] != ACTION_TYPE:
        raise NasaTargetReferenceActionError(
            f"this executor accepts only action_type={ACTION_TYPE!r}"
        )
    expected_sha = raw["expected_registry_sha256"]
    if not isinstance(expected_sha, str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_sha
    ):
        raise NasaTargetReferenceActionError(
            "expected_registry_sha256 must be a lowercase SHA-256 hex string"
        )
    base = path.parent
    return {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "action_id": action_id,
        "action_type": ACTION_TYPE,
        "research_run": _resolve_path(
            raw["research_run"], field="research_run", base=base
        ),
        "analysis_run": _resolve_path(
            raw["analysis_run"], field="analysis_run", base=base
        ),
        "registry": _resolve_path(raw["registry"], field="registry", base=base),
        "repository_root": _resolve_path(
            raw["repository_root"], field="repository_root", base=base
        ),
        "expected_registry_sha256": expected_sha,
    }


def _paths_overlap(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def _snapshot(paths: list[Path]) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in paths}


def _snapshot_matches(snapshot: dict[Path, bytes]) -> bool:
    return all(path.is_file() and path.read_bytes() == value for path, value in snapshot.items())


def _restore(snapshot: dict[Path, bytes]) -> None:
    for path, value in snapshot.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)


def _audit_report_from_state(state: dict[str, Any]) -> Path:
    completed = [
        action
        for action in state["actions"]
        if action["action_type"] == "audit_existing_battery_run"
        and action["status"] == "completed"
    ]
    if not completed:
        raise NasaTargetReferenceActionError(
            "a completed audit_existing_battery_run action is required"
        )
    artifacts = completed[-1].get("artifacts", [])
    matches = [
        Path(item["path"])
        for item in artifacts
        if Path(item["path"]).name == ACTION_REPORT_FILENAME
    ]
    if len(matches) != 1:
        raise NasaTargetReferenceActionError(
            "completed audit action must bind exactly one action_result.json"
        )
    verify_nasa_audit_action_report(matches[0])
    return matches[0].resolve(strict=True)


def _load_config(analysis_run: Path) -> dict[str, Any]:
    payload = _load_json(analysis_run / "config_snapshot.json")
    if not isinstance(payload, dict) or not isinstance(payload.get("config"), dict):
        raise NasaTargetReferenceActionError(
            "config_snapshot.json must contain a config object"
        )
    return dict(payload["config"])


def _compute(analysis_run: Path) -> dict[str, Any]:
    return build_target_reference_sensitivity(
        cycle_summary=pd.read_csv(
            analysis_run / "tables/validated_cycle_summary.csv"
        ),
        predictions=pd.read_csv(
            analysis_run / "tables/validation_predictions.csv"
        ),
        config=_load_config(analysis_run),
    )


def _write_outputs(root: Path, result: dict[str, Any]) -> list[Path]:
    output = root / OUTPUT_DIRECTORY_NAME
    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / "reference_definitions.json", result["reference_definitions"])
    result["target_reference_by_battery"].to_csv(
        output / "target_reference_by_battery.csv", index=False
    )
    result["model_metrics_by_reference"].to_csv(
        output / "model_metrics_by_reference.csv", index=False
    )
    result["battery_metrics_by_reference"].to_csv(
        output / "battery_metrics_by_reference.csv", index=False
    )
    _write_json(output / "target_reference_sensitivity.json", result["summary"])
    return [root / relative for relative in _OUTPUT_RELATIVE_PATHS]


def _preflight(request_path: Path) -> dict[str, Any]:
    request = _validate_request(request_path)
    research_run = request["research_run"]
    analysis_run = request["analysis_run"]
    repository_root = request["repository_root"]
    if not research_run.is_dir() or not analysis_run.is_dir() or not repository_root.is_dir():
        raise NasaTargetReferenceActionError(
            "research_run, analysis_run, and repository_root must be directories"
        )
    if _paths_overlap(research_run, analysis_run):
        raise NasaTargetReferenceActionError(
            "research_run and analysis_run must be separate non-overlapping directories"
        )
    state = load_research_state(research_run)
    if state["status"] != "active":
        raise NasaTargetReferenceActionError("research run is stopped")
    if any(action["action_id"] == request["action_id"] for action in state["actions"]):
        raise NasaTargetReferenceActionError(
            f"duplicate action_id: {request['action_id']}"
        )
    action_directory = research_run / "actions" / request["action_id"]
    if action_directory.exists():
        raise FileExistsError(f"action output already exists: {action_directory}")

    audit_report = _audit_report_from_state(state)
    registry = load_action_registry(request["registry"], repository_root=repository_root)
    if registry["registry_sha256"] != request["expected_registry_sha256"]:
        raise NasaTargetReferenceActionError(
            "action registry SHA-256 does not match the request"
        )
    contract = describe_action(registry, ACTION_TYPE)
    if contract["availability"] != "available":
        raise NasaTargetReferenceActionError(
            "registered target-reference action is not currently executable"
        )
    binding = contract["binding"]
    if (
        binding["kind"] != "installed_command"
        or binding["name"] != "mda-research-loop"
    ):
        raise NasaTargetReferenceActionError(
            "target-reference action binding does not match the fixed executor"
        )
    if state["budget"]["actions_remaining"] <= 0:
        raise NasaTargetReferenceActionError("research action budget is exhausted")
    if contract["cost_units"] > state["budget"]["cost_units_remaining"]:
        raise NasaTargetReferenceActionError(
            "research cost budget would be exceeded"
        )
    missing = [
        relative
        for relative in _REQUIRED_ANALYSIS_PATHS
        if not (analysis_run / relative).is_file()
    ]
    if missing:
        raise NasaTargetReferenceActionError(
            "analysis run is missing required action inputs: " + ", ".join(missing)
        )
    return {
        "request": request,
        "state": state,
        "registry": registry,
        "contract": contract,
        "audit_report": audit_report,
    }


def execute_nasa_target_reference_action(request_file: str | Path) -> dict[str, Any]:
    """Execute and ledger-record one fixed target-reference sensitivity action."""
    request_path = Path(request_file).expanduser().resolve(strict=True)
    preflight = _preflight(request_path)
    request = preflight["request"]
    action_id = request["action_id"]
    analysis_run: Path = request["analysis_run"]
    research_run: Path = request["research_run"]
    contract = preflight["contract"]
    started_at = _utc_now()
    input_paths = [analysis_run / relative for relative in _REQUIRED_ANALYSIS_PATHS]
    input_snapshot = _snapshot(input_paths)
    input_records = [_file_record(path) for path in input_paths]
    request_record = _file_record(request_path)

    try:
        result = _compute(analysis_run)
        if result["summary"]["outcome"] not in contract["allowed_outcomes"]:
            raise NasaTargetReferenceActionError(
                "computed outcome is not allowed by the action registry"
            )
        if not _snapshot_matches(input_snapshot):
            raise NasaTargetReferenceActionError(
                "target-reference action modified an immutable analysis input"
            )
        action_directory = research_run / "actions" / action_id
        report: dict[str, Any]
        with transactional_output_directory(
            action_directory,
            protected_paths=(request_path, analysis_run),
            recognized_markers=(ACTION_REPORT_FILENAME,),
        ) as staging:
            output_paths = _write_outputs(staging, result)
            output_records = [
                {
                    "relative_path": path.relative_to(staging).as_posix(),
                    **_file_record(path),
                }
                for path in output_paths
            ]
            report = {
                "schema_version": REPORT_SCHEMA_VERSION,
                "execution_status": "completed",
                "action_id": action_id,
                "action_type": ACTION_TYPE,
                "action_version": contract["version"],
                "cost_units": contract["cost_units"],
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
                "prior_audit_report": _file_record(preflight["audit_report"]),
                "immutable_inputs": input_records,
                "outcome": result["summary"]["outcome"],
                "summary": result["summary"],
                "outputs": output_records,
                "verification": {
                    "predeclared_references_only": True,
                    "model_refit_not_performed": True,
                    "analysis_inputs_unchanged": True,
                    "all_prediction_rows_preserved_when_complete": True,
                    "primary_reference_unchanged": True,
                },
            }
            _write_json(staging / ACTION_REPORT_FILENAME, report)
        report_path = action_directory / ACTION_REPORT_FILENAME
        final_outputs = [action_directory / relative for relative in _OUTPUT_RELATIVE_PATHS]
        state = append_action(
            research_run,
            action_id=action_id,
            action_type=ACTION_TYPE,
            status="completed",
            summary=(
                "Predeclared target-reference sensitivity completed with outcome: "
                f"{report['outcome']}."
            ),
            cost_units=contract["cost_units"],
            artifact_paths=[report_path, *final_outputs],
        )
        return {
            "execution_status": "completed",
            "action_id": action_id,
            "outcome": report["outcome"],
            "action_report": str(report_path),
            "research_state": state,
        }
    except Exception as exc:
        _restore(input_snapshot)
        rollback_verified = _snapshot_matches(input_snapshot)
        action_directory = research_run / "actions" / action_id
        failure_report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "execution_status": "failed",
            "action_id": action_id,
            "action_type": ACTION_TYPE,
            "action_version": contract["version"],
            "cost_units": contract["cost_units"],
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
            "prior_audit_report": _file_record(preflight["audit_report"]),
            "immutable_inputs": input_records,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "rollback_verified": rollback_verified,
        }
        with transactional_output_directory(
            action_directory,
            protected_paths=(request_path, analysis_run),
            recognized_markers=(ACTION_REPORT_FILENAME,),
        ) as staging:
            _write_json(staging / ACTION_REPORT_FILENAME, failure_report)
        report_path = action_directory / ACTION_REPORT_FILENAME
        state = append_action(
            research_run,
            action_id=action_id,
            action_type=ACTION_TYPE,
            status="failed",
            summary=(
                "Target-reference sensitivity failed and "
                f"rollback_verified={rollback_verified}: {type(exc).__name__}: {exc}"
            ),
            cost_units=contract["cost_units"],
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


def verify_nasa_target_reference_report(report_file: str | Path) -> dict[str, Any]:
    """Recompute and verify one target-reference action report and its ledger binding."""
    report_path = Path(report_file).expanduser().resolve(strict=True)
    report = _load_json(report_path)
    if not isinstance(report, dict) or report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise NasaTargetReferenceActionError(
            "invalid target-reference action report schema"
        )
    if report.get("action_type") != ACTION_TYPE:
        raise NasaTargetReferenceActionError("action report has the wrong action_type")
    status = report.get("execution_status")
    if status not in {"completed", "failed"}:
        raise NasaTargetReferenceActionError(
            "action report has an invalid execution_status"
        )
    request_record = report.get("request")
    if not isinstance(request_record, dict) or _file_record(
        Path(request_record["path"])
    ) != request_record:
        raise NasaTargetReferenceActionError(
            "action request file no longer matches the report"
        )
    for record in report.get("immutable_inputs", []):
        if _file_record(Path(record["path"])) != record:
            raise NasaTargetReferenceActionError(
                f"immutable input no longer matches the report: {record['path']}"
            )
    prior_audit = report.get("prior_audit_report")
    if not isinstance(prior_audit, dict) or _file_record(
        Path(prior_audit["path"])
    ) != prior_audit:
        raise NasaTargetReferenceActionError(
            "prior audit report no longer matches the target-reference report"
        )
    verify_nasa_audit_action_report(prior_audit["path"])

    if status == "completed":
        analysis_run = Path(report["analysis_run"])
        result = _compute(analysis_run)
        with tempfile.TemporaryDirectory(prefix="mda-target-reference-verify-") as temporary:
            expected_root = Path(temporary)
            expected_paths = _write_outputs(expected_root, result)
            expected_by_relative = {
                path.relative_to(expected_root).as_posix(): path for path in expected_paths
            }
            for record in report.get("outputs", []):
                relative = str(record["relative_path"])
                current = _file_record(Path(record["path"]))
                expected = expected_by_relative.get(relative)
                if expected is None or current != {
                    key: record[key] for key in ("path", "bytes", "sha256")
                }:
                    raise NasaTargetReferenceActionError(
                        f"action output no longer matches the report: {relative}"
                    )
                if Path(record["path"]).read_bytes() != expected.read_bytes():
                    raise NasaTargetReferenceActionError(
                        f"action output is not reproducible from source inputs: {relative}"
                    )
        if report.get("summary") != result["summary"]:
            raise NasaTargetReferenceActionError(
                "reported target-reference summary is not reproducible"
            )

    research_run = Path(report["research_run"])
    state = load_research_state(research_run)
    matching = [
        action
        for action in state["actions"]
        if action["action_id"] == report["action_id"]
    ]
    if len(matching) != 1 or matching[0]["status"] != status:
        raise NasaTargetReferenceActionError(
            "research ledger does not contain the matching action status"
        )
    report_record = _file_record(report_path)
    if not any(
        artifact["path"] == report_record["path"]
        and artifact["sha256"] == report_record["sha256"]
        and artifact["bytes"] == report_record["bytes"]
        for artifact in matching[0]["artifacts"]
    ):
        raise NasaTargetReferenceActionError(
            "research ledger does not checksum-bind the current action report"
        )
    return {
        "valid": True,
        "execution_status": status,
        "action_id": report["action_id"],
        "outcome": report.get("outcome"),
        "action_report": str(report_path),
        "research_id": state["research_id"],
        "ledger_sha256": state["ledger_sha256"],
    }
