"""Compile one bounded machine-authored typed request under authenticated delegation.

The externally supplied expected mission SHA-256 is the trust root.  This module may
make request bytes eligible for later consideration, but it never authenticates the
root supplier, synthesizes operator acknowledgement, executes an action, grants network
or physical-experiment authority, fits a model, or upgrades scientific evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

from . import action_authorization as action_authorization_module
from . import authorized_execution as authorized_execution_module
from . import mission_request_delegation_bridge as delegation_bridge_module
from .action_registry import describe_action, load_action_registry
from .kernel import LEDGER_FILENAME, ResearchLoopError, load_research_state
from .research_program import build_research_program

AUTHENTICATED_REQUEST_MANIFEST_SCHEMA_VERSION = "1.0"
AUTHENTICATED_REQUEST_COMPILER_POLICY_VERSION = "1.0"
_EXPECTED_AUTHORIZATION_POLICY_VERSION = "1.1"
_EXPECTED_EXECUTION_POLICY_VERSION = "1.7"
_EXPECTED_BRIDGE_SCHEMA_VERSION = "1.0"
_REQUEST_SCHEMA_VERSION = "1.0"

# A registry or policy cannot opt a new action into this finite request-authorship set.
_SAFE_ACTIONS: dict[str, dict[str, Any]] = {
    "audit_existing_battery_run": {
        "version": "1.0",
        "category": "diagnostic_audit",
        "cost": 2,
        "request_inputs": ("analysis_run",),
        "registry_inputs": ("run_output",),
        "aliases": {"run_output": "analysis_run"},
        "binding": {"kind": "installed_command", "name": "mda-battery-result-audit", "path": None, "platform": "cross_platform"},
    },
    "target_reference_sensitivity": {
        "version": "1.0",
        "category": "target_semantics_audit",
        "cost": 4,
        "request_inputs": ("analysis_run",),
        "registry_inputs": ("analysis_run", "research_run"),
        "aliases": {"analysis_run": "analysis_run"},
        "binding": {"kind": "installed_command", "name": "mda-research-loop", "path": None, "platform": "cross_platform"},
    },
    "protocol_stratification": {
        "version": "1.0",
        "category": "hypothesis_discrimination",
        "cost": 5,
        "request_inputs": ("import_run", "analysis_run"),
        "registry_inputs": ("import_run", "analysis_run", "research_run"),
        "aliases": {"import_run": "import_run", "analysis_run": "analysis_run"},
        "binding": {"kind": "installed_command", "name": "mda-research-loop", "path": None, "platform": "cross_platform"},
    },
    "external_data_requirement_generation": {
        "version": "1.0",
        "category": "next_evidence_planning",
        "cost": 2,
        "request_inputs": (),
        "registry_inputs": ("research_state", "unresolved_blocker_reports"),
        "aliases": {},
        "binding": {"kind": "source_script", "name": None, "path": "scripts/run_nasa_external_data_requirement_action.py", "platform": "cross_platform"},
    },
}
_HARD_DENIED = {
    "run_fixed_battery_intelligence",
    "import_official_nasa_archive",
    "close_reviewed_nasa_audit",
    "hierarchical_state_space_baseline",
    "feature_family_ablation",
    "selective_prediction_abstention",
    "source_cohort_leave_one_out",
}


class AuthenticatedRequestCompilerError(ResearchLoopError):
    """Raised when bounded request authorship cannot remain fail-closed."""


class AuthenticatedRequestInputBindingRequired(AuthenticatedRequestCompilerError):
    """Raised instead of guessing an action-specific input path."""


def _duplicate_safe_json(raw: bytes, field: str) -> dict[str, Any]:
    def reject(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise AuthenticatedRequestCompilerError(f"duplicate JSON key is not allowed: {key}")
            out[key] = value
        return out

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthenticatedRequestCompilerError(f"{field} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise AuthenticatedRequestCompilerError(f"{field} root must be an object")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise AuthenticatedRequestCompilerError(f"{field} must be non-empty text without surrounding whitespace")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        raise AuthenticatedRequestCompilerError(f"{field} must be lowercase SHA-256 hex")
    return text


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AuthenticatedRequestCompilerError(f"{field} must be a positive integer")
    return value


def _file(value: str | Path, field: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise AuthenticatedRequestCompilerError(f"{field} does not resolve") from exc
    if not path.is_file():
        raise AuthenticatedRequestCompilerError(f"{field} must be a file")
    return path


def _directory(value: str | Path, field: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise AuthenticatedRequestCompilerError(f"{field} does not resolve") from exc
    if not path.is_dir():
        raise AuthenticatedRequestCompilerError(f"{field} must be a directory")
    return path


def _repo_file(value: object, root: Path, field: str) -> Path:
    if isinstance(value, Path):
        candidate = value.expanduser()
    else:
        candidate = Path(_text(value, field)).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    path = candidate.resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise AuthenticatedRequestCompilerError(f"{field} escapes repository_root") from exc
    if not path.is_file():
        raise AuthenticatedRequestCompilerError(f"{field} must resolve to a file")
    return path


def _raw_snapshot(path: Path, field: str) -> tuple[dict[str, Any], bytes, str]:
    raw = path.read_bytes()
    if not raw:
        raise AuthenticatedRequestCompilerError(f"{field} must not be empty")
    return _duplicate_safe_json(raw, field), raw, hashlib.sha256(raw).hexdigest()


def _registry_snapshot(path: Path, root: Path) -> tuple[dict[str, Any], str]:
    before = path.read_bytes()
    registry = load_action_registry(path, repository_root=root)
    after = path.read_bytes()
    if before != after:
        raise AuthenticatedRequestCompilerError("registry changed while being validated")
    return registry, hashlib.sha256(after).hexdigest()


def _research_snapshot(run: Path) -> tuple[dict[str, Any], str]:
    ledger = (run / LEDGER_FILENAME).resolve(strict=True)
    before = ledger.read_bytes()
    state = load_research_state(run)
    after = ledger.read_bytes()
    if before != after:
        raise AuthenticatedRequestCompilerError("research ledger changed while being validated")
    raw_sha = hashlib.sha256(after).hexdigest()
    if _sha(state.get("ledger_sha256"), "research_state.ledger_sha256") != raw_sha:
        raise AuthenticatedRequestCompilerError("research ledger raw bytes do not match verified ledger_sha256")
    if not isinstance(state.get("actions"), list):
        raise AuthenticatedRequestCompilerError("research state actions are malformed")
    return state, raw_sha


def _canonical_digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _validate_downstream_versions() -> None:
    if action_authorization_module.AUTHORIZATION_POLICY_VERSION != _EXPECTED_AUTHORIZATION_POLICY_VERSION:
        raise AuthenticatedRequestCompilerError("downstream action-authorization policy version drifted")
    if authorized_execution_module.EXECUTION_POLICY_VERSION != _EXPECTED_EXECUTION_POLICY_VERSION:
        raise AuthenticatedRequestCompilerError("downstream typed-executor policy version drifted")


def _authenticate(
    *, root: Path, mission_file: Path, policy_file: Path,
    expected_mission_sha256: str, policy_id: str, adapter_id: str,
) -> tuple[bytes, str, bytes, str, dict[str, Any]]:
    mission_value, mission_bytes, mission_sha = _raw_snapshot(mission_file, "research mission")
    expected = _sha(expected_mission_sha256, "expected_mission_sha256")
    if mission_sha != expected:
        raise AuthenticatedRequestCompilerError("mission bytes do not match supplied expected mission SHA")
    autonomy = mission_value.get("autonomy_policy")
    if not isinstance(autonomy, Mapping) or autonomy.get("typed_computational_actions") != "explicit_request":
        raise AuthenticatedRequestCompilerError("machine request compilation requires typed_computational_actions=explicit_request")
    program = build_research_program(mission_file, repository_root=root)
    if mission_file.read_bytes() != mission_bytes:
        raise AuthenticatedRequestCompilerError("mission bytes changed while building program projection")
    _, policy_bytes, policy_sha = _raw_snapshot(policy_file, "request-delegation policy")
    if delegation_bridge_module.MISSION_REQUEST_DELEGATION_BRIDGE_SCHEMA_VERSION != _EXPECTED_BRIDGE_SCHEMA_VERSION:
        raise AuthenticatedRequestCompilerError("mission request-delegation bridge version drifted")
    report = delegation_bridge_module.authenticate_request_delegation_policy_under_expected_mission_root(
        mission_bytes=mission_bytes,
        expected_mission_sha256=expected,
        program_state=program,
        policy_id=_text(policy_id, "policy_id"),
        request_delegation_policy_bytes=policy_bytes,
    )
    if report.get("schema_version") != _EXPECTED_BRIDGE_SCHEMA_VERSION or report.get("request_delegation_policy_sha256") != policy_sha:
        raise AuthenticatedRequestCompilerError("delegation bridge did not authenticate exact policy bytes")
    for field in (
        "expected_mission_root_supplier_authenticated", "human_authorship_authenticated",
        "machine_request_authorship_authorized", "execution_authorized", "network_access_authorized",
        "physical_experiment_execution_authorized", "generic_command_execution_authorized",
        "scientific_evidence_upgraded", "scientific_status_changed", "empirical_authority_granted",
        "positive_closeout_granted",
    ):
        if report.get(field) is not False:
            raise AuthenticatedRequestCompilerError(f"delegation bridge widened authority: {field}")
    policy = report.get("normalized_request_delegation_policy")
    if not isinstance(policy, dict) or policy.get("adapter_id") != adapter_id:
        raise AuthenticatedRequestCompilerError("authenticated delegation policy adapter mismatch")
    return mission_bytes, mission_sha, policy_bytes, policy_sha, policy


def _input_names(contract: Mapping[str, Any]) -> tuple[str, ...]:
    values = contract.get("required_inputs")
    if not isinstance(values, list):
        raise AuthenticatedRequestCompilerError("registry required_inputs are malformed")
    names: list[str] = []
    for item in values:
        if not isinstance(item, Mapping):
            raise AuthenticatedRequestCompilerError("registry input record is malformed")
        names.append(_text(item.get("name"), "registry input name"))
    return tuple(names)


def _policy_action(policy: Mapping[str, Any], action_type: str, version: str) -> Mapping[str, Any]:
    values = policy.get("allowed_actions")
    matches = [item for item in values if isinstance(item, Mapping) and item.get("action_type") == action_type and item.get("action_version") == version] if isinstance(values, list) else []
    if len(matches) != 1:
        raise AuthenticatedRequestCompilerError("authenticated policy does not delegate exact action/version")
    return matches[0]


def _verify_selected(authorization: Mapping[str, Any], root: Path, policy: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any], Path, Mapping[str, Any], str]:
    if authorization.get("authorization_status") != "ready_for_explicit_execution_request":
        raise AuthenticatedRequestCompilerError("current planner/authorization state is not ready for an explicit request")
    selected = authorization.get("selected_action")
    auth_contract = authorization.get("execution_contract")
    if not isinstance(selected, Mapping) or not isinstance(auth_contract, Mapping):
        raise AuthenticatedRequestCompilerError("authorization omitted selected action contract")
    action_type = _text(selected.get("action_type"), "selected_action.action_type")
    version = _text(selected.get("action_version"), "selected_action.action_version")
    if action_type in _HARD_DENIED:
        raise AuthenticatedRequestCompilerError(f"action is hard-denied for machine request authorship: {action_type}")
    spec = _SAFE_ACTIONS.get(action_type)
    if spec is None or version != spec["version"]:
        raise AuthenticatedRequestCompilerError("selected action/version is outside hardcoded audited request allowlist")
    if selected.get("availability") != "available" or selected.get("cost_units") != spec["cost"]:
        raise AuthenticatedRequestCompilerError("selected action availability or cost drifted")
    execution_path = _repo_file(selected.get("execution_registry_path"), root, "selected execution registry")
    if _repo_file(auth_contract.get("registry_path"), root, "authorization execution registry") != execution_path:
        raise AuthenticatedRequestCompilerError("planner selection and authorization disagree on execution registry")
    registry, raw_sha = _registry_snapshot(execution_path, root)
    registry_id = _text(selected.get("execution_registry_id"), "selected registry id")
    registry_sha = _sha(selected.get("execution_registry_sha256"), "selected registry sha")
    if registry["registry_id"] != registry_id or registry["registry_sha256"] != registry_sha:
        raise AuthenticatedRequestCompilerError("selected execution registry identity drifted")
    if auth_contract.get("registry_id") != registry_id or auth_contract.get("registry_sha256") != registry_sha:
        raise AuthenticatedRequestCompilerError("authorization execution registry identity drifted")
    contract = describe_action(registry, action_type)
    expected = {"version": version, "availability": "available", "category": spec["category"], "cost_units": spec["cost"], "binding": spec["binding"]}
    for key, value in expected.items():
        if contract.get(key) != value:
            raise AuthenticatedRequestCompilerError(f"execution registry contract drifted on {key}")
    if auth_contract.get("category") != spec["category"] or auth_contract.get("cost_units") != spec["cost"] or auth_contract.get("binding") != spec["binding"]:
        raise AuthenticatedRequestCompilerError("authorization contract drifted")
    if _input_names(contract) != spec["registry_inputs"]:
        raise AuthenticatedRequestCompilerError("execution registry required-input contract drifted")
    if not isinstance(contract.get("verifier_checks"), list) or not contract["verifier_checks"]:
        raise AuthenticatedRequestCompilerError("safe typed action must retain verifier checks")
    delegated = _policy_action(policy, action_type, version)
    if spec["cost"] > _positive_int(policy.get("max_cost_units_per_request"), "policy max cost") or spec["cost"] > _positive_int(delegated.get("max_cost_units"), "policy action max cost"):
        raise AuthenticatedRequestCompilerError("selected action exceeds authenticated delegation cost")
    return action_type, version, spec, registry, execution_path, selected, raw_sha


def _resolve_inputs(spec: Mapping[str, Any], supplied: Mapping[str, str | Path] | None) -> dict[str, str]:
    required = tuple(spec["request_inputs"])
    values = dict(supplied or {})
    missing = sorted(set(required) - set(values))
    extra = sorted(set(values) - set(required))
    if missing:
        raise AuthenticatedRequestInputBindingRequired("explicit action input binding required; compiler will not guess: " + ", ".join(missing))
    if extra:
        raise AuthenticatedRequestCompilerError("action_inputs contains fields outside audited typed request contract: " + ", ".join(extra))
    return {name: str(_directory(values[name], f"action_inputs.{name}")) for name in required}


def _action_id(*, adapter: str, mission_sha: str, policy_sha: str, planning: Mapping[str, Any], planning_raw: str, execution: Mapping[str, Any], execution_raw: str, ledger_sha: str, selected_sha: str, action_type: str, version: str, inputs: Mapping[str, str]) -> str:
    digest = _canonical_digest({
        "adapter_id": adapter,
        "mission_sha256": mission_sha,
        "policy_sha256": policy_sha,
        "planning_registry_id": planning["registry_id"],
        "planning_registry_sha256": planning["registry_sha256"],
        "planning_registry_file_sha256": planning_raw,
        "execution_registry_id": execution["registry_id"],
        "execution_registry_sha256": execution["registry_sha256"],
        "execution_registry_file_sha256": execution_raw,
        "ledger_sha256": ledger_sha,
        "ledger_file_sha256": ledger_sha,
        "selected_action_sha256": selected_sha,
        "action_type": action_type,
        "action_version": version,
        "action_inputs": dict(inputs),
        "authorization_policy_version": _EXPECTED_AUTHORIZATION_POLICY_VERSION,
        "execution_policy_version": _EXPECTED_EXECUTION_POLICY_VERSION,
    })
    return f"delegated-{digest[:40]}"


def compile_authenticated_machine_request(
    adapter_id: str,
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    policy_id: str,
    request_delegation_policy_path: str | Path,
    research_run: str | Path,
    planning_registry_path: str | Path,
    output_dir: str | Path,
    action_inputs: Mapping[str, str | Path] | None = None,
) -> dict[str, Any]:
    """Compile one exact request; actual execution remains a later independent step."""
    adapter = _text(adapter_id, "adapter_id")
    root = _directory(repository_root, "repository_root")
    mission_file = _file(mission_path, "mission_path")
    policy_file = _file(request_delegation_policy_path, "request_delegation_policy_path")
    run = _directory(research_run, "research_run")
    planning_path = _repo_file(planning_registry_path, root, "planning_registry_path")
    _validate_downstream_versions()
    mission_bytes, mission_sha, policy_bytes, policy_sha, policy = _authenticate(
        root=root, mission_file=mission_file, policy_file=policy_file,
        expected_mission_sha256=expected_mission_sha256, policy_id=policy_id, adapter_id=adapter,
    )
    planning, planning_raw = _registry_snapshot(planning_path, root)
    state, ledger_sha = _research_snapshot(run)
    authorization = action_authorization_module.assess_current_action_authorization(
        adapter, repository_root=root, research_run=run, action_registry_path=planning_path
    )
    action_type, version, spec, execution, execution_path, selected, execution_raw = _verify_selected(authorization, root, policy)
    inputs = _resolve_inputs(spec, action_inputs)
    selected_sha = _canonical_digest(dict(selected))
    action_id = _action_id(
        adapter=adapter, mission_sha=mission_sha, policy_sha=policy_sha,
        planning=planning, planning_raw=planning_raw, execution=execution,
        execution_raw=execution_raw, ledger_sha=ledger_sha, selected_sha=selected_sha,
        action_type=action_type, version=version, inputs=inputs,
    )
    if any(isinstance(item, Mapping) and item.get("action_id") == action_id for item in state["actions"]):
        raise AuthenticatedRequestCompilerError("deterministic delegated action_id already exists in research ledger")
    request = {
        "schema_version": _REQUEST_SCHEMA_VERSION,
        "action_id": action_id,
        "action_type": action_type,
        "research_run": str(run),
        **inputs,
        "registry": str(execution_path),
        "repository_root": str(root),
        "expected_registry_sha256": execution["registry_sha256"],
    }
    request_bytes = _canonical_bytes(request)
    request_sha = hashlib.sha256(request_bytes).hexdigest()

    # Re-read every mutable authority input immediately before materialization.
    if mission_file.read_bytes() != mission_bytes or policy_file.read_bytes() != policy_bytes:
        raise AuthenticatedRequestCompilerError("mission or delegation-policy bytes changed during compilation")
    planning2, planning_raw2 = _registry_snapshot(planning_path, root)
    execution2, execution_raw2 = _registry_snapshot(execution_path, root)
    state2, ledger_sha2 = _research_snapshot(run)
    if planning2["registry_sha256"] != planning["registry_sha256"] or planning_raw2 != planning_raw:
        raise AuthenticatedRequestCompilerError("planning registry changed during compilation")
    if execution2["registry_sha256"] != execution["registry_sha256"] or execution_raw2 != execution_raw:
        raise AuthenticatedRequestCompilerError("execution registry changed during compilation")
    if ledger_sha2 != ledger_sha or state2 != state:
        raise AuthenticatedRequestCompilerError("research ledger/state changed during compilation")

    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise AuthenticatedRequestCompilerError(f"output_dir already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    request_path = staging / "execution_request.json"
    manifest_path = staging / "authenticated_request_manifest.json"
    final_request = output / request_path.name
    final_manifest = output / manifest_path.name
    manifest = {
        "schema_version": AUTHENTICATED_REQUEST_MANIFEST_SCHEMA_VERSION,
        "compiler_policy_version": AUTHENTICATED_REQUEST_COMPILER_POLICY_VERSION,
        "compilation_status": "bounded_machine_request_compiled_not_executed",
        "adapter_id": adapter,
        "mission_binding": {"path": str(mission_file), "sha256": mission_sha, "bytes": len(mission_bytes), "supplied_expected_sha256": _sha(expected_mission_sha256, "expected_mission_sha256")},
        "request_delegation_policy_binding": {"path": str(policy_file), "policy_id": policy_id, "sha256": policy_sha, "bytes": len(policy_bytes)},
        "planning_registry_binding": {"path": str(planning_path), "registry_id": planning["registry_id"], "registry_sha256": planning["registry_sha256"], "file_sha256": planning_raw},
        "execution_registry_binding": {"path": str(execution_path), "registry_id": execution["registry_id"], "registry_sha256": execution["registry_sha256"], "file_sha256": execution_raw},
        "research_state_binding": {"research_run": str(run), "ledger_sha256": ledger_sha, "ledger_file_sha256": ledger_sha},
        "selected_action_binding": {"sha256": selected_sha, "action_type": action_type, "action_version": version, "category": spec["category"], "cost_units": spec["cost"]},
        "request_binding": {"path": str(final_request), "sha256": request_sha, "bytes": len(request_bytes)},
        "action_inputs": dict(inputs),
        "registry_input_aliases": dict(spec["aliases"]),
        "downstream_contract": {"action_authorization_policy_version": _EXPECTED_AUTHORIZATION_POLICY_VERSION, "authorized_execution_policy_version": _EXPECTED_EXECUTION_POLICY_VERSION},
        "authority_boundary": {
            "machine_request_authorship_permitted_under_supplied_external_mission_root": True,
            "expected_mission_root_supplier_authenticated": False,
            "human_authorship_authenticated": False,
            "operator_identity_authenticated": False,
            "operator_acknowledgement_synthesized": False,
            "execution_authorized": False,
            "action_executed": False,
            "network_access_authorized": False,
            "physical_experiment_execution_authorized": False,
            "generic_command_execution_authorized": False,
            "model_fitting_authorized": False,
            "scientific_evidence_upgraded": False,
            "scientific_status_changed": False,
            "empirical_authority_granted": False,
            "positive_closeout_granted": False,
        },
    }
    try:
        request_path.write_bytes(request_bytes)
        manifest_path.write_bytes(_canonical_bytes(manifest))
        os.replace(staging, output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {**manifest, "manifest_binding": {"path": str(final_manifest), "sha256": hashlib.sha256(final_manifest.read_bytes()).hexdigest()}}


__all__ = [
    "AUTHENTICATED_REQUEST_COMPILER_POLICY_VERSION",
    "AUTHENTICATED_REQUEST_MANIFEST_SCHEMA_VERSION",
    "AuthenticatedRequestCompilerError",
    "AuthenticatedRequestInputBindingRequired",
    "compile_authenticated_machine_request",
]
