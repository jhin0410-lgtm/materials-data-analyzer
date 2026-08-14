"""Independent verifier for machine-authored bounded local execution requests.

This verifier deliberately re-derives planner selection, registry contract, budget,
mission binding, delegation scope, research-ledger binding, deterministic action ID,
and the exact typed request shape.  It does not trust compiler-returned booleans and
performs no execution itself.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .action_authorization import assess_current_action_authorization
from .action_registry import describe_action, load_action_registry
from .kernel import ResearchLoopError, load_research_state
from .research_program import validate_research_mission

VERIFIER_SCHEMA_VERSION = "1.0"
VERIFIER_POLICY_VERSION = "1.0"
_EXPECTED_COMPILER_POLICY_VERSION = "1.0"
_EXPECTED_DELEGATION_SCHEMA_VERSION = "1.0"
_EXPECTED_REQUEST_SCHEMA_VERSION = "1.0"

# Repeated intentionally instead of importing the compiler allowlist.  This keeps a
# compiler edit from silently widening the independent verification boundary.
_VERIFIED_SAFE_ACTIONS: dict[str, dict[str, Any]] = {
    "audit_existing_battery_run": {
        "version": "1.0",
        "category": "diagnostic_audit",
        "cost_units": 2,
        "request_inputs": ("analysis_run",),
    },
    "target_reference_sensitivity": {
        "version": "1.0",
        "category": "target_semantics_audit",
        "cost_units": 4,
        "request_inputs": ("analysis_run",),
    },
    "protocol_stratification": {
        "version": "1.0",
        "category": "hypothesis_discrimination",
        "cost_units": 5,
        "request_inputs": ("import_run", "analysis_run"),
    },
    "external_data_requirement_generation": {
        "version": "1.0",
        "category": "next_evidence_planning",
        "cost_units": 2,
        "request_inputs": (),
    },
}


class PolicyRequestVerificationError(ResearchLoopError):
    """Raised when a compiled request cannot be independently re-authorized."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PolicyRequestVerificationError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _snapshot_json(path: Path) -> tuple[dict[str, Any], bytes, str]:
    raw = path.read_bytes()
    if not raw:
        raise PolicyRequestVerificationError(f"JSON file must not be empty: {path}")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PolicyRequestVerificationError(f"invalid JSON snapshot: {path}") from exc
    if not isinstance(value, dict):
        raise PolicyRequestVerificationError(f"JSON root must be an object: {path}")
    return value, raw, hashlib.sha256(raw).hexdigest()


def _canonical_digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolicyRequestVerificationError(f"{field} must be a non-empty string")
    return value.strip()


def _sha256_text(value: object, field: str) -> str:
    text = _nonempty_text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise PolicyRequestVerificationError(f"{field} must be lowercase SHA-256 hex")
    return text


def _exact_object(
    value: object,
    *,
    required: set[str],
    allowed: set[str],
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PolicyRequestVerificationError(f"{field} must be an object")
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise PolicyRequestVerificationError(
            f"{field} is missing required keys: {', '.join(missing)}"
        )
    if unknown:
        raise PolicyRequestVerificationError(
            f"{field} has unknown keys: {', '.join(unknown)}"
        )
    return value


def _resolve_file(value: str | Path, field: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise PolicyRequestVerificationError(f"{field} does not resolve: {value}") from exc
    if not path.is_file():
        raise PolicyRequestVerificationError(f"{field} must be a file: {path}")
    return path


def _resolve_dir(value: str | Path, field: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise PolicyRequestVerificationError(f"{field} does not resolve: {value}") from exc
    if not path.is_dir():
        raise PolicyRequestVerificationError(f"{field} must be a directory: {path}")
    return path


def _binding_path(value: object, *, base: Path, field: str, expect_file: bool) -> Path:
    text = _nonempty_text(value, field)
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = base / path
    try:
        resolved = path.resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise PolicyRequestVerificationError(f"{field} does not resolve") from exc
    if expect_file and not resolved.is_file():
        raise PolicyRequestVerificationError(f"{field} must resolve to a file")
    return resolved


def _verify_policy(
    value: Mapping[str, Any],
    *,
    policy_path: Path,
    policy_sha256: str,
    mission_path: Path,
    mission_sha256: str,
    adapter_id: str,
    action_type: str,
    action_version: str,
    action_cost: int,
) -> None:
    policy = _exact_object(
        value,
        required={
            "schema_version",
            "policy_id",
            "mission_binding",
            "adapter_id",
            "allowed_actions",
            "max_cost_units_per_request",
            "network_access",
            "physical_experiment_execution",
            "generic_command_execution",
        },
        allowed={
            "schema_version",
            "policy_id",
            "mission_binding",
            "adapter_id",
            "allowed_actions",
            "max_cost_units_per_request",
            "network_access",
            "physical_experiment_execution",
            "generic_command_execution",
            "metadata",
        },
        field="delegation policy",
    )
    if policy["schema_version"] != _EXPECTED_DELEGATION_SCHEMA_VERSION:
        raise PolicyRequestVerificationError("unsupported delegation policy schema_version")
    _nonempty_text(policy["policy_id"], "policy.policy_id")
    if _nonempty_text(policy["adapter_id"], "policy.adapter_id") != adapter_id:
        raise PolicyRequestVerificationError("policy adapter_id mismatch")
    mission_binding = _exact_object(
        policy["mission_binding"],
        required={"path", "sha256"},
        allowed={"path", "sha256"},
        field="policy.mission_binding",
    )
    bound_mission = _binding_path(
        mission_binding["path"],
        base=policy_path.parent,
        field="policy.mission_binding.path",
        expect_file=True,
    )
    if bound_mission != mission_path:
        raise PolicyRequestVerificationError("policy is bound to a different mission path")
    if _sha256_text(mission_binding["sha256"], "policy.mission_binding.sha256") != mission_sha256:
        raise PolicyRequestVerificationError("policy mission checksum mismatch")
    for field in ("network_access", "physical_experiment_execution", "generic_command_execution"):
        if policy[field] is not False:
            raise PolicyRequestVerificationError(f"policy must keep {field}=false")
    max_cost = policy["max_cost_units_per_request"]
    if isinstance(max_cost, bool) or not isinstance(max_cost, int) or max_cost <= 0:
        raise PolicyRequestVerificationError("policy max_cost_units_per_request is malformed")
    if action_cost > max_cost:
        raise PolicyRequestVerificationError("request action cost exceeds policy maximum")

    actions = policy["allowed_actions"]
    if not isinstance(actions, list):
        raise PolicyRequestVerificationError("policy allowed_actions must be a list")
    matches: list[Mapping[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(actions):
        item = _exact_object(
            raw,
            required={"action_type", "action_version", "max_cost_units"},
            allowed={"action_type", "action_version", "max_cost_units"},
            field=f"policy.allowed_actions[{index}]",
        )
        key = (
            _nonempty_text(item["action_type"], "policy action_type"),
            _nonempty_text(item["action_version"], "policy action_version"),
        )
        if key in seen:
            raise PolicyRequestVerificationError("policy contains duplicate action/version")
        seen.add(key)
        per_action_cost = item["max_cost_units"]
        if isinstance(per_action_cost, bool) or not isinstance(per_action_cost, int) or per_action_cost <= 0:
            raise PolicyRequestVerificationError("policy action max_cost_units is malformed")
        if key == (action_type, action_version):
            matches.append(item)
    if len(matches) != 1:
        raise PolicyRequestVerificationError("policy does not delegate exact action/version")
    if action_cost > int(matches[0]["max_cost_units"]):
        raise PolicyRequestVerificationError("request action cost exceeds delegated per-action maximum")
    if len(policy_sha256) != 64:
        raise PolicyRequestVerificationError("internal policy snapshot checksum is malformed")


def _request_keys(spec: Mapping[str, Any]) -> set[str]:
    return {
        "schema_version",
        "action_id",
        "action_type",
        "research_run",
        *tuple(str(item) for item in spec["request_inputs"]),
        "registry",
        "repository_root",
        "expected_registry_sha256",
    }


def _verify_request_shape(
    request: Mapping[str, Any],
    *,
    spec: Mapping[str, Any],
    action_type: str,
    research_run: Path,
    registry_path: Path,
    repository_root: Path,
    registry_sha256: str,
) -> dict[str, str]:
    keys = _request_keys(spec)
    _exact_object(request, required=keys, allowed=keys, field="compiled execution request")
    if request["schema_version"] != _EXPECTED_REQUEST_SCHEMA_VERSION:
        raise PolicyRequestVerificationError("unsupported execution request schema_version")
    if request["action_type"] != action_type:
        raise PolicyRequestVerificationError("compiled request action_type mismatch")
    if _resolve_dir(request["research_run"], "request.research_run") != research_run:
        raise PolicyRequestVerificationError("compiled request research_run mismatch")
    if _resolve_file(request["registry"], "request.registry") != registry_path:
        raise PolicyRequestVerificationError("compiled request registry mismatch")
    if _resolve_dir(request["repository_root"], "request.repository_root") != repository_root:
        raise PolicyRequestVerificationError("compiled request repository_root mismatch")
    if _sha256_text(request["expected_registry_sha256"], "request.expected_registry_sha256") != registry_sha256:
        raise PolicyRequestVerificationError("compiled request expected registry checksum mismatch")
    action_id = _nonempty_text(request["action_id"], "request.action_id")
    if len(action_id) > 128 or not all(char.isalnum() or char in "._-" for char in action_id):
        raise PolicyRequestVerificationError("compiled request action_id is not executor-safe")
    return {
        name: str(_resolve_dir(request[name], f"request.{name}"))
        for name in tuple(str(item) for item in spec["request_inputs"])
    }


def _deterministic_action_id(
    *,
    policy_sha256: str,
    mission_sha256: str,
    registry_sha256: str,
    ledger_sha256: str,
    action_type: str,
    action_version: str,
    action_inputs: Mapping[str, str],
) -> str:
    digest = _canonical_digest(
        {
            "policy_sha256": policy_sha256,
            "mission_sha256": mission_sha256,
            "registry_sha256": registry_sha256,
            "ledger_sha256": ledger_sha256,
            "action_type": action_type,
            "action_version": action_version,
            "action_inputs": dict(action_inputs),
        }
    )
    return f"policy-{digest[:40]}"


def verify_policy_authorized_request(
    adapter_id: str,
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    delegation_policy_path: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
    manifest_path: str | Path,
) -> dict[str, Any]:
    """Re-authorize exact compiled bytes without executing them."""
    adapter = _nonempty_text(adapter_id, "adapter_id")
    root = _resolve_dir(repository_root, "repository_root")
    mission_file = _resolve_file(mission_path, "mission_path")
    policy_file = _resolve_file(delegation_policy_path, "delegation_policy_path")
    run = _resolve_dir(research_run, "research_run")
    registry_file = _resolve_file(action_registry_path, "action_registry_path")
    request_file = _resolve_file(request_path, "request_path")
    manifest_file = _resolve_file(manifest_path, "manifest_path")

    mission_value, mission_raw, mission_sha = _snapshot_json(mission_file)
    mission = validate_research_mission(mission_value)
    autonomy = mission.get("autonomy_policy")
    if not isinstance(autonomy, Mapping) or autonomy.get("typed_computational_actions") != "explicit_request":
        raise PolicyRequestVerificationError(
            "delegated request authorship requires mission typed_computational_actions=explicit_request"
        )
    policy_value, policy_raw, policy_sha = _snapshot_json(policy_file)
    request, request_raw, request_sha = _snapshot_json(request_file)
    manifest, _, _ = _snapshot_json(manifest_file)

    manifest = _exact_object(
        manifest,
        required={
            "schema_version",
            "compiler_policy_version",
            "compilation_status",
            "adapter_id",
            "policy_binding",
            "mission_binding",
            "research_state_binding",
            "registry_binding",
            "selected_action_binding",
            "request_binding",
            "action_inputs",
            "autonomy_boundary",
        },
        allowed={
            "schema_version",
            "compiler_policy_version",
            "compilation_status",
            "adapter_id",
            "policy_binding",
            "mission_binding",
            "research_state_binding",
            "registry_binding",
            "selected_action_binding",
            "request_binding",
            "action_inputs",
            "autonomy_boundary",
        },
        field="policy request manifest",
    )
    if manifest["schema_version"] != _EXPECTED_REQUEST_SCHEMA_VERSION:
        raise PolicyRequestVerificationError("unsupported policy request manifest schema_version")
    if manifest["compiler_policy_version"] != _EXPECTED_COMPILER_POLICY_VERSION:
        raise PolicyRequestVerificationError("unsupported compiler policy version")
    if manifest["compilation_status"] != "compiled_bounded_local_request_not_executed":
        raise PolicyRequestVerificationError("manifest compilation status is not pre-execution")
    if manifest["adapter_id"] != adapter:
        raise PolicyRequestVerificationError("manifest adapter_id mismatch")

    request_binding = _exact_object(
        manifest["request_binding"],
        required={"path", "sha256", "bytes"},
        allowed={"path", "sha256", "bytes"},
        field="manifest.request_binding",
    )
    if _resolve_file(request_binding["path"], "manifest.request_binding.path") != request_file:
        raise PolicyRequestVerificationError("manifest request path mismatch")
    if _sha256_text(request_binding["sha256"], "manifest.request_binding.sha256") != request_sha:
        raise PolicyRequestVerificationError("manifest request checksum mismatch")
    if request_binding["bytes"] != len(request_raw):
        raise PolicyRequestVerificationError("manifest request byte count mismatch")

    policy_binding = _exact_object(
        manifest["policy_binding"],
        required={"path", "sha256"},
        allowed={"path", "sha256"},
        field="manifest.policy_binding",
    )
    if _resolve_file(policy_binding["path"], "manifest.policy_binding.path") != policy_file:
        raise PolicyRequestVerificationError("manifest policy path mismatch")
    if _sha256_text(policy_binding["sha256"], "manifest.policy_binding.sha256") != policy_sha:
        raise PolicyRequestVerificationError("manifest policy checksum mismatch")

    mission_binding = _exact_object(
        manifest["mission_binding"],
        required={"path", "sha256", "bytes"},
        allowed={"path", "sha256", "bytes"},
        field="manifest.mission_binding",
    )
    if _resolve_file(mission_binding["path"], "manifest.mission_binding.path") != mission_file:
        raise PolicyRequestVerificationError("manifest mission path mismatch")
    if _sha256_text(mission_binding["sha256"], "manifest.mission_binding.sha256") != mission_sha:
        raise PolicyRequestVerificationError("manifest mission checksum mismatch")
    if mission_binding["bytes"] != len(mission_raw):
        raise PolicyRequestVerificationError("manifest mission byte count mismatch")

    registry = load_action_registry(registry_file, repository_root=root)
    authorization = assess_current_action_authorization(
        adapter,
        repository_root=root,
        research_run=run,
        action_registry_path=registry_file,
    )
    if authorization.get("authorization_status") != "ready_for_explicit_execution_request":
        raise PolicyRequestVerificationError("current planner/registry/budget state no longer permits the request")
    selected = authorization.get("selected_action")
    if not isinstance(selected, Mapping):
        raise PolicyRequestVerificationError("current authorization omitted selected action")
    action_type = _nonempty_text(selected.get("action_type"), "selected_action.action_type")
    action_version = _nonempty_text(selected.get("action_version"), "selected_action.action_version")
    spec = _VERIFIED_SAFE_ACTIONS.get(action_type)
    if spec is None or action_version != spec["version"]:
        raise PolicyRequestVerificationError("selected action/version is outside independent safe allowlist")
    contract = describe_action(registry, action_type)
    if contract.get("availability") != "available":
        raise PolicyRequestVerificationError("runtime registry action is no longer available")
    if (
        contract.get("version") != spec["version"]
        or contract.get("category") != spec["category"]
        or contract.get("cost_units") != spec["cost_units"]
    ):
        raise PolicyRequestVerificationError("runtime registry contract differs from independent safe contract")
    binding = contract.get("binding")
    if not isinstance(binding, Mapping) or binding.get("kind") != "installed_command":
        raise PolicyRequestVerificationError("safe machine request requires installed-command binding")
    if not isinstance(contract.get("verifier_checks"), list) or not contract["verifier_checks"]:
        raise PolicyRequestVerificationError("safe machine request requires verifier checks")
    if selected.get("execution_registry_sha256") != registry.get("registry_sha256"):
        raise PolicyRequestVerificationError("planner-selected registry checksum drifted")
    if selected.get("cost_units") != spec["cost_units"]:
        raise PolicyRequestVerificationError("planner-selected cost drifted")

    _verify_policy(
        policy_value,
        policy_path=policy_file,
        policy_sha256=policy_sha,
        mission_path=mission_file,
        mission_sha256=mission_sha,
        adapter_id=adapter,
        action_type=action_type,
        action_version=action_version,
        action_cost=int(spec["cost_units"]),
    )
    action_inputs = _verify_request_shape(
        request,
        spec=spec,
        action_type=action_type,
        research_run=run,
        registry_path=registry_file,
        repository_root=root,
        registry_sha256=str(registry["registry_sha256"]),
    )
    manifest_inputs = manifest["action_inputs"]
    if not isinstance(manifest_inputs, dict) or manifest_inputs != action_inputs:
        raise PolicyRequestVerificationError("manifest action inputs differ from exact typed request")

    selected_binding = _exact_object(
        manifest["selected_action_binding"],
        required={"sha256", "action_type", "action_version", "category", "cost_units"},
        allowed={"sha256", "action_type", "action_version", "category", "cost_units"},
        field="manifest.selected_action_binding",
    )
    if _sha256_text(selected_binding["sha256"], "manifest.selected_action_binding.sha256") != _canonical_digest(dict(selected)):
        raise PolicyRequestVerificationError("manifest selected-action fingerprint mismatch")
    expected_selected = {
        "action_type": action_type,
        "action_version": action_version,
        "category": spec["category"],
        "cost_units": spec["cost_units"],
    }
    for key, expected in expected_selected.items():
        if selected_binding[key] != expected:
            raise PolicyRequestVerificationError(f"manifest selected action drifted on {key}")

    state = load_research_state(run)
    ledger_sha = _sha256_text(state.get("ledger_sha256"), "research_state.ledger_sha256")
    state_binding = _exact_object(
        manifest["research_state_binding"],
        required={"research_run", "ledger_sha256"},
        allowed={"research_run", "ledger_sha256"},
        field="manifest.research_state_binding",
    )
    if _resolve_dir(state_binding["research_run"], "manifest.research_state_binding.research_run") != run:
        raise PolicyRequestVerificationError("manifest research_run mismatch")
    if _sha256_text(state_binding["ledger_sha256"], "manifest.research_state_binding.ledger_sha256") != ledger_sha:
        raise PolicyRequestVerificationError("research ledger changed after request compilation")

    registry_binding = _exact_object(
        manifest["registry_binding"],
        required={"path", "registry_id", "registry_sha256"},
        allowed={"path", "registry_id", "registry_sha256"},
        field="manifest.registry_binding",
    )
    if _resolve_file(registry_binding["path"], "manifest.registry_binding.path") != registry_file:
        raise PolicyRequestVerificationError("manifest registry path mismatch")
    if registry_binding["registry_id"] != registry["registry_id"]:
        raise PolicyRequestVerificationError("manifest registry_id mismatch")
    if _sha256_text(registry_binding["registry_sha256"], "manifest.registry_binding.registry_sha256") != registry["registry_sha256"]:
        raise PolicyRequestVerificationError("manifest registry checksum mismatch")

    expected_action_id = _deterministic_action_id(
        policy_sha256=policy_sha,
        mission_sha256=mission_sha,
        registry_sha256=str(registry["registry_sha256"]),
        ledger_sha256=ledger_sha,
        action_type=action_type,
        action_version=action_version,
        action_inputs=action_inputs,
    )
    if request.get("action_id") != expected_action_id:
        raise PolicyRequestVerificationError("compiled request action_id is not deterministic for current authority state")
    actions = state.get("actions")
    if not isinstance(actions, list):
        raise PolicyRequestVerificationError("research state actions are malformed")
    if any(isinstance(item, Mapping) and item.get("action_id") == expected_action_id for item in actions):
        raise PolicyRequestVerificationError("compiled action_id already exists in research ledger")

    boundary = manifest["autonomy_boundary"]
    if not isinstance(boundary, Mapping):
        raise PolicyRequestVerificationError("manifest autonomy boundary is malformed")
    required_false = {
        "execution_authorized_by_compiler",
        "human_acknowledgement_generated",
        "network_access_authorized",
        "physical_experiment_execution_authorized",
        "generic_command_execution_authorized",
        "model_fitting_authorized",
        "scientific_evidence_upgraded",
    }
    if boundary.get("request_authorship_delegated") is not True or any(
        boundary.get(field) is not False for field in required_false
    ):
        raise PolicyRequestVerificationError("manifest autonomy boundary is not fail-closed")

    return {
        "schema_version": VERIFIER_SCHEMA_VERSION,
        "verifier_policy_version": VERIFIER_POLICY_VERSION,
        "verification_status": "authorized_for_existing_typed_executor",
        "adapter_id": adapter,
        "action_type": action_type,
        "action_version": action_version,
        "cost_units": spec["cost_units"],
        "request_binding": {
            "path": str(request_file),
            "sha256": request_sha,
            "bytes": len(request_raw),
        },
        "policy_binding": {"path": str(policy_file), "sha256": policy_sha, "bytes": len(policy_raw)},
        "mission_binding": {"path": str(mission_file), "sha256": mission_sha},
        "registry_binding": {
            "path": str(registry_file),
            "registry_id": registry["registry_id"],
            "registry_sha256": registry["registry_sha256"],
        },
        "research_state_binding": {"research_run": str(run), "ledger_sha256": ledger_sha},
        "automatic_execution_permitted_under_delegation": True,
        "action_executed": False,
        "network_access_authorized": False,
        "physical_experiment_execution_authorized": False,
        "generic_command_execution_authorized": False,
        "scientific_evidence_upgraded": False,
    }


__all__ = [
    "VERIFIER_POLICY_VERSION",
    "VERIFIER_SCHEMA_VERSION",
    "PolicyRequestVerificationError",
    "verify_policy_authorized_request",
]
