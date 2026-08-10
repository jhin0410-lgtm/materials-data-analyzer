"""Typed execution and independent verification for protocol stratification."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from platform_core.output_safety import transactional_output_directory

from .action_registry import describe_action, load_action_registry
from .kernel import ResearchLoopError, append_action, load_research_state
from .nasa_audit_executor import verify_nasa_audit_action_report
from .nasa_target_reference_action import (
    ACTION_TYPE as TARGET_REFERENCE_ACTION_TYPE,
    verify_nasa_target_reference_report,
)
from .protocol_stratification import build_protocol_stratification

ACTION_TYPE = "protocol_stratification"
ACTION_REPORT_FILENAME = "action_result.json"
REQUEST_SCHEMA_VERSION = "1.0"
REPORT_SCHEMA_VERSION = "1.0"
OUTPUT_DIRECTORY_NAME = "protocol_stratification"
_REQUEST_KEYS = {
    "schema_version",
    "action_id",
    "action_type",
    "research_run",
    "import_run",
    "analysis_run",
    "registry",
    "repository_root",
    "expected_registry_sha256",
}
_REQUIRED_SOURCE_PATHS = (
    ("import_run", "nasa_pcoe_protocol_summary.csv"),
    ("analysis_run", "tables/validation_predictions.csv"),
    ("analysis_run", "reports/scientific_closeout.json"),
    ("analysis_run", "run_manifest.json"),
)
_OUTPUT_RELATIVE_PATHS = (
    "protocol_stratification/battery_protocol_errors.csv",
    "protocol_stratification/protocol_group_metrics.csv",
    "protocol_stratification/protocol_stratification.json",
)
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_REQUIRED_TARGET_OUTCOME = "conclusion_stable_across_defensible_targets"


class NasaProtocolStratificationActionError(ResearchLoopError):
    """Raised when protocol stratification violates its fixed contract."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise NasaProtocolStratificationActionError(
                f"duplicate JSON key is not allowed: {key}"
            )
        output[key] = value
    return output


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise NasaProtocolStratificationActionError(
            f"invalid JSON in {path}: {exc}"
        ) from exc


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


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_record(path: Path, *, recorded_path: Path | None = None) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"required action file not found: {path}")
    return {
        "path": str((recorded_path or path).resolve()),
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def _request_record_from_bytes(path: Path, data: bytes) -> dict[str, Any]:
    return {"path": str(path), "bytes": len(data), "sha256": _sha256_bytes(data)}


def _load_request_snapshot(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.is_file():
        raise NasaProtocolStratificationActionError(
            f"action request is not a file: {path}"
        )
    data = path.read_bytes()
    if not data:
        raise NasaProtocolStratificationActionError(
            "action request file must not be empty"
        )
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NasaProtocolStratificationActionError(
            "action request must be UTF-8 JSON"
        ) from exc
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise NasaProtocolStratificationActionError(
            f"invalid JSON in {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise NasaProtocolStratificationActionError(
            "action request must be a JSON object"
        )
    return value, _request_record_from_bytes(path, data)


def _validate_request_record(
    record: Mapping[str, Any], *, request_path: Path
) -> dict[str, Any]:
    if set(record) != {"path", "bytes", "sha256"}:
        raise NasaProtocolStratificationActionError(
            "request record must contain path, bytes, and sha256"
        )
    if record.get("path") != str(request_path):
        raise NasaProtocolStratificationActionError(
            "request record path does not match the pinned request path"
        )
    size = record.get("bytes")
    digest = record.get("sha256")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise NasaProtocolStratificationActionError(
            "request record bytes must be a positive integer"
        )
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise NasaProtocolStratificationActionError(
            "request record sha256 must be lowercase SHA-256 hex"
        )
    return {"path": str(request_path), "bytes": size, "sha256": digest}


def _resolve_path(raw: Any, *, field: str, base: Path) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise NasaProtocolStratificationActionError(
            f"{field} must be a non-empty path string"
        )
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve(strict=True)


def _validate_request(value: Mapping[str, Any], *, base: Path) -> dict[str, Any]:
    missing = sorted(_REQUEST_KEYS - set(value))
    unknown = sorted(set(value) - _REQUEST_KEYS)
    if missing:
        raise NasaProtocolStratificationActionError(
            "action request is missing required keys: " + ", ".join(missing)
        )
    if unknown:
        raise NasaProtocolStratificationActionError(
            "action request has unknown keys: " + ", ".join(unknown)
        )
    if value["schema_version"] != REQUEST_SCHEMA_VERSION:
        raise NasaProtocolStratificationActionError(
            f"unsupported action request schema_version: {value['schema_version']!r}"
        )
    action_id = value["action_id"]
    if not isinstance(action_id, str) or not _SAFE_ID.fullmatch(action_id):
        raise NasaProtocolStratificationActionError(
            "action_id must use only letters, digits, dot, underscore, or hyphen"
        )
    if value["action_type"] != ACTION_TYPE:
        raise NasaProtocolStratificationActionError(
            f"this executor accepts only action_type={ACTION_TYPE!r}"
        )
    registry_sha = value["expected_registry_sha256"]
    if not isinstance(registry_sha, str) or not re.fullmatch(
        r"[0-9a-f]{64}", registry_sha
    ):
        raise NasaProtocolStratificationActionError(
            "expected_registry_sha256 must be a lowercase SHA-256 hex string"
        )
    return {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "action_id": action_id,
        "action_type": ACTION_TYPE,
        "research_run": _resolve_path(
            value["research_run"], field="research_run", base=base
        ),
        "import_run": _resolve_path(
            value["import_run"], field="import_run", base=base
        ),
        "analysis_run": _resolve_path(
            value["analysis_run"], field="analysis_run", base=base
        ),
        "registry": _resolve_path(value["registry"], field="registry", base=base),
        "repository_root": _resolve_path(
            value["repository_root"], field="repository_root", base=base
        ),
        "expected_registry_sha256": registry_sha,
    }


def _paths_overlap(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def _snapshot(paths: list[Path]) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in paths}


def _snapshot_matches(snapshot: dict[Path, bytes]) -> bool:
    return all(
        path.is_file() and path.read_bytes() == content
        for path, content in snapshot.items()
    )


def _restore(snapshot: dict[Path, bytes]) -> None:
    for path, content in snapshot.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def _action_report(state: dict[str, Any], action_type: str, *, required: bool) -> Path | None:
    actions = [
        action for action in state["actions"] if action["action_type"] == action_type
    ]
    if not actions:
        if required:
            raise NasaProtocolStratificationActionError(
                f"a completed {action_type} action is required"
            )
        return None
    latest = actions[-1]
    if latest["status"] != "completed":
        raise NasaProtocolStratificationActionError(
            f"latest {action_type} action must be completed"
        )
    matches = [
        Path(artifact["path"])
        for artifact in latest.get("artifacts", [])
        if Path(artifact["path"]).name == ACTION_REPORT_FILENAME
    ]
    if len(matches) != 1:
        raise NasaProtocolStratificationActionError(
            f"completed {action_type} action must bind exactly one action_result.json"
        )
    return matches[0].resolve(strict=True)


def _verified_prior_reports(state: dict[str, Any]) -> dict[str, Path | None]:
    audit_report = _action_report(
        state, "audit_existing_battery_run", required=True
    )
    assert audit_report is not None
    verify_nasa_audit_action_report(audit_report)
    audit = _load_json(audit_report)
    target_required = "target_or_reference_flags_detected" in set(
        audit.get("outcomes", [])
    )
    target_report = _action_report(
        state, TARGET_REFERENCE_ACTION_TYPE, required=target_required
    )
    if target_report is not None:
        verified = verify_nasa_target_reference_report(target_report)
        if verified.get("outcome") != _REQUIRED_TARGET_OUTCOME:
            raise NasaProtocolStratificationActionError(
                "protocol stratification requires a stable target-reference conclusion"
            )
    return {"audit_report": audit_report, "target_report": target_report}


def _source_paths(request: dict[str, Any]) -> list[Path]:
    roots = {
        "import_run": request["import_run"],
        "analysis_run": request["analysis_run"],
    }
    return [roots[root] / relative for root, relative in _REQUIRED_SOURCE_PATHS]


def _compute(import_run: Path, analysis_run: Path) -> dict[str, Any]:
    return build_protocol_stratification(
        protocol_summary=pd.read_csv(
            import_run / "nasa_pcoe_protocol_summary.csv"
        ),
        predictions=pd.read_csv(
            analysis_run / "tables/validation_predictions.csv"
        ),
    )


def _write_outputs(root: Path, result: dict[str, Any]) -> list[Path]:
    output = root / OUTPUT_DIRECTORY_NAME
    output.mkdir(parents=True, exist_ok=True)
    result["battery_protocol_errors"].to_csv(
        output / "battery_protocol_errors.csv", index=False
    )
    result["protocol_group_metrics"].to_csv(
        output / "protocol_group_metrics.csv", index=False
    )
    _write_json(output / "protocol_stratification.json", result["summary"])
    return [root / relative for relative in _OUTPUT_RELATIVE_PATHS]


def _preflight(
    request_path: Path, request_value: Mapping[str, Any]
) -> dict[str, Any]:
    request = _validate_request(request_value, base=request_path.parent)
    research_run = request["research_run"]
    import_run = request["import_run"]
    analysis_run = request["analysis_run"]
    repository_root = request["repository_root"]
    if not all(
        path.is_dir()
        for path in (research_run, import_run, analysis_run, repository_root)
    ):
        raise NasaProtocolStratificationActionError(
            "research_run, import_run, analysis_run, and repository_root must be directories"
        )
    if _paths_overlap(research_run, import_run) or _paths_overlap(
        research_run, analysis_run
    ):
        raise NasaProtocolStratificationActionError(
            "research_run must not overlap import_run or analysis_run"
        )
    state = load_research_state(research_run)
    if state["status"] != "active":
        raise NasaProtocolStratificationActionError("research run is stopped")
    if any(action["action_id"] == request["action_id"] for action in state["actions"]):
        raise NasaProtocolStratificationActionError(
            f"duplicate action_id: {request['action_id']}"
        )
    action_directory = research_run / "actions" / request["action_id"]
    if action_directory.exists():
        raise FileExistsError(f"action output already exists: {action_directory}")

    prior_reports = _verified_prior_reports(state)
    registry = load_action_registry(request["registry"], repository_root=repository_root)
    if registry["registry_sha256"] != request["expected_registry_sha256"]:
        raise NasaProtocolStratificationActionError(
            "action registry SHA-256 does not match the request"
        )
    contract = describe_action(registry, ACTION_TYPE)
    if contract["availability"] != "available":
        raise NasaProtocolStratificationActionError(
            "registered protocol-stratification action is not executable"
        )
    binding = contract["binding"]
    if (
        binding["kind"] != "installed_command"
        or binding["name"] != "mda-research-loop"
    ):
        raise NasaProtocolStratificationActionError(
            "protocol-stratification binding does not match the fixed executor"
        )
    if state["budget"]["actions_remaining"] <= 0:
        raise NasaProtocolStratificationActionError(
            "research action budget is exhausted"
        )
    if contract["cost_units"] > state["budget"]["cost_units_remaining"]:
        raise NasaProtocolStratificationActionError(
            "research cost budget would be exceeded"
        )
    missing = [str(path) for path in _source_paths(request) if not path.is_file()]
    if missing:
        raise NasaProtocolStratificationActionError(
            "protocol action is missing required source files: " + ", ".join(missing)
        )
    return {
        "request": request,
        "state": state,
        "registry": registry,
        "contract": contract,
        **prior_reports,
    }


def execute_nasa_protocol_stratification_action_preparsed(
    request_value: Mapping[str, Any],
    *,
    request_path: str | Path,
    request_record: Mapping[str, Any],
) -> dict[str, Any]:
    """Execute protocol stratification from already-pinned request bytes."""
    pinned_path = Path(request_path)
    if not pinned_path.is_absolute():
        raise NasaProtocolStratificationActionError(
            "pinned request_path must be absolute"
        )
    pinned_record = _validate_request_record(request_record, request_path=pinned_path)
    preflight = _preflight(pinned_path, request_value)
    request = preflight["request"]
    action_id = request["action_id"]
    research_run: Path = request["research_run"]
    import_run: Path = request["import_run"]
    analysis_run: Path = request["analysis_run"]
    contract = preflight["contract"]
    started_at = _utc_now()
    source_paths = _source_paths(request)
    source_snapshot = _snapshot(source_paths)
    input_records = [_file_record(path) for path in source_paths]
    request_record_dict = dict(pinned_record)
    action_directory = research_run / "actions" / action_id

    try:
        result = _compute(import_run, analysis_run)
        outcome = str(result["summary"]["outcome"])
        if outcome not in contract["allowed_outcomes"]:
            raise NasaProtocolStratificationActionError(
                "computed outcome is not allowed by the action registry"
            )
        if not _snapshot_matches(source_snapshot):
            raise NasaProtocolStratificationActionError(
                "protocol action modified an immutable source input"
            )
        with transactional_output_directory(
            action_directory,
            protected_paths=(pinned_path, import_run, analysis_run),
            recognized_markers=(ACTION_REPORT_FILENAME,),
        ) as staging:
            staged_outputs = _write_outputs(staging, result)
            output_records = []
            for staged_path in staged_outputs:
                relative = staged_path.relative_to(staging)
                output_records.append(
                    {
                        "relative_path": relative.as_posix(),
                        **_file_record(
                            staged_path,
                            recorded_path=action_directory / relative,
                        ),
                    }
                )
            report = {
                "schema_version": REPORT_SCHEMA_VERSION,
                "execution_status": "completed",
                "action_id": action_id,
                "action_type": ACTION_TYPE,
                "action_version": contract["version"],
                "cost_units": contract["cost_units"],
                "started_at_utc": started_at,
                "completed_at_utc": _utc_now(),
                "request": request_record_dict,
                "registry": {
                    "registry_id": preflight["registry"]["registry_id"],
                    "registry_path": preflight["registry"]["registry_path"],
                    "registry_sha256": preflight["registry"]["registry_sha256"],
                },
                "research_run": str(research_run),
                "import_run": str(import_run),
                "analysis_run": str(analysis_run),
                "prior_audit_report": _file_record(preflight["audit_report"]),
                "prior_target_reference_report": (
                    _file_record(preflight["target_report"])
                    if preflight["target_report"] is not None
                    else None
                ),
                "immutable_inputs": input_records,
                "outcome": outcome,
                "summary": result["summary"],
                "outputs": output_records,
                "verification": {
                    "explicit_protocol_metadata_only": True,
                    "battery_level_primary_test": True,
                    "model_refit_not_performed": True,
                    "source_inputs_unchanged": True,
                    "all_protocol_batteries_preserved": True,
                    "evidence_level_unchanged": True,
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
            summary=f"Protocol stratification completed with outcome: {outcome}.",
            cost_units=contract["cost_units"],
            artifact_paths=[report_path, *final_outputs],
        )
        return {
            "execution_status": "completed",
            "action_id": action_id,
            "outcome": outcome,
            "action_report": str(report_path),
            "research_state": state,
        }
    except Exception as exc:
        _restore(source_snapshot)
        rollback_verified = _snapshot_matches(source_snapshot)
        failure_report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "execution_status": "failed",
            "action_id": action_id,
            "action_type": ACTION_TYPE,
            "action_version": contract["version"],
            "cost_units": contract["cost_units"],
            "started_at_utc": started_at,
            "completed_at_utc": _utc_now(),
            "request": request_record_dict,
            "registry": {
                "registry_id": preflight["registry"]["registry_id"],
                "registry_path": preflight["registry"]["registry_path"],
                "registry_sha256": preflight["registry"]["registry_sha256"],
            },
            "research_run": str(research_run),
            "import_run": str(import_run),
            "analysis_run": str(analysis_run),
            "prior_audit_report": _file_record(preflight["audit_report"]),
            "prior_target_reference_report": (
                _file_record(preflight["target_report"])
                if preflight["target_report"] is not None
                else None
            ),
            "immutable_inputs": input_records,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "rollback_verified": rollback_verified,
        }
        with transactional_output_directory(
            action_directory,
            protected_paths=(pinned_path, import_run, analysis_run),
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
                "Protocol stratification failed and "
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


def execute_nasa_protocol_stratification_action(
    request_file: str | Path,
) -> dict[str, Any]:
    """Execute exact-temperature stratification and append its ledger result."""
    request_path = Path(request_file).expanduser().resolve(strict=True)
    request_value, request_record = _load_request_snapshot(request_path)
    return execute_nasa_protocol_stratification_action_preparsed(
        request_value,
        request_path=request_path,
        request_record=request_record,
    )


def verify_nasa_protocol_stratification_report(
    report_file: str | Path,
) -> dict[str, Any]:
    """Recompute and verify a protocol action report, outputs, and ledger."""
    report_path = Path(report_file).expanduser().resolve(strict=True)
    report = _load_json(report_path)
    if not isinstance(report, dict) or report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise NasaProtocolStratificationActionError(
            "invalid protocol-stratification action report schema"
        )
    if report.get("action_type") != ACTION_TYPE:
        raise NasaProtocolStratificationActionError(
            "action report has the wrong action_type"
        )
    status = report.get("execution_status")
    if status not in {"completed", "failed"}:
        raise NasaProtocolStratificationActionError(
            "action report has an invalid execution_status"
        )
    request_record = report.get("request")
    if not isinstance(request_record, dict) or _file_record(
        Path(request_record["path"])
    ) != request_record:
        raise NasaProtocolStratificationActionError(
            "action request file no longer matches the report"
        )
    for record in report.get("immutable_inputs", []):
        if _file_record(Path(record["path"])) != record:
            raise NasaProtocolStratificationActionError(
                f"immutable input no longer matches the report: {record['path']}"
            )
    audit_record = report.get("prior_audit_report")
    if not isinstance(audit_record, dict) or _file_record(
        Path(audit_record["path"])
    ) != audit_record:
        raise NasaProtocolStratificationActionError(
            "prior audit report no longer matches the protocol report"
        )
    verify_nasa_audit_action_report(audit_record["path"])
    target_record = report.get("prior_target_reference_report")
    if target_record is not None:
        if not isinstance(target_record, dict) or _file_record(
            Path(target_record["path"])
        ) != target_record:
            raise NasaProtocolStratificationActionError(
                "prior target-reference report no longer matches the protocol report"
            )
        target = verify_nasa_target_reference_report(target_record["path"])
        if target.get("outcome") != _REQUIRED_TARGET_OUTCOME:
            raise NasaProtocolStratificationActionError(
                "verified target-reference outcome is not stable"
            )

    if status == "completed":
        result = _compute(Path(report["import_run"]), Path(report["analysis_run"]))
        if report.get("summary") != result["summary"]:
            raise NasaProtocolStratificationActionError(
                "reported protocol summary is not reproducible"
            )
        with tempfile.TemporaryDirectory(prefix="mda-protocol-verify-") as temporary:
            expected_root = Path(temporary)
            expected_paths = _write_outputs(expected_root, result)
            expected = {
                path.relative_to(expected_root).as_posix(): path
                for path in expected_paths
            }
            records = report.get("outputs", [])
            if not isinstance(records, list) or len(records) != len(expected):
                raise NasaProtocolStratificationActionError(
                    "action report does not bind every required output"
                )
            for record in records:
                relative = str(record["relative_path"])
                source = expected.get(relative)
                current_path = Path(record["path"])
                current = _file_record(current_path)
                recorded = {
                    key: record[key] for key in ("path", "bytes", "sha256")
                }
                if source is None or current != recorded:
                    raise NasaProtocolStratificationActionError(
                        f"action output no longer matches the report: {relative}"
                    )
                if current_path.read_bytes() != source.read_bytes():
                    raise NasaProtocolStratificationActionError(
                        f"action output is not reproducible from source inputs: {relative}"
                    )

    research_run = Path(report["research_run"])
    state = load_research_state(research_run)
    matching = [
        action
        for action in state["actions"]
        if action["action_id"] == report["action_id"]
    ]
    if len(matching) != 1 or matching[0]["status"] != status:
        raise NasaProtocolStratificationActionError(
            "research ledger does not contain the matching action status"
        )
    report_record = _file_record(report_path)
    if not any(
        artifact["path"] == report_record["path"]
        and artifact["sha256"] == report_record["sha256"]
        and artifact["bytes"] == report_record["bytes"]
        for artifact in matching[0]["artifacts"]
    ):
        raise NasaProtocolStratificationActionError(
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
