"""Mission-rooted authenticated request compile/verify for NIST structural simulation."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .action_authorization import (
    AUTHORIZATION_POLICY_VERSION,
    assess_current_action_authorization,
)
from .action_registry import describe_action, load_action_registry
from .authorized_execution import EXECUTION_POLICY_VERSION as _BASE_EXECUTION_POLICY_VERSION
from .kernel import LEDGER_FILENAME, ResearchLoopError, load_research_state
from .mission_request_delegation_bridge import (
    MISSION_REQUEST_DELEGATION_BRIDGE_SCHEMA_VERSION,
    authenticate_request_delegation_policy_under_expected_mission_root,
)
from .research_program import build_research_program

ADAPTER_ID = "nist-ambench-process-characterization"
ACTION_TYPE = "nist_structural_design_simulation"
ACTION_VERSION = "1.0"
ACTION_COST_UNITS = 1
REQUEST_SCHEMA_VERSION = "1.0"
MANIFEST_SCHEMA_VERSION = "1.0"
COMPILER_POLICY_VERSION = "1.1"
VERIFIER_POLICY_VERSION = "1.1"
NIST_EXECUTION_POLICY_VERSION = (
    f"{_BASE_EXECUTION_POLICY_VERSION}+nist-structural-1.1"
)
EXPECTED_SPEC_RELATIVE_PATH = (
    "configs/research/nist_ambench_stage1_structural_design_simulation.v1.json"
)


class NistAuthenticatedRequestError(ResearchLoopError):
    """Raised when NIST request authorship/verification cannot remain fail closed."""


def _reject_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise NistAuthenticatedRequestError(
                f"duplicate JSON key is not allowed: {key}"
            )
        out[key] = value
    return out


def _json_bytes(raw: bytes, field: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NistAuthenticatedRequestError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise NistAuthenticatedRequestError(f"{field} root must be an object")
    return value


def _file(value: str | Path, field: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise NistAuthenticatedRequestError(f"{field} does not resolve") from exc
    if not path.is_file():
        raise NistAuthenticatedRequestError(f"{field} must be a file")
    return path


def _directory(value: str | Path, field: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise NistAuthenticatedRequestError(f"{field} does not resolve") from exc
    if not path.is_dir():
        raise NistAuthenticatedRequestError(f"{field} must be a directory")
    return path


def _repo_file(value: str | Path, root: Path, field: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    path = candidate.resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise NistAuthenticatedRequestError(f"{field} escapes repository root") from exc
    if not path.is_file():
        raise NistAuthenticatedRequestError(f"{field} must be a file")
    return path


def _sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _sha(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise NistAuthenticatedRequestError(f"{field} must be lowercase SHA-256 hex")
    return value


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _digest(value: Mapping[str, Any]) -> str:
    return _sha_bytes(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def _research_snapshot(run: Path) -> tuple[dict[str, Any], str]:
    ledger = (run / LEDGER_FILENAME).resolve(strict=True)
    before = ledger.read_bytes()
    state = load_research_state(run)
    after = ledger.read_bytes()
    if before != after:
        raise NistAuthenticatedRequestError("research ledger changed during snapshot")
    digest = _sha_bytes(after)
    if state.get("ledger_sha256") != digest:
        raise NistAuthenticatedRequestError("research ledger SHA binding drifted")
    return state, digest


def _authenticate(
    *,
    root: Path,
    mission: Path,
    expected_mission_sha256: str,
    policy: Path,
    policy_id: str,
) -> tuple[str, str, dict[str, Any]]:
    mission_bytes = mission.read_bytes()
    mission_sha = _sha_bytes(mission_bytes)
    if mission_sha != _sha(expected_mission_sha256, "expected_mission_sha256"):
        raise NistAuthenticatedRequestError(
            "mission bytes do not match supplied trust root"
        )
    mission_value = _json_bytes(mission_bytes, "research mission")
    autonomy = mission_value.get("autonomy_policy")
    if (
        not isinstance(autonomy, Mapping)
        or autonomy.get("typed_computational_actions") != "explicit_request"
    ):
        raise NistAuthenticatedRequestError(
            "NIST machine request requires typed_computational_actions=explicit_request"
        )
    program = build_research_program(mission, repository_root=root)
    policy_bytes = policy.read_bytes()
    policy_sha = _sha_bytes(policy_bytes)
    report = authenticate_request_delegation_policy_under_expected_mission_root(
        mission_bytes=mission_bytes,
        expected_mission_sha256=mission_sha,
        program_state=program,
        policy_id=policy_id,
        request_delegation_policy_bytes=policy_bytes,
    )
    if report.get("schema_version") != MISSION_REQUEST_DELEGATION_BRIDGE_SCHEMA_VERSION:
        raise NistAuthenticatedRequestError("delegation bridge schema drifted")
    if report.get("request_delegation_policy_sha256") != policy_sha:
        raise NistAuthenticatedRequestError("delegation policy byte binding drifted")
    normalized = report.get("normalized_request_delegation_policy")
    if not isinstance(normalized, dict) or normalized.get("adapter_id") != ADAPTER_ID:
        raise NistAuthenticatedRequestError("delegation policy adapter drifted")
    allowed = normalized.get("allowed_actions")
    matches = (
        [
            item
            for item in allowed
            if isinstance(item, Mapping)
            and item.get("action_type") == ACTION_TYPE
            and item.get("action_version") == ACTION_VERSION
        ]
        if isinstance(allowed, list)
        else []
    )
    if (
        len(matches) != 1
        or matches[0].get("max_cost_units") != ACTION_COST_UNITS
    ):
        raise NistAuthenticatedRequestError(
            "delegation policy does not bind exact NIST action"
        )
    if normalized.get("max_cost_units_per_request") != ACTION_COST_UNITS:
        raise NistAuthenticatedRequestError("delegation policy cost ceiling drifted")
    for field in (
        "network_access",
        "physical_experiment_execution",
        "generic_command_execution",
    ):
        if normalized.get(field) is not False:
            raise NistAuthenticatedRequestError(f"delegation policy widened {field}")
    return mission_sha, policy_sha, normalized


def _current_selection(
    root: Path,
    run: Path,
    registry_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    authorization = assess_current_action_authorization(
        ADAPTER_ID,
        repository_root=root,
        research_run=run,
        action_registry_path=registry_path,
    )
    if (
        authorization.get("authorization_status")
        != "ready_for_explicit_execution_request"
    ):
        raise NistAuthenticatedRequestError(
            "current NIST state is not request-authorizable"
        )
    selected = authorization.get("selected_action")
    contract = authorization.get("execution_contract")
    if not isinstance(selected, Mapping) or not isinstance(contract, Mapping):
        raise NistAuthenticatedRequestError(
            "NIST authorization omitted action contract"
        )
    expected = {
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "availability": "available",
        "cost_units": ACTION_COST_UNITS,
    }
    for key, value in expected.items():
        if selected.get(key) != value:
            raise NistAuthenticatedRequestError(
                f"NIST selected action drifted on {key}"
            )
    if (
        contract.get("action_type") != ACTION_TYPE
        or contract.get("action_version") != ACTION_VERSION
        or contract.get("cost_units") != ACTION_COST_UNITS
    ):
        raise NistAuthenticatedRequestError(
            "NIST authorization execution contract drifted"
        )
    return dict(selected), dict(contract)


def _action_id(
    *,
    mission_sha: str,
    policy_sha: str,
    registry_sha: str,
    ledger_sha: str,
    selected_sha: str,
    spec_sha: str,
) -> str:
    digest = _digest(
        {
            "adapter_id": ADAPTER_ID,
            "action_type": ACTION_TYPE,
            "action_version": ACTION_VERSION,
            "mission_sha256": mission_sha,
            "policy_sha256": policy_sha,
            "registry_sha256": registry_sha,
            "ledger_sha256": ledger_sha,
            "selected_action_sha256": selected_sha,
            "simulation_spec_sha256": spec_sha,
            "authorization_policy_version": AUTHORIZATION_POLICY_VERSION,
            "execution_policy_version": NIST_EXECUTION_POLICY_VERSION,
        }
    )
    return f"delegated-{digest[:40]}"


def compile_nist_authenticated_request(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    policy_id: str,
    request_delegation_policy_path: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    simulation_spec_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    root = _directory(repository_root, "repository_root")
    mission = _file(mission_path, "mission_path")
    policy = _file(
        request_delegation_policy_path,
        "request_delegation_policy_path",
    )
    run = _directory(research_run, "research_run")
    registry_path = _repo_file(action_registry_path, root, "action_registry_path")
    spec = _repo_file(simulation_spec_path, root, "simulation_spec_path")
    expected_spec = (root / EXPECTED_SPEC_RELATIVE_PATH).resolve(strict=True)
    if spec != expected_spec:
        raise NistAuthenticatedRequestError(
            "only the frozen NIST Stage 1 spec may be bound"
        )
    mission_sha, policy_sha, _ = _authenticate(
        root=root,
        mission=mission,
        expected_mission_sha256=expected_mission_sha256,
        policy=policy,
        policy_id=policy_id,
    )
    registry = load_action_registry(registry_path, repository_root=root)
    contract = describe_action(registry, ACTION_TYPE)
    if (
        contract.get("version") != ACTION_VERSION
        or contract.get("cost_units") != ACTION_COST_UNITS
    ):
        raise NistAuthenticatedRequestError("NIST registry action contract drifted")
    selected, auth_contract = _current_selection(root, run, registry_path)
    state, ledger_sha = _research_snapshot(run)
    selected_sha = _digest(selected)
    spec_sha = _sha_file(spec)
    action_id = _action_id(
        mission_sha=mission_sha,
        policy_sha=policy_sha,
        registry_sha=registry["registry_sha256"],
        ledger_sha=ledger_sha,
        selected_sha=selected_sha,
        spec_sha=spec_sha,
    )
    if any(item.get("action_id") == action_id for item in state["actions"]):
        raise NistAuthenticatedRequestError(
            "deterministic NIST action_id already exists"
        )
    request = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "action_id": action_id,
        "action_type": ACTION_TYPE,
        "research_run": str(run),
        "simulation_spec": str(spec),
        "expected_simulation_spec_sha256": spec_sha,
        "registry": str(registry_path),
        "repository_root": str(root),
        "expected_registry_sha256": registry["registry_sha256"],
    }
    request_bytes = _canonical_bytes(request)
    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise NistAuthenticatedRequestError(f"output_dir already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    final_request = output / "execution_request.json"
    final_manifest = output / "authenticated_request_manifest.json"
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "compiler_policy_version": COMPILER_POLICY_VERSION,
        "compilation_status": "bounded_nist_machine_request_compiled_not_executed",
        "adapter_id": ADAPTER_ID,
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "mission_binding": {"path": str(mission), "sha256": mission_sha},
        "policy_binding": {
            "path": str(policy),
            "policy_id": policy_id,
            "sha256": policy_sha,
        },
        "registry_binding": {
            "path": str(registry_path),
            "registry_id": registry["registry_id"],
            "registry_sha256": registry["registry_sha256"],
            "file_sha256": _sha_file(registry_path),
        },
        "research_binding": {
            "research_run": str(run),
            "ledger_sha256": ledger_sha,
        },
        "selected_action_binding": {"sha256": selected_sha},
        "simulation_spec_binding": {
            "path": str(spec),
            "sha256": spec_sha,
        },
        "request_binding": {
            "path": str(final_request),
            "sha256": _sha_bytes(request_bytes),
            "bytes": len(request_bytes),
        },
        "downstream_contract": {
            "authorization_policy_version": AUTHORIZATION_POLICY_VERSION,
            "execution_policy_version": NIST_EXECUTION_POLICY_VERSION,
            "authorized_registry_path": auth_contract["registry_path"],
        },
        "authority_boundary": {
            "request_authorship_eligible": True,
            "execution_authorized": False,
            "network_access_authorized": False,
            "physical_experiment_execution_authorized": False,
            "generic_command_execution_authorized": False,
            "model_fitting_authorized": False,
            "scientific_evidence_upgraded": False,
            "physical_evidence_requirement_satisfied": False,
        },
    }
    try:
        (staging / "execution_request.json").write_bytes(request_bytes)
        (staging / "authenticated_request_manifest.json").write_bytes(
            _canonical_bytes(manifest)
        )
        os.replace(staging, output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        **manifest,
        "manifest_binding": {
            "path": str(final_manifest),
            "sha256": _sha_file(final_manifest),
        },
    }


def verify_nist_authenticated_request(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    policy_id: str,
    request_delegation_policy_path: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
    manifest_path: str | Path,
) -> dict[str, Any]:
    root = _directory(repository_root, "repository_root")
    mission = _file(mission_path, "mission_path")
    policy = _file(
        request_delegation_policy_path,
        "request_delegation_policy_path",
    )
    run = _directory(research_run, "research_run")
    registry_path = _repo_file(action_registry_path, root, "action_registry_path")
    request_file = _file(request_path, "request_path")
    manifest_file = _file(manifest_path, "manifest_path")
    mission_sha, policy_sha, _ = _authenticate(
        root=root,
        mission=mission,
        expected_mission_sha256=expected_mission_sha256,
        policy=policy,
        policy_id=policy_id,
    )
    request_raw = request_file.read_bytes()
    request = _json_bytes(request_raw, "execution request")
    expected_keys = {
        "schema_version",
        "action_id",
        "action_type",
        "research_run",
        "simulation_spec",
        "expected_simulation_spec_sha256",
        "registry",
        "repository_root",
        "expected_registry_sha256",
    }
    if set(request) != expected_keys:
        raise NistAuthenticatedRequestError("NIST request field set drifted")
    if (
        request["schema_version"] != REQUEST_SCHEMA_VERSION
        or request["action_type"] != ACTION_TYPE
    ):
        raise NistAuthenticatedRequestError("NIST request schema/type drifted")
    if _directory(request["research_run"], "request research_run") != run:
        raise NistAuthenticatedRequestError("NIST request research_run drifted")
    if _directory(request["repository_root"], "request repository_root") != root:
        raise NistAuthenticatedRequestError("NIST request repository_root drifted")
    if _file(request["registry"], "request registry") != registry_path:
        raise NistAuthenticatedRequestError("NIST request registry path drifted")
    spec = _repo_file(request["simulation_spec"], root, "request simulation_spec")
    if spec != (root / EXPECTED_SPEC_RELATIVE_PATH).resolve(strict=True):
        raise NistAuthenticatedRequestError(
            "NIST request simulation spec path drifted"
        )
    spec_sha = _sha_file(spec)
    if request["expected_simulation_spec_sha256"] != spec_sha:
        raise NistAuthenticatedRequestError(
            "NIST request simulation spec SHA drifted"
        )
    registry = load_action_registry(registry_path, repository_root=root)
    if request["expected_registry_sha256"] != registry["registry_sha256"]:
        raise NistAuthenticatedRequestError("NIST request registry SHA drifted")
    selected, auth_contract = _current_selection(root, run, registry_path)
    state, ledger_sha = _research_snapshot(run)
    selected_sha = _digest(selected)
    expected_id = _action_id(
        mission_sha=mission_sha,
        policy_sha=policy_sha,
        registry_sha=registry["registry_sha256"],
        ledger_sha=ledger_sha,
        selected_sha=selected_sha,
        spec_sha=spec_sha,
    )
    if request["action_id"] != expected_id:
        raise NistAuthenticatedRequestError(
            "NIST request deterministic action_id drifted"
        )
    if any(item.get("action_id") == expected_id for item in state["actions"]):
        raise NistAuthenticatedRequestError(
            "NIST request action_id already exists in ledger"
        )

    manifest = _json_bytes(manifest_file.read_bytes(), "NIST request manifest")
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise NistAuthenticatedRequestError("NIST manifest schema drifted")
    if manifest.get("compiler_policy_version") != COMPILER_POLICY_VERSION:
        raise NistAuthenticatedRequestError("NIST compiler policy drifted")
    if (
        manifest.get("adapter_id") != ADAPTER_ID
        or manifest.get("action_type") != ACTION_TYPE
    ):
        raise NistAuthenticatedRequestError("NIST manifest adapter/action drifted")
    if manifest.get("action_version") != ACTION_VERSION:
        raise NistAuthenticatedRequestError("NIST manifest version drifted")
    if manifest.get("mission_binding") != {
        "path": str(mission),
        "sha256": mission_sha,
    }:
        raise NistAuthenticatedRequestError("NIST manifest mission binding drifted")
    if manifest.get("policy_binding") != {
        "path": str(policy),
        "policy_id": policy_id,
        "sha256": policy_sha,
    }:
        raise NistAuthenticatedRequestError("NIST manifest policy binding drifted")
    rb = manifest.get("request_binding")
    expected_request_binding = {
        "path": str(request_file),
        "sha256": _sha_bytes(request_raw),
        "bytes": len(request_raw),
    }
    if rb != expected_request_binding:
        raise NistAuthenticatedRequestError("NIST manifest request binding drifted")
    if manifest.get("simulation_spec_binding") != {
        "path": str(spec),
        "sha256": spec_sha,
    }:
        raise NistAuthenticatedRequestError(
            "NIST manifest simulation spec binding drifted"
        )
    boundary = manifest.get("authority_boundary")
    expected_boundary = {
        "request_authorship_eligible": True,
        "execution_authorized": False,
        "network_access_authorized": False,
        "physical_experiment_execution_authorized": False,
        "generic_command_execution_authorized": False,
        "model_fitting_authorized": False,
        "scientific_evidence_upgraded": False,
        "physical_evidence_requirement_satisfied": False,
    }
    if boundary != expected_boundary:
        raise NistAuthenticatedRequestError(
            "NIST manifest widened authority boundary"
        )
    downstream = manifest.get("downstream_contract")
    if downstream != {
        "authorization_policy_version": AUTHORIZATION_POLICY_VERSION,
        "execution_policy_version": NIST_EXECUTION_POLICY_VERSION,
        "authorized_registry_path": auth_contract["registry_path"],
    }:
        raise NistAuthenticatedRequestError(
            "NIST manifest downstream contract drifted"
        )
    if manifest.get("selected_action_binding") != {"sha256": selected_sha}:
        raise NistAuthenticatedRequestError(
            "NIST selected-action manifest binding drifted"
        )
    registry_binding = manifest.get("registry_binding")
    expected_registry_binding = {
        "path": str(registry_path),
        "registry_id": registry["registry_id"],
        "registry_sha256": registry["registry_sha256"],
        "file_sha256": _sha_file(registry_path),
    }
    if registry_binding != expected_registry_binding:
        raise NistAuthenticatedRequestError(
            "NIST manifest registry binding drifted"
        )
    if manifest.get("research_binding") != {
        "research_run": str(run),
        "ledger_sha256": ledger_sha,
    }:
        raise NistAuthenticatedRequestError(
            "NIST manifest research binding drifted"
        )
    return {
        "schema_version": "1.0",
        "verifier_policy_version": VERIFIER_POLICY_VERSION,
        "verification_status": (
            "bounded_nist_request_verified_eligible_for_existing_typed_executor"
        ),
        "adapter_id": ADAPTER_ID,
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "cost_units": ACTION_COST_UNITS,
        "execution_policy_version": NIST_EXECUTION_POLICY_VERSION,
        "request_binding": expected_request_binding,
        "mission_sha256": mission_sha,
        "policy_sha256": policy_sha,
        "ledger_sha256": ledger_sha,
        "simulation_spec_sha256": spec_sha,
        "execution_authorized": False,
        "network_access_authorized": False,
        "physical_experiment_execution_authorized": False,
        "generic_command_execution_authorized": False,
        "model_fitting_authorized": False,
        "scientific_evidence_upgraded": False,
        "physical_evidence_requirement_satisfied": False,
    }


__all__ = [
    "NIST_EXECUTION_POLICY_VERSION",
    "NistAuthenticatedRequestError",
    "compile_nist_authenticated_request",
    "verify_nist_authenticated_request",
]
