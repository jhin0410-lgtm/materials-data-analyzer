"""Typed registration of one real, SHA-pinned IN625 external evidence archive.

The action consumes an archive that has already crossed an explicit network/acquisition
boundary.  It independently re-verifies the exact Zenodo source policy, the full archive
SHA-256, and every selected numerical member before appending one immutable research-ledger
action.  Registration establishes source availability/provenance only; it does not establish
condition comparability, measurement semantics, empirical model validity, or hypothesis truth.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from platform_core.output_safety import transactional_output_directory

from .action_registry import describe_action, load_action_registry
from .in625_zenodo_live_evidence import inspect_verified_in625_dataset_archive
from .kernel import ResearchLoopError, append_action, load_research_state

ACTION_TYPE = "external_evidence_search"
ACTION_VERSION = "1.0"
COST_UNITS = 2
REQUEST_SCHEMA_VERSION = "1.0"
REPORT_SCHEMA_VERSION = "1.0"
ACTION_REPORT_FILENAME = "action_result.json"
OUTPUT_RELATIVE_PATH = "reports/verified_external_evidence.json"
EXPECTED_BINDING_PATH = "scripts/run_in625_external_evidence_action.py"
EXPECTED_REGISTRY_DOMAIN = "in625_external_empirical_evidence"
EXPECTED_SOURCE_ID = "zenodo-20503603-in625-lpbf-publication-supplement"
EXPECTED_RECORD_ID = 20503603
_REGISTERED_OUTCOME = "verified_external_source_archive_registered"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_KEYS = {
    "schema_version",
    "action_id",
    "action_type",
    "action_version",
    "research_run",
    "source_config",
    "expected_source_config_sha256",
    "archive_path",
    "expected_archive_sha256",
    "registry",
    "repository_root",
    "expected_registry_sha256",
}


class In625ExternalEvidenceActionError(ResearchLoopError):
    """Raised when the real external-source registration boundary drifts."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    return {
        "path": str(resolved),
        "bytes": resolved.stat().st_size,
        "sha256": _sha256_file(resolved),
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise In625ExternalEvidenceActionError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_json_file(path: Path, *, field: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise In625ExternalEvidenceActionError(f"{field} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise In625ExternalEvidenceActionError(f"{field} root must be an object")
    return value


def _resolve(raw: object, *, field: str, base: Path) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise In625ExternalEvidenceActionError(f"{field} must be a path string")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        return candidate.resolve(strict=True)
    except OSError as exc:
        raise In625ExternalEvidenceActionError(f"{field} does not resolve") from exc


def _within(path: Path, parent: Path, *, field: str) -> None:
    try:
        path.relative_to(parent)
    except ValueError as exc:
        raise In625ExternalEvidenceActionError(f"{field} escapes repository_root") from exc


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise In625ExternalEvidenceActionError(f"{field} must be lowercase SHA-256")
    return value


def _validate_request(value: Mapping[str, Any], *, request_path: Path) -> dict[str, Any]:
    if set(value) != _REQUEST_KEYS:
        raise In625ExternalEvidenceActionError("typed IN625 execution request field set drifted")
    if value.get("schema_version") != REQUEST_SCHEMA_VERSION:
        raise In625ExternalEvidenceActionError("unsupported typed IN625 execution request schema")
    action_id = value.get("action_id")
    if not isinstance(action_id, str) or _SAFE_ID.fullmatch(action_id) is None:
        raise In625ExternalEvidenceActionError("action_id is not executor-safe")
    if value.get("action_type") != ACTION_TYPE or value.get("action_version") != ACTION_VERSION:
        raise In625ExternalEvidenceActionError("IN625 action type/version binding drifted")
    base = request_path.parent
    return {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "action_id": action_id,
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "research_run": _resolve(value.get("research_run"), field="research_run", base=base),
        "source_config": _resolve(value.get("source_config"), field="source_config", base=base),
        "expected_source_config_sha256": _sha(
            value.get("expected_source_config_sha256"), "expected_source_config_sha256"
        ),
        "archive_path": _resolve(value.get("archive_path"), field="archive_path", base=base),
        "expected_archive_sha256": _sha(
            value.get("expected_archive_sha256"), "expected_archive_sha256"
        ),
        "registry": _resolve(value.get("registry"), field="registry", base=base),
        "repository_root": _resolve(
            value.get("repository_root"), field="repository_root", base=base
        ),
        "expected_registry_sha256": _sha(
            value.get("expected_registry_sha256"), "expected_registry_sha256"
        ),
    }


def _source_policy(config: Mapping[str, Any]) -> tuple[str, str]:
    if config.get("source_id") != EXPECTED_SOURCE_ID:
        raise In625ExternalEvidenceActionError("IN625 source_id drifted from the registered source")
    zenodo = config.get("zenodo")
    if not isinstance(zenodo, Mapping) or zenodo.get("record_id") != EXPECTED_RECORD_ID:
        raise In625ExternalEvidenceActionError("IN625 Zenodo record identity drifted")
    files = zenodo.get("files")
    archive_name = zenodo.get("archive_file")
    if not isinstance(files, Mapping) or not isinstance(archive_name, str):
        raise In625ExternalEvidenceActionError("IN625 source config archive identity is malformed")
    archive = files.get(archive_name)
    if not isinstance(archive, Mapping):
        raise In625ExternalEvidenceActionError("IN625 source config archive entry is missing")
    archive_sha = _sha(archive.get("verified_sha256"), "source_config archive verified_sha256")
    boundaries = config.get("scientific_boundaries")
    if not isinstance(boundaries, Mapping):
        raise In625ExternalEvidenceActionError("IN625 source scientific boundaries are missing")
    for key in (
        "automatic_scientific_promotion",
        "source_acquisition_establishes_direct_nist_comparability",
        "source_acquisition_establishes_hypothesis_truth",
        "source_acquisition_establishes_positive_scientific_closeout",
    ):
        if boundaries.get(key) is not False:
            raise In625ExternalEvidenceActionError(f"IN625 source boundary {key} must remain false")
    return archive_name, archive_sha


def _numerical_candidates(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = manifest.get("selected_tabular_files")
    if not isinstance(raw, list):
        raise In625ExternalEvidenceActionError("IN625 archive selected-file manifest is malformed")
    candidates: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise In625ExternalEvidenceActionError("IN625 selected-file record is malformed")
        path = item.get("path")
        size = item.get("size_bytes")
        digest = item.get("sha256")
        if not isinstance(path, str) or not path or "\\" in path:
            raise In625ExternalEvidenceActionError("IN625 selected-file path is unsafe")
        pure = PurePosixPath(path)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise In625ExternalEvidenceActionError("IN625 selected-file path escapes archive root")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise In625ExternalEvidenceActionError("IN625 selected-file size is invalid")
        digest = _sha(digest, "selected-file sha256")
        if pure.suffix.lower() in {".dat", ".xlsx", ".xls", ".csv", ".tsv"}:
            candidates.append({"path": path, "size_bytes": size, "sha256": digest})
    if not candidates:
        raise In625ExternalEvidenceActionError(
            "verified IN625 archive contains no bounded numerical-source candidate"
        )
    return candidates


def _verify_inputs(
    request_value: Mapping[str, Any],
    *,
    request_path: Path,
    require_unexecuted: bool,
) -> dict[str, Any]:
    request = _validate_request(request_value, request_path=request_path)
    root = request["repository_root"]
    run = request["research_run"]
    if not root.is_dir() or not run.is_dir():
        raise In625ExternalEvidenceActionError("repository_root and research_run must be directories")
    for path, field in (
        (request["source_config"], "source_config"),
        (request["archive_path"], "archive_path"),
        (request["registry"], "registry"),
    ):
        _within(path, root, field=field)
    source_record = _snapshot(request["source_config"])
    if source_record["sha256"] != request["expected_source_config_sha256"]:
        raise In625ExternalEvidenceActionError("source config bytes differ from request-pinned SHA-256")
    source_config = _load_json_file(request["source_config"], field="source_config")
    archive_name, configured_archive_sha = _source_policy(source_config)
    if configured_archive_sha != request["expected_archive_sha256"]:
        raise In625ExternalEvidenceActionError("request archive SHA differs from repository source policy")
    if request["archive_path"].name != archive_name:
        raise In625ExternalEvidenceActionError("archive path basename differs from source policy")
    archive_record = _snapshot(request["archive_path"])
    if archive_record["sha256"] != request["expected_archive_sha256"]:
        raise In625ExternalEvidenceActionError("external archive bytes differ from request-pinned SHA-256")
    archive_manifest = inspect_verified_in625_dataset_archive(
        config=source_config,
        archive_path=request["archive_path"],
        selected_output_dir=None,
    )
    archive_block = archive_manifest.get("archive")
    if (
        not isinstance(archive_block, Mapping)
        or archive_block.get("sha256") != configured_archive_sha
        or archive_block.get("sha256_previously_pinned") is not True
    ):
        raise In625ExternalEvidenceActionError("live archive inspection lost the repository SHA pin")
    candidates = _numerical_candidates(archive_manifest)

    registry = load_action_registry(request["registry"], repository_root=root)
    if registry.get("domain") != EXPECTED_REGISTRY_DOMAIN:
        raise In625ExternalEvidenceActionError("IN625 execution registry domain drifted")
    if registry.get("registry_sha256") != request["expected_registry_sha256"]:
        raise In625ExternalEvidenceActionError("execution registry bytes differ from request pin")
    contract = describe_action(registry, ACTION_TYPE)
    binding = contract.get("binding")
    if (
        contract.get("version") != ACTION_VERSION
        or contract.get("availability") != "available"
        or contract.get("category") != "external_evidence_search"
        or contract.get("cost_units") != COST_UNITS
        or not isinstance(binding, Mapping)
        or binding.get("kind") != "source_script"
        or binding.get("path") != EXPECTED_BINDING_PATH
        or _REGISTERED_OUTCOME not in contract.get("allowed_outcomes", [])
    ):
        raise In625ExternalEvidenceActionError("registered IN625 external-evidence contract drifted")

    state = load_research_state(run)
    if state.get("status") != "active":
        raise In625ExternalEvidenceActionError("research run is not active")
    actions = state.get("actions")
    if not isinstance(actions, list):
        raise In625ExternalEvidenceActionError("research action ledger is malformed")
    prior = [
        item
        for item in actions
        if isinstance(item, Mapping) and item.get("action_type") == ACTION_TYPE
    ]
    if require_unexecuted and prior:
        raise In625ExternalEvidenceActionError(
            "registered IN625 external-evidence action may execute only once per research run"
        )
    if require_unexecuted:
        budget = state.get("budget")
        if (
            not isinstance(budget, Mapping)
            or int(budget.get("actions_remaining", 0)) <= 0
            or int(budget.get("cost_units_remaining", 0)) < COST_UNITS
        ):
            raise In625ExternalEvidenceActionError("research budget cannot fund external-evidence registration")
    return {
        "request": request,
        "source_record": source_record,
        "archive_record": archive_record,
        "archive_manifest": archive_manifest,
        "numerical_candidates": candidates,
        "registry": registry,
        "contract": contract,
        "state": state,
    }


def execute_in625_external_evidence_action_preparsed(
    request_value: Mapping[str, Any],
    *,
    request_path: str | Path,
    request_record: Mapping[str, Any],
) -> dict[str, Any]:
    pinned_path = Path(request_path).expanduser().resolve(strict=True)
    if set(request_record) != {"path", "bytes", "sha256"} or request_record.get("path") != str(pinned_path):
        raise In625ExternalEvidenceActionError("pinned execution request record is malformed")
    _sha(request_record.get("sha256"), "request_record.sha256")
    preflight = _verify_inputs(request_value, request_path=pinned_path, require_unexecuted=True)
    request = preflight["request"]
    run = request["research_run"]
    action_id = request["action_id"]
    action_directory = run / "actions" / action_id
    if action_directory.exists():
        raise FileExistsError(f"action output already exists: {action_directory}")
    started = _utc_now()
    selected = list(preflight["numerical_candidates"])
    evidence_payload = {
        "schema_version": "1.0",
        "source_id": EXPECTED_SOURCE_ID,
        "zenodo_record_id": str(EXPECTED_RECORD_ID),
        "archive_sha256": preflight["archive_record"]["sha256"],
        "archive_bytes": preflight["archive_record"]["bytes"],
        "archive_manifest_sha256": preflight["archive_manifest"]["manifest_sha256"],
        "numerical_candidate_count": len(selected),
        "numerical_candidates": selected,
        "source_provenance_verified": True,
        "real_external_archive_bytes_observed": True,
        "network_access_performed_by_typed_action": False,
        "condition_comparability_established": False,
        "measurement_semantics_interpreted": False,
        "empirical_model_validation_established": False,
        "hypothesis_truth_established": False,
        "scientific_status_changed": False,
    }
    with transactional_output_directory(
        action_directory,
        protected_paths=(pinned_path, request["source_config"], request["archive_path"], request["registry"]),
        recognized_markers=(ACTION_REPORT_FILENAME,),
    ) as staging:
        staged_evidence = staging / OUTPUT_RELATIVE_PATH
        _write_json(staged_evidence, evidence_payload)
        evidence_record = _snapshot(staged_evidence)
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "execution_status": "completed",
            "registered_outcome": _REGISTERED_OUTCOME,
            "action_id": action_id,
            "action_type": ACTION_TYPE,
            "action_version": ACTION_VERSION,
            "cost_units": COST_UNITS,
            "started_at_utc": started,
            "completed_at_utc": _utc_now(),
            "request": dict(request_record),
            "source_config": dict(preflight["source_record"]),
            "external_archive": dict(preflight["archive_record"]),
            "archive_manifest_sha256": preflight["archive_manifest"]["manifest_sha256"],
            "registry": {
                "registry_id": preflight["registry"]["registry_id"],
                "registry_sha256": preflight["registry"]["registry_sha256"],
                "registry_path": preflight["registry"]["registry_path"],
            },
            "verified_evidence": {
                "path": str(action_directory / OUTPUT_RELATIVE_PATH),
                "sha256": evidence_record["sha256"],
                "bytes": evidence_record["bytes"],
                "numerical_candidate_count": len(selected),
            },
            "network_access_performed_by_typed_action": False,
            "physical_experiment_executed": False,
            "empirical_model_validation_established": False,
            "scientific_status_upgrade_authorized": False,
        }
        _write_json(staging / ACTION_REPORT_FILENAME, report)
    report_path = action_directory / ACTION_REPORT_FILENAME
    evidence_path = action_directory / OUTPUT_RELATIVE_PATH
    state = append_action(
        run,
        action_id=action_id,
        action_type=ACTION_TYPE,
        status="completed",
        summary=(
            "Registered one independently SHA-verified real IN625 external source archive and its bounded numerical-source members; no comparability or scientific truth was promoted."
        ),
        cost_units=COST_UNITS,
        artifact_paths=(report_path, evidence_path),
    )
    return {
        "action_report": str(report_path),
        "verified_evidence": str(evidence_path),
        "ledger_sha256": state["ledger_sha256"],
        "execution_status": "completed",
        "registered_outcome": _REGISTERED_OUTCOME,
    }


def verify_in625_external_evidence_action_report_pinned(
    report_path: str | Path,
    *,
    request_value: Mapping[str, Any],
    request_path: str | Path,
    request_record: Mapping[str, Any],
) -> dict[str, Any]:
    pinned_request = Path(request_path).expanduser().resolve(strict=True)
    report_file = Path(report_path).expanduser().resolve(strict=True)
    if request_record.get("path") != str(pinned_request):
        raise In625ExternalEvidenceActionError("verifier request path binding drifted")
    _sha(request_record.get("sha256"), "request_record.sha256")
    if _sha256_file(pinned_request) != request_record.get("sha256"):
        raise In625ExternalEvidenceActionError("execution request bytes changed after execution")
    verified = _verify_inputs(request_value, request_path=pinned_request, require_unexecuted=False)
    report = _load_json_file(report_file, field="action report")
    request = verified["request"]
    action_id = request["action_id"]
    expected_dir = request["research_run"] / "actions" / action_id
    if report_file != (expected_dir / ACTION_REPORT_FILENAME).resolve(strict=True):
        raise In625ExternalEvidenceActionError("action report path differs from ledger action directory")
    if (
        report.get("schema_version") != REPORT_SCHEMA_VERSION
        or report.get("execution_status") != "completed"
        or report.get("registered_outcome") != _REGISTERED_OUTCOME
        or report.get("action_id") != action_id
        or report.get("action_type") != ACTION_TYPE
        or report.get("action_version") != ACTION_VERSION
        or report.get("cost_units") != COST_UNITS
        or report.get("request") != dict(request_record)
        or report.get("source_config") != verified["source_record"]
        or report.get("external_archive") != verified["archive_record"]
        or report.get("archive_manifest_sha256") != verified["archive_manifest"]["manifest_sha256"]
        or report.get("network_access_performed_by_typed_action") is not False
        or report.get("physical_experiment_executed") is not False
        or report.get("empirical_model_validation_established") is not False
        or report.get("scientific_status_upgrade_authorized") is not False
    ):
        raise In625ExternalEvidenceActionError("IN625 action report semantics or byte bindings drifted")
    evidence_block = report.get("verified_evidence")
    if not isinstance(evidence_block, Mapping):
        raise In625ExternalEvidenceActionError("verified_evidence report binding is malformed")
    evidence_path = Path(str(evidence_block.get("path"))).expanduser().resolve(strict=True)
    if evidence_path != (expected_dir / OUTPUT_RELATIVE_PATH).resolve(strict=True):
        raise In625ExternalEvidenceActionError("verified-evidence output path drifted")
    evidence_record = _snapshot(evidence_path)
    if (
        evidence_block.get("sha256") != evidence_record["sha256"]
        or evidence_block.get("bytes") != evidence_record["bytes"]
        or evidence_block.get("numerical_candidate_count") != len(verified["numerical_candidates"])
    ):
        raise In625ExternalEvidenceActionError("verified-evidence output bytes drifted")
    evidence = _load_json_file(evidence_path, field="verified external evidence")
    if (
        evidence.get("archive_sha256") != verified["archive_record"]["sha256"]
        or evidence.get("archive_manifest_sha256") != verified["archive_manifest"]["manifest_sha256"]
        or evidence.get("numerical_candidates") != verified["numerical_candidates"]
        or evidence.get("source_provenance_verified") is not True
        or evidence.get("condition_comparability_established") is not False
        or evidence.get("measurement_semantics_interpreted") is not False
        or evidence.get("empirical_model_validation_established") is not False
        or evidence.get("hypothesis_truth_established") is not False
        or evidence.get("scientific_status_changed") is not False
    ):
        raise In625ExternalEvidenceActionError("verified external-evidence payload drifted")
    state = load_research_state(request["research_run"])
    actions = [
        item
        for item in state.get("actions", [])
        if isinstance(item, Mapping) and item.get("action_id") == action_id
    ]
    if len(actions) != 1:
        raise In625ExternalEvidenceActionError("research ledger lacks exactly one matching IN625 action")
    ledger_action = actions[0]
    if (
        ledger_action.get("action_type") != ACTION_TYPE
        or ledger_action.get("status") != "completed"
        or ledger_action.get("cost_units") != COST_UNITS
    ):
        raise In625ExternalEvidenceActionError("research ledger IN625 action semantics drifted")
    return {
        "schema_version": "1.0",
        "action_id": action_id,
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "registered_outcome": _REGISTERED_OUTCOME,
        "request_sha256": request_record["sha256"],
        "archive_sha256": verified["archive_record"]["sha256"],
        "archive_manifest_sha256": verified["archive_manifest"]["manifest_sha256"],
        "numerical_candidate_count": len(verified["numerical_candidates"]),
        "source_provenance_verified": True,
        "direct_condition_comparability_established": False,
        "empirical_model_validation_established": False,
        "scientific_status_changed": False,
    }


__all__ = [
    "ACTION_TYPE",
    "ACTION_VERSION",
    "COST_UNITS",
    "In625ExternalEvidenceActionError",
    "execute_in625_external_evidence_action_preparsed",
    "verify_in625_external_evidence_action_report_pinned",
]
