"""Independently verify mission-rooted machine-authored request bytes.

This verifier deliberately re-runs the external mission-root/delegation chain, current
action authorization, registry bindings, ledger binding, typed-input contract and
deterministic request identity.  It never executes the request and never trusts a
compiler-returned authorization report.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from . import action_authorization as action_authorization_module
from . import authorized_execution as authorized_execution_module
from . import mission_request_delegation_bridge as delegation_bridge_module
from .action_registry import describe_action, load_action_registry
from .kernel import LEDGER_FILENAME, ResearchLoopError, load_research_state
from .research_program import build_research_program

AUTHENTICATED_REQUEST_VERIFIER_SCHEMA_VERSION = "1.0"
AUTHENTICATED_REQUEST_VERIFIER_POLICY_VERSION = "1.0"
_EXPECTED_MANIFEST_SCHEMA_VERSION = "1.0"
_EXPECTED_COMPILER_POLICY_VERSION = "1.0"
_EXPECTED_AUTHORIZATION_POLICY_VERSION = "1.1"
_EXPECTED_EXECUTION_POLICY_VERSION = "1.7"
_EXPECTED_BRIDGE_SCHEMA_VERSION = "1.0"
_EXPECTED_REQUEST_SCHEMA_VERSION = "1.0"

# Deliberately duplicated instead of importing the compiler allowlist.
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


class AuthenticatedRequestVerificationError(ResearchLoopError):
    """Raised when independently verified request eligibility fails closed."""


def _json(raw: bytes, field: str) -> dict[str, Any]:
    def reject(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise AuthenticatedRequestVerificationError(f"duplicate JSON key is not allowed: {key}")
            out[key] = value
        return out

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthenticatedRequestVerificationError(f"{field} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise AuthenticatedRequestVerificationError(f"{field} root must be an object")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise AuthenticatedRequestVerificationError(f"{field} must be non-empty text without surrounding whitespace")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        raise AuthenticatedRequestVerificationError(f"{field} must be lowercase SHA-256 hex")
    return text


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AuthenticatedRequestVerificationError(f"{field} must be a positive integer")
    return value


def _exact(value: object, required: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AuthenticatedRequestVerificationError(f"{field} must be an object")
    missing = sorted(required - set(value))
    extra = sorted(set(value) - required)
    if missing:
        raise AuthenticatedRequestVerificationError(f"{field} is missing required keys: {', '.join(missing)}")
    if extra:
        raise AuthenticatedRequestVerificationError(f"{field} has unknown keys: {', '.join(extra)}")
    return value


def _file(value: str | Path, field: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise AuthenticatedRequestVerificationError(f"{field} does not resolve") from exc
    if not path.is_file():
        raise AuthenticatedRequestVerificationError(f"{field} must be a file")
    return path


def _directory(value: str | Path, field: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise AuthenticatedRequestVerificationError(f"{field} does not resolve") from exc
    if not path.is_dir():
        raise AuthenticatedRequestVerificationError(f"{field} must be a directory")
    return path


def _repo_file(value: object, root: Path, field: str) -> Path:
    candidate = Path(_text(value, field)).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    path = candidate.resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise AuthenticatedRequestVerificationError(f"{field} escapes repository_root") from exc
    if not path.is_file():
        raise AuthenticatedRequestVerificationError(f"{field} must resolve to a file")
    return path


def _snapshot(path: Path, field: str) -> tuple[dict[str, Any], bytes, str]:
    raw = path.read_bytes()
    if not raw:
        raise AuthenticatedRequestVerificationError(f"{field} must not be empty")
    return _json(raw, field), raw, hashlib.sha256(raw).hexdigest()


def _registry(path: Path, root: Path) -> tuple[dict[str, Any], str]:
    before = path.read_bytes()
    value = load_action_registry(path, repository_root=root)
    after = path.read_bytes()
    if before != after:
        raise AuthenticatedRequestVerificationError("registry changed while being validated")
    return value, hashlib.sha256(after).hexdigest()


def _research(run: Path) -> tuple[dict[str, Any], str]:
    ledger = (run / LEDGER_FILENAME).resolve(strict=True)
    before = ledger.read_bytes()
    state = load_research_state(run)
    after = ledger.read_bytes()
    if before != after:
        raise AuthenticatedRequestVerificationError("research ledger changed while being validated")
    raw_sha = hashlib.sha256(after).hexdigest()
    if _sha(state.get("ledger_sha256"), "research_state.ledger_sha256") != raw_sha:
        raise AuthenticatedRequestVerificationError("verified ledger checksum differs from exact ledger bytes")
    if not isinstance(state.get("actions"), list):
        raise AuthenticatedRequestVerificationError("research state actions are malformed")
    return state, raw_sha


def _digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _downstream_versions() -> None:
    if action_authorization_module.AUTHORIZATION_POLICY_VERSION != _EXPECTED_AUTHORIZATION_POLICY_VERSION:
        raise AuthenticatedRequestVerificationError("downstream action-authorization policy version drifted")
    if authorized_execution_module.EXECUTION_POLICY_VERSION != _EXPECTED_EXECUTION_POLICY_VERSION:
        raise AuthenticatedRequestVerificationError("downstream typed-executor policy version drifted")


def _authenticate(*, root: Path, mission: Path, policy: Path, expected: str, policy_id: str, adapter: str) -> tuple[bytes, str, bytes, str, dict[str, Any]]:
    mission_value, mission_bytes, mission_sha = _snapshot(mission, "research mission")
    if mission_sha != _sha(expected, "expected_mission_sha256"):
        raise AuthenticatedRequestVerificationError("mission bytes do not match supplied expected mission SHA")
    autonomy = mission_value.get("autonomy_policy")
    if not isinstance(autonomy, Mapping) or autonomy.get("typed_computational_actions") != "explicit_request":
        raise AuthenticatedRequestVerificationError("machine request verification requires typed_computational_actions=explicit_request")
    program = build_research_program(mission, repository_root=root)
    if mission.read_bytes() != mission_bytes:
        raise AuthenticatedRequestVerificationError("mission changed while rebuilding program projection")
    _, policy_bytes, policy_sha = _snapshot(policy, "request-delegation policy")
    if delegation_bridge_module.MISSION_REQUEST_DELEGATION_BRIDGE_SCHEMA_VERSION != _EXPECTED_BRIDGE_SCHEMA_VERSION:
        raise AuthenticatedRequestVerificationError("mission request-delegation bridge version drifted")
    report = delegation_bridge_module.authenticate_request_delegation_policy_under_expected_mission_root(
        mission_bytes=mission_bytes,
        expected_mission_sha256=mission_sha,
        program_state=program,
        policy_id=_text(policy_id, "policy_id"),
        request_delegation_policy_bytes=policy_bytes,
    )
    if report.get("schema_version") != _EXPECTED_BRIDGE_SCHEMA_VERSION or report.get("request_delegation_policy_sha256") != policy_sha:
        raise AuthenticatedRequestVerificationError("delegation bridge did not authenticate exact policy bytes")
    for field in (
        "expected_mission_root_supplier_authenticated", "human_authorship_authenticated",
        "machine_request_authorship_authorized", "execution_authorized", "network_access_authorized",
        "physical_experiment_execution_authorized", "generic_command_execution_authorized",
        "scientific_evidence_upgraded", "scientific_status_changed", "empirical_authority_granted",
        "positive_closeout_granted",
    ):
        if report.get(field) is not False:
            raise AuthenticatedRequestVerificationError(f"delegation bridge widened authority: {field}")
    normalized = report.get("normalized_request_delegation_policy")
    if not isinstance(normalized, dict) or normalized.get("adapter_id") != adapter:
        raise AuthenticatedRequestVerificationError("authenticated delegation policy adapter mismatch")
    return mission_bytes, mission_sha, policy_bytes, policy_sha, normalized


def _input_names(contract: Mapping[str, Any]) -> tuple[str, ...]:
    values = contract.get("required_inputs")
    if not isinstance(values, list):
        raise AuthenticatedRequestVerificationError("registry required_inputs are malformed")
    names: list[str] = []
    for item in values:
        if not isinstance(item, Mapping):
            raise AuthenticatedRequestVerificationError("registry input record is malformed")
        names.append(_text(item.get("name"), "registry input name"))
    return tuple(names)


def _policy_action(policy: Mapping[str, Any], action_type: str, version: str) -> Mapping[str, Any]:
    values = policy.get("allowed_actions")
    matches = [item for item in values if isinstance(item, Mapping) and item.get("action_type") == action_type and item.get("action_version") == version] if isinstance(values, list) else []
    if len(matches) != 1:
        raise AuthenticatedRequestVerificationError("authenticated policy does not delegate exact action/version")
    return matches[0]


def _selected(authorization: Mapping[str, Any], root: Path, policy: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any], Path, Mapping[str, Any], str]:
    if authorization.get("authorization_status") != "ready_for_explicit_execution_request":
        raise AuthenticatedRequestVerificationError("current planner/authorization state does not permit an explicit request")
    selected = authorization.get("selected_action")
    auth = authorization.get("execution_contract")
    if not isinstance(selected, Mapping) or not isinstance(auth, Mapping):
        raise AuthenticatedRequestVerificationError("authorization omitted selected action contract")
    action_type = _text(selected.get("action_type"), "selected action type")
    version = _text(selected.get("action_version"), "selected action version")
    if action_type in _HARD_DENIED:
        raise AuthenticatedRequestVerificationError(f"action is hard-denied for machine request authorship: {action_type}")
    spec = _SAFE_ACTIONS.get(action_type)
    if spec is None or version != spec["version"]:
        raise AuthenticatedRequestVerificationError("selected action/version is outside independent hardcoded request allowlist")
    if selected.get("availability") != "available" or selected.get("cost_units") != spec["cost"]:
        raise AuthenticatedRequestVerificationError("selected action availability or cost drifted")
    path = _repo_file(selected.get("execution_registry_path"), root, "selected execution registry")
    if _repo_file(auth.get("registry_path"), root, "authorization execution registry") != path:
        raise AuthenticatedRequestVerificationError("planner selection and authorization disagree on execution registry")
    registry, raw_sha = _registry(path, root)
    rid = _text(selected.get("execution_registry_id"), "selected registry id")
    rsha = _sha(selected.get("execution_registry_sha256"), "selected registry sha")
    if registry["registry_id"] != rid or registry["registry_sha256"] != rsha:
        raise AuthenticatedRequestVerificationError("selected execution registry identity drifted")
    if auth.get("registry_id") != rid or auth.get("registry_sha256") != rsha:
        raise AuthenticatedRequestVerificationError("authorization execution registry identity drifted")
    contract = describe_action(registry, action_type)
    expected = {"version": version, "availability": "available", "category": spec["category"], "cost_units": spec["cost"], "binding": spec["binding"]}
    for key, value in expected.items():
        if contract.get(key) != value:
            raise AuthenticatedRequestVerificationError(f"execution registry contract drifted on {key}")
    if auth.get("category") != spec["category"] or auth.get("cost_units") != spec["cost"] or auth.get("binding") != spec["binding"]:
        raise AuthenticatedRequestVerificationError("authorization contract drifted")
    if _input_names(contract) != spec["registry_inputs"]:
        raise AuthenticatedRequestVerificationError("execution registry required-input contract drifted")
    if not isinstance(contract.get("verifier_checks"), list) or not contract["verifier_checks"]:
        raise AuthenticatedRequestVerificationError("safe typed action must retain verifier checks")
    delegated = _policy_action(policy, action_type, version)
    if spec["cost"] > _positive_int(policy.get("max_cost_units_per_request"), "policy max cost") or spec["cost"] > _positive_int(delegated.get("max_cost_units"), "policy action max cost"):
        raise AuthenticatedRequestVerificationError("selected action exceeds authenticated delegation cost")
    return action_type, version, spec, registry, path, selected, raw_sha


def _request_inputs(request: Mapping[str, Any], spec: Mapping[str, Any], *, action_type: str, run: Path, root: Path, execution_path: Path, execution_sha: str) -> dict[str, str]:
    keys = {"schema_version", "action_id", "action_type", "research_run", "registry", "repository_root", "expected_registry_sha256", *spec["request_inputs"]}
    _exact(request, keys, "execution request")
    if request["schema_version"] != _EXPECTED_REQUEST_SCHEMA_VERSION or request["action_type"] != action_type:
        raise AuthenticatedRequestVerificationError("execution request schema/action differs from verified selection")
    if _directory(request["research_run"], "request research_run") != run or _directory(request["repository_root"], "request repository_root") != root:
        raise AuthenticatedRequestVerificationError("execution request run/root binding drifted")
    if _file(request["registry"], "request registry") != execution_path or _sha(request["expected_registry_sha256"], "request expected registry sha") != execution_sha:
        raise AuthenticatedRequestVerificationError("execution request registry binding drifted")
    action_id = _text(request["action_id"], "request action_id")
    if len(action_id) > 128 or not all(c.isalnum() or c in "._-" for c in action_id):
        raise AuthenticatedRequestVerificationError("execution request action_id is not executor-safe")
    return {name: str(_directory(request[name], f"request {name}")) for name in spec["request_inputs"]}


def _registry_binding(value: object, path: Path, registry: Mapping[str, Any], field: str) -> str:
    binding = _exact(value, {"path", "registry_id", "registry_sha256", "file_sha256"}, field)
    if _file(binding["path"], f"{field}.path") != path or binding["registry_id"] != registry["registry_id"] or _sha(binding["registry_sha256"], f"{field}.registry_sha256") != registry["registry_sha256"]:
        raise AuthenticatedRequestVerificationError(f"{field} normalized binding mismatch")
    raw_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if _sha(binding["file_sha256"], f"{field}.file_sha256") != raw_sha:
        raise AuthenticatedRequestVerificationError(f"{field} raw registry bytes changed")
    return raw_sha


def _action_id(*, adapter: str, mission_sha: str, policy_sha: str, planning: Mapping[str, Any], planning_raw: str, execution: Mapping[str, Any], execution_raw: str, ledger_sha: str, selected_sha: str, action_type: str, version: str, inputs: Mapping[str, str]) -> str:
    digest = _digest({
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


def _authority_boundary(value: object) -> None:
    keys = {
        "machine_request_authorship_permitted_under_supplied_external_mission_root",
        "expected_mission_root_supplier_authenticated", "human_authorship_authenticated",
        "operator_identity_authenticated", "operator_acknowledgement_synthesized",
        "execution_authorized", "action_executed", "network_access_authorized",
        "physical_experiment_execution_authorized", "generic_command_execution_authorized",
        "model_fitting_authorized", "scientific_evidence_upgraded", "scientific_status_changed",
        "empirical_authority_granted", "positive_closeout_granted",
    }
    boundary = _exact(value, keys, "manifest authority_boundary")
    if boundary["machine_request_authorship_permitted_under_supplied_external_mission_root"] is not True:
        raise AuthenticatedRequestVerificationError("manifest did not declare bounded request-authorship eligibility")
    for key in keys - {"machine_request_authorship_permitted_under_supplied_external_mission_root"}:
        if boundary[key] is not False:
            raise AuthenticatedRequestVerificationError(f"manifest widened authority boundary: {key}")


def verify_authenticated_machine_request(
    adapter_id: str,
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    policy_id: str,
    request_delegation_policy_path: str | Path,
    research_run: str | Path,
    planning_registry_path: str | Path,
    request_path: str | Path,
    manifest_path: str | Path,
) -> dict[str, Any]:
    """Re-authorize exact request bytes without executing them."""
    adapter = _text(adapter_id, "adapter_id")
    root = _directory(repository_root, "repository_root")
    mission_file = _file(mission_path, "mission_path")
    policy_file = _file(request_delegation_policy_path, "request_delegation_policy_path")
    run = _directory(research_run, "research_run")
    planning_path = _repo_file(planning_registry_path, root, "planning_registry_path")
    request_file = _file(request_path, "request_path")
    manifest_file = _file(manifest_path, "manifest_path")
    _downstream_versions()
    mission_bytes, mission_sha, policy_bytes, policy_sha, policy = _authenticate(
        root=root, mission=mission_file, policy=policy_file, expected=expected_mission_sha256,
        policy_id=policy_id, adapter=adapter,
    )
    request, request_bytes, request_sha = _snapshot(request_file, "execution request")
    manifest, _, _ = _snapshot(manifest_file, "authenticated request manifest")
    manifest_keys = {
        "schema_version", "compiler_policy_version", "compilation_status", "adapter_id",
        "mission_binding", "request_delegation_policy_binding", "planning_registry_binding",
        "execution_registry_binding", "research_state_binding", "selected_action_binding",
        "request_binding", "action_inputs", "registry_input_aliases", "downstream_contract",
        "authority_boundary",
    }
    manifest = _exact(manifest, manifest_keys, "authenticated request manifest")
    if manifest["schema_version"] != _EXPECTED_MANIFEST_SCHEMA_VERSION or manifest["compiler_policy_version"] != _EXPECTED_COMPILER_POLICY_VERSION:
        raise AuthenticatedRequestVerificationError("unsupported compiler manifest/policy version")
    if manifest["compilation_status"] != "bounded_machine_request_compiled_not_executed" or manifest["adapter_id"] != adapter:
        raise AuthenticatedRequestVerificationError("manifest status or adapter drifted")

    mission_binding = _exact(manifest["mission_binding"], {"path", "sha256", "bytes", "supplied_expected_sha256"}, "manifest mission binding")
    if _file(mission_binding["path"], "manifest mission path") != mission_file or _sha(mission_binding["sha256"], "manifest mission sha") != mission_sha or mission_binding["bytes"] != len(mission_bytes) or _sha(mission_binding["supplied_expected_sha256"], "manifest expected mission sha") != mission_sha:
        raise AuthenticatedRequestVerificationError("manifest mission binding differs from independently supplied root")
    policy_binding = _exact(manifest["request_delegation_policy_binding"], {"path", "policy_id", "sha256", "bytes"}, "manifest policy binding")
    if _file(policy_binding["path"], "manifest policy path") != policy_file or policy_binding["policy_id"] != policy_id or _sha(policy_binding["sha256"], "manifest policy sha") != policy_sha or policy_binding["bytes"] != len(policy_bytes):
        raise AuthenticatedRequestVerificationError("manifest policy binding mismatch")
    request_binding = _exact(manifest["request_binding"], {"path", "sha256", "bytes"}, "manifest request binding")
    if _file(request_binding["path"], "manifest request path") != request_file or _sha(request_binding["sha256"], "manifest request sha") != request_sha or request_binding["bytes"] != len(request_bytes):
        raise AuthenticatedRequestVerificationError("manifest request checksum/path binding mismatch")

    planning, planning_raw = _registry(planning_path, root)
    if _registry_binding(manifest["planning_registry_binding"], planning_path, planning, "planning registry binding") != planning_raw:
        raise AuthenticatedRequestVerificationError("planning registry raw-byte verification disagreement")
    state_before, ledger_sha = _research(run)
    authorization = action_authorization_module.assess_current_action_authorization(
        adapter, repository_root=root, research_run=run, action_registry_path=planning_path
    )
    action_type, version, spec, execution, execution_path, selected, execution_raw = _selected(authorization, root, policy)
    if _registry_binding(manifest["execution_registry_binding"], execution_path, execution, "execution registry binding") != execution_raw:
        raise AuthenticatedRequestVerificationError("execution registry raw-byte verification disagreement")
    inputs = _request_inputs(request, spec, action_type=action_type, run=run, root=root, execution_path=execution_path, execution_sha=execution["registry_sha256"])
    if manifest["action_inputs"] != inputs or manifest["registry_input_aliases"] != spec["aliases"]:
        raise AuthenticatedRequestVerificationError("manifest typed inputs or registry aliases differ from independent contract")

    selected_sha = _digest(dict(selected))
    selected_binding = _exact(manifest["selected_action_binding"], {"sha256", "action_type", "action_version", "category", "cost_units"}, "manifest selected action")
    if _sha(selected_binding["sha256"], "manifest selected action sha") != selected_sha or selected_binding != {"sha256": selected_sha, "action_type": action_type, "action_version": version, "category": spec["category"], "cost_units": spec["cost"]}:
        raise AuthenticatedRequestVerificationError("manifest selected action binding drifted")
    state_after, ledger_sha_after = _research(run)
    if ledger_sha_after != ledger_sha or state_after != state_before:
        raise AuthenticatedRequestVerificationError("research ledger/state changed during independent verification")
    state_binding = _exact(manifest["research_state_binding"], {"research_run", "ledger_sha256", "ledger_file_sha256"}, "manifest research state")
    if _directory(state_binding["research_run"], "manifest research_run") != run or _sha(state_binding["ledger_sha256"], "manifest ledger sha") != ledger_sha or _sha(state_binding["ledger_file_sha256"], "manifest ledger file sha") != ledger_sha:
        raise AuthenticatedRequestVerificationError("research ledger changed after request compilation")
    downstream = _exact(manifest["downstream_contract"], {"action_authorization_policy_version", "authorized_execution_policy_version"}, "manifest downstream contract")
    if downstream != {"action_authorization_policy_version": _EXPECTED_AUTHORIZATION_POLICY_VERSION, "authorized_execution_policy_version": _EXPECTED_EXECUTION_POLICY_VERSION}:
        raise AuthenticatedRequestVerificationError("manifest downstream contract drifted")
    expected_id = _action_id(
        adapter=adapter, mission_sha=mission_sha, policy_sha=policy_sha,
        planning=planning, planning_raw=planning_raw, execution=execution, execution_raw=execution_raw,
        ledger_sha=ledger_sha, selected_sha=selected_sha, action_type=action_type, version=version, inputs=inputs,
    )
    if request.get("action_id") != expected_id:
        raise AuthenticatedRequestVerificationError("execution request action_id disagrees with independent deterministic derivation")
    if any(isinstance(item, Mapping) and item.get("action_id") == expected_id for item in state_after["actions"]):
        raise AuthenticatedRequestVerificationError("deterministic delegated action_id already exists in research ledger")
    _authority_boundary(manifest["authority_boundary"])

    # Final byte rebinding protects the whole verification interval.
    if hashlib.sha256(mission_file.read_bytes()).hexdigest() != mission_sha or hashlib.sha256(policy_file.read_bytes()).hexdigest() != policy_sha:
        raise AuthenticatedRequestVerificationError("mission or delegation-policy bytes changed during verification")
    planning2, planning_raw2 = _registry(planning_path, root)
    execution2, execution_raw2 = _registry(execution_path, root)
    _, ledger_sha2 = _research(run)
    if planning2["registry_sha256"] != planning["registry_sha256"] or planning_raw2 != planning_raw or execution2["registry_sha256"] != execution["registry_sha256"] or execution_raw2 != execution_raw or ledger_sha2 != ledger_sha:
        raise AuthenticatedRequestVerificationError("registry or ledger changed during independent verification")

    return {
        "schema_version": AUTHENTICATED_REQUEST_VERIFIER_SCHEMA_VERSION,
        "verifier_policy_version": AUTHENTICATED_REQUEST_VERIFIER_POLICY_VERSION,
        "verification_status": "bounded_machine_request_verified_eligible_for_existing_typed_executor",
        "adapter_id": adapter,
        "action_type": action_type,
        "action_version": version,
        "cost_units": spec["cost"],
        "expected_mission_sha256": mission_sha,
        "request_binding": {"path": str(request_file), "sha256": request_sha, "bytes": len(request_bytes)},
        "request_delegation_policy_binding": {"path": str(policy_file), "policy_id": policy_id, "sha256": policy_sha, "bytes": len(policy_bytes)},
        "planning_registry_binding": {"path": str(planning_path), "registry_id": planning["registry_id"], "registry_sha256": planning["registry_sha256"], "file_sha256": planning_raw},
        "execution_registry_binding": {"path": str(execution_path), "registry_id": execution["registry_id"], "registry_sha256": execution["registry_sha256"], "file_sha256": execution_raw},
        "research_state_binding": {"research_run": str(run), "ledger_sha256": ledger_sha, "ledger_file_sha256": ledger_sha},
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
    }


__all__ = [
    "AUTHENTICATED_REQUEST_VERIFIER_POLICY_VERSION",
    "AUTHENTICATED_REQUEST_VERIFIER_SCHEMA_VERSION",
    "AuthenticatedRequestVerificationError",
    "verify_authenticated_machine_request",
]
