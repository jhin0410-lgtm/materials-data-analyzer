"""Independent pre-execution verifier for the IN625 external-evidence adapter."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .action_registry import describe_action, load_action_registry
from .in625_external_evidence_action import ACTION_TYPE, ACTION_VERSION, COST_UNITS
from .in625_zenodo_live_evidence import inspect_verified_in625_dataset_archive
from .kernel import LEDGER_FILENAME, ResearchLoopError, load_research_state

ADAPTER_ID = "in625-external-evidence"
REGISTRY_DOMAIN = "in625_external_empirical_evidence"
EXPECTED_SOURCE_ID = "zenodo-20503603-in625-lpbf-publication-supplement"
EXPECTED_RECORD_ID = 20503603
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


class In625ExecutionVerifierError(ResearchLoopError):
    """Raised when independent IN625 execution pins cannot be established exactly."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise In625ExecutionVerifierError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_json(path: Path, *, field: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise In625ExecutionVerifierError(f"{field} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise In625ExecutionVerifierError(f"{field} root must be an object")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise In625ExecutionVerifierError(f"{field} must be canonical lowercase SHA-256")
    return value


def _resolve(raw: object, *, base: Path, field: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise In625ExecutionVerifierError(f"{field} must be a path string")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = base / path
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise In625ExecutionVerifierError(f"{field} does not resolve") from exc


def _within(path: Path, root: Path, field: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise In625ExecutionVerifierError(f"{field} escapes repository root") from exc


def _load_request(path: Path) -> dict[str, Any]:
    value = _load_json(path, field="execution request")
    if set(value) != _REQUEST_KEYS:
        raise In625ExecutionVerifierError("typed IN625 execution request field set drifted")
    if value.get("schema_version") != "1.0":
        raise In625ExecutionVerifierError("unsupported typed IN625 execution request schema")
    if value.get("action_type") != ACTION_TYPE or value.get("action_version") != ACTION_VERSION:
        raise In625ExecutionVerifierError("execution request action type/version drifted")
    action_id = value.get("action_id")
    if not isinstance(action_id, str) or not action_id.strip():
        raise In625ExecutionVerifierError("execution request action_id is missing")
    for field in (
        "expected_source_config_sha256",
        "expected_archive_sha256",
        "expected_registry_sha256",
    ):
        _sha(value.get(field), field)
    return value


def _source_archive_sha(config: Mapping[str, Any]) -> str:
    if config.get("source_id") != EXPECTED_SOURCE_ID:
        raise In625ExecutionVerifierError("source config source_id drifted")
    zenodo = config.get("zenodo")
    if not isinstance(zenodo, Mapping) or zenodo.get("record_id") != EXPECTED_RECORD_ID:
        raise In625ExecutionVerifierError("source config Zenodo record identity drifted")
    archive_name = zenodo.get("archive_file")
    files = zenodo.get("files")
    if not isinstance(archive_name, str) or not isinstance(files, Mapping):
        raise In625ExecutionVerifierError("source config archive identity is malformed")
    archive = files.get(archive_name)
    if not isinstance(archive, Mapping):
        raise In625ExecutionVerifierError("source config archive entry is missing")
    return _sha(archive.get("verified_sha256"), "source config archive verified_sha256")


def verify_in625_execution_handoff(
    *,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
) -> dict[str, Any]:
    """Reconstruct all immutable pins required before typed IN625 execution."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    run = Path(research_run).expanduser().resolve(strict=True)
    registry_path = Path(action_registry_path).expanduser().resolve(strict=True)
    request_file = Path(request_path).expanduser().resolve(strict=True)
    request = _load_request(request_file)
    base = request_file.parent
    if _resolve(request.get("repository_root"), base=base, field="repository_root") != root:
        raise In625ExecutionVerifierError("request repository_root differs from verifier context")
    if _resolve(request.get("research_run"), base=base, field="research_run") != run:
        raise In625ExecutionVerifierError("request research_run differs from verifier context")
    if _resolve(request.get("registry"), base=base, field="registry") != registry_path:
        raise In625ExecutionVerifierError("request registry differs from verifier context")

    source_config_path = _resolve(request.get("source_config"), base=base, field="source_config")
    archive_path = _resolve(request.get("archive_path"), base=base, field="archive_path")
    for path, field in ((source_config_path, "source_config"), (archive_path, "archive_path"), (registry_path, "registry")):
        _within(path, root, field)
    source_config_sha = _sha256_file(source_config_path)
    if request.get("expected_source_config_sha256") != source_config_sha:
        raise In625ExecutionVerifierError("source config differs from request-pinned SHA-256")
    source_config = _load_json(source_config_path, field="source config")
    configured_archive_sha = _source_archive_sha(source_config)
    if request.get("expected_archive_sha256") != configured_archive_sha:
        raise In625ExecutionVerifierError("request archive SHA differs from verified source policy")
    archive_sha = _sha256_file(archive_path)
    if archive_sha != configured_archive_sha:
        raise In625ExecutionVerifierError("external archive differs from request/source SHA-256")

    archive_manifest = inspect_verified_in625_dataset_archive(
        config=source_config,
        archive_path=archive_path,
        selected_output_dir=None,
    )
    archive_block = archive_manifest.get("archive")
    selected = archive_manifest.get("selected_tabular_files")
    if (
        not isinstance(archive_block, Mapping)
        or archive_block.get("sha256") != archive_sha
        or archive_block.get("sha256_previously_pinned") is not True
        or not isinstance(selected, list)
    ):
        raise In625ExecutionVerifierError("independent archive inspection lost exact source binding")
    numerical = []
    for item in selected:
        if not isinstance(item, Mapping):
            raise In625ExecutionVerifierError("archive selected-member record is malformed")
        path = item.get("path")
        if isinstance(path, str) and PurePosixPath(path).suffix.lower() in {".dat", ".xlsx", ".xls", ".csv", ".tsv"}:
            numerical.append(item)
    if not numerical:
        raise In625ExecutionVerifierError("verified archive exposes no numerical-source candidate")

    registry = load_action_registry(registry_path, repository_root=root)
    if registry.get("domain") != REGISTRY_DOMAIN:
        raise In625ExecutionVerifierError("IN625 registry domain drifted")
    contract = describe_action(registry, ACTION_TYPE)
    if (
        contract.get("version") != ACTION_VERSION
        or contract.get("availability") != "available"
        or contract.get("category") != "external_evidence_search"
        or contract.get("cost_units") != COST_UNITS
    ):
        raise In625ExecutionVerifierError("IN625 registry action contract drifted")
    registry_sha = str(registry["registry_sha256"])
    if request.get("expected_registry_sha256") != registry_sha:
        raise In625ExecutionVerifierError("request expected_registry_sha256 differs from verified registry")

    state = load_research_state(run)
    if state.get("status") != "active":
        raise In625ExecutionVerifierError("research run is not active")
    ledger = (run / LEDGER_FILENAME).resolve(strict=True)
    ledger_sha = _sha256_file(ledger)
    if state.get("ledger_sha256") != ledger_sha:
        raise In625ExecutionVerifierError("research state ledger SHA differs from current ledger bytes")
    request_sha = _sha256_file(request_file)
    return {
        "schema_version": "1.0",
        "adapter_id": ADAPTER_ID,
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "request_sha256": request_sha,
        "research_ledger_sha256": ledger_sha,
        "registry_sha256": registry_sha,
        "source_config_sha256": source_config_sha,
        "archive_sha256": archive_sha,
        "archive_manifest_sha256": archive_manifest["manifest_sha256"],
        "numerical_candidate_count": len(numerical),
        "authorization_granted": False,
        "execution_performed": False,
        "source_provenance_verified": True,
        "direct_condition_comparability_established": False,
        "scientific_status_upgrade_authorized": False,
    }


__all__ = ["ADAPTER_ID", "In625ExecutionVerifierError", "verify_in625_execution_handoff"]
