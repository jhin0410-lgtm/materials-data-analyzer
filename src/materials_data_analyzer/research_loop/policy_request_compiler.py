"""Compile one bounded machine-authored typed request under explicit delegation.

Request authorship is delegated; execution and scientific authority are not. The
compiler reuses the existing planner/budget authorization, but independently pins the
planning registry, the planner-selected execution registry, the current research
ledger, explicit typed inputs, and a human-authored delegation policy.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .action_authorization import assess_current_action_authorization
from .action_registry import describe_action, load_action_registry
from .kernel import ResearchLoopError, load_research_state
from .research_program import validate_research_mission

POLICY_REQUEST_SCHEMA_VERSION = "1.1"
DELEGATION_POLICY_SCHEMA_VERSION = "1.0"
POLICY_REQUEST_COMPILER_VERSION = "1.1"

# These contracts intentionally duplicate facts implemented by the finite typed
# executor. A registry cannot opt itself into machine-authored execution requests.
_SAFE_TYPED_ACTIONS: dict[str, dict[str, Any]] = {
    "audit_existing_battery_run": {
        "version": "1.0",
        "category": "diagnostic_audit",
        "cost_units": 2,
        "request_inputs": ("analysis_run",),
        "registry_inputs": ("run_output",),
        "input_aliases": {"run_output": "analysis_run"},
        "binding": {
            "kind": "installed_command",
            "name": "mda-battery-result-audit",
            "path": None,
            "platform": "cross_platform",
        },
    },
    "target_reference_sensitivity": {
        "version": "1.0",
        "category": "target_semantics_audit",
        "cost_units": 4,
        "request_inputs": ("analysis_run",),
        "registry_inputs": ("analysis_run", "research_run"),
        "input_aliases": {"analysis_run": "analysis_run"},
        "binding": {
            "kind": "installed_command",
            "name": "mda-research-loop",
            "path": None,
            "platform": "cross_platform",
        },
    },
    "protocol_stratification": {
        "version": "1.0",
        "category": "hypothesis_discrimination",
        "cost_units": 5,
        "request_inputs": ("import_run", "analysis_run"),
        "registry_inputs": ("import_run", "analysis_run", "research_run"),
        "input_aliases": {
            "import_run": "import_run",
            "analysis_run": "analysis_run",
        },
        "binding": {
            "kind": "installed_command",
            "name": "mda-research-loop",
            "path": None,
            "platform": "cross_platform",
        },
    },
    "external_data_requirement_generation": {
        "version": "1.0",
        "category": "next_evidence_planning",
        "cost_units": 2,
        "request_inputs": (),
        "registry_inputs": ("research_state", "unresolved_blocker_reports"),
        "input_aliases": {},
        "binding": {
            "kind": "source_script",
            "name": None,
            "path": "scripts/run_nasa_external_data_requirement_action.py",
            "platform": "cross_platform",
        },
    },
}

_HARD_DENIED_ACTIONS = {
    "run_fixed_battery_intelligence",
    "import_official_nasa_archive",
    "close_reviewed_nasa_audit",
    "hierarchical_state_space_baseline",
    "feature_family_ablation",
    "selective_prediction_abstention",
    "source_cohort_leave_one_out",
}


class PolicyRequestCompilerError(ResearchLoopError):
    """Raised when delegated request authorship cannot remain fail-closed."""


class PolicyRequestInputBindingRequired(PolicyRequestCompilerError):
    """Raised instead of guessing an action-specific input path."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PolicyRequestCompilerError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _snapshot_json(path: Path) -> tuple[dict[str, Any], bytes, str]:
    raw = path.read_bytes()
    if not raw:
        raise PolicyRequestCompilerError(f"JSON file must not be empty: {path}")
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PolicyRequestCompilerError(f"invalid JSON snapshot: {path}") from exc
    if not isinstance(value, dict):
        raise PolicyRequestCompilerError(f"JSON root must be an object: {path}")
    return value, raw, hashlib.sha256(raw).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


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
        raise PolicyRequestCompilerError(f"{field} must be a non-empty string")
    return value.strip()


def _sha256_text(value: object, field: str) -> str:
    text = _nonempty_text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise PolicyRequestCompilerError(f"{field} must be lowercase SHA-256 hex")
    return text


def _resolve_file(value: str | Path, field: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise PolicyRequestCompilerError(f"{field} does not resolve: {value}") from exc
    if not path.is_file():
        raise PolicyRequestCompilerError(f"{field} must be a regular file: {path}")
    return path


def _resolve_repo_file(value: object, *, root: Path, field: str) -> Path:
    text = _nonempty_text(value, field)
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        resolved = path.resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise PolicyRequestCompilerError(f"{field} does not resolve") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PolicyRequestCompilerError(f"{field} escapes repository_root") from exc
    if not resolved.is_file():
        raise PolicyRequestCompilerError(f"{field} must resolve to a file")
    return resolved


def _resolve_dir(value: str | Path, field: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise PolicyRequestCompilerError(f"{field} does not resolve: {value}") from exc
    if not path.is_dir():
        raise PolicyRequestCompilerError(f"{field} must be a directory: {path}")
    return path


def _exact_object(
    value: object,
    *,
    required: set[str],
    allowed: set[str],
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PolicyRequestCompilerError(f"{field} must be an object")
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise PolicyRequestCompilerError(
            f"{field} is missing required keys: {', '.join(missing)}"
        )
    if unknown:
        raise PolicyRequestCompilerError(
            f"{field} has unknown keys: {', '.join(unknown)}"
        )
    return value


def _load_delegation_policy(
    policy_path: Path,
    *,
    mission_path: Path,
    mission_sha256: str,
    adapter_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    value, raw, policy_sha = _snapshot_json(policy_path)
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
        field="bounded request delegation policy",
    )
    if policy["schema_version"] != DELEGATION_POLICY_SCHEMA_VERSION:
        raise PolicyRequestCompilerError(
            "unsupported delegation policy schema_version"
        )
    if _nonempty_text(policy["adapter_id"], "policy.adapter_id") != adapter_id:
        raise PolicyRequestCompilerError(
            "delegation policy adapter_id does not match request adapter"
        )

    mission_binding = _exact_object(
        policy["mission_binding"],
        required={"path", "sha256"},
        allowed={"path", "sha256"},
        field="policy.mission_binding",
    )
    bound_mission = Path(
        _nonempty_text(
            mission_binding["path"], "policy.mission_binding.path"
        )
    ).expanduser()
    if not bound_mission.is_absolute():
        bound_mission = policy_path.parent / bound_mission
    try:
        bound_mission = bound_mission.resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise PolicyRequestCompilerError(
            "policy mission binding does not resolve"
        ) from exc
    if bound_mission != mission_path:
        raise PolicyRequestCompilerError(
            "delegation policy is bound to a different mission path"
        )
    if (
        _sha256_text(
            mission_binding["sha256"], "policy.mission_binding.sha256"
        )
        != mission_sha256
    ):
        raise PolicyRequestCompilerError(
            "delegation policy mission checksum does not match current bytes"
        )

    max_cost = policy["max_cost_units_per_request"]
    if (
        isinstance(max_cost, bool)
        or not isinstance(max_cost, int)
        or max_cost <= 0
    ):
        raise PolicyRequestCompilerError(
            "max_cost_units_per_request must be a positive integer"
        )
    for field in (
        "network_access",
        "physical_experiment_execution",
        "generic_command_execution",
    ):
        if policy[field] is not False:
            raise PolicyRequestCompilerError(
                f"delegation policy must set {field}=false"
            )

    raw_actions = policy["allowed_actions"]
    if not isinstance(raw_actions, list) or not raw_actions:
        raise PolicyRequestCompilerError(
            "delegation policy allowed_actions must be non-empty"
        )
    normalized_actions: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, raw_action in enumerate(raw_actions):
        item = _exact_object(
            raw_action,
            required={"action_type", "action_version", "max_cost_units"},
            allowed={"action_type", "action_version", "max_cost_units"},
            field=f"policy.allowed_actions[{index}]",
        )
        action_type = _nonempty_text(item["action_type"], "policy action_type")
        action_version = _nonempty_text(
            item["action_version"], "policy action_version"
        )
        action_cost = item["max_cost_units"]
        if (
            isinstance(action_cost, bool)
            or not isinstance(action_cost, int)
            or action_cost <= 0
        ):
            raise PolicyRequestCompilerError(
                "policy action max_cost_units must be positive"
            )
        key = (action_type, action_version)
        if key in seen:
            raise PolicyRequestCompilerError(
                "delegation policy contains duplicate action/version"
            )
        seen.add(key)
        normalized_actions.append(
            {
                "action_type": action_type,
                "action_version": action_version,
                "max_cost_units": action_cost,
            }
        )

    normalized: dict[str, Any] = {
        "schema_version": DELEGATION_POLICY_SCHEMA_VERSION,
        "policy_id": _nonempty_text(policy["policy_id"], "policy.policy_id"),
        "mission_binding": {
            "path": str(mission_path),
            "sha256": mission_sha256,
        },
        "adapter_id": adapter_id,
        "allowed_actions": normalized_actions,
        "max_cost_units_per_request": max_cost,
        "network_access": False,
        "physical_experiment_execution": False,
        "generic_command_execution": False,
    }
    if "metadata" in policy:
        if not isinstance(policy["metadata"], dict):
            raise PolicyRequestCompilerError(
                "policy.metadata must be an object"
            )
        normalized["metadata"] = policy["metadata"]
    return normalized, {
        "path": str(policy_path),
        "sha256": policy_sha,
        "bytes": len(raw),
    }


def _policy_action(
    policy: Mapping[str, Any], action_type: str, action_version: str
) -> Mapping[str, Any]:
    matches = [
        item
        for item in policy.get("allowed_actions", [])
        if isinstance(item, Mapping)
        and item.get("action_type") == action_type
        and item.get("action_version") == action_version
    ]
    if len(matches) != 1:
        raise PolicyRequestCompilerError(
            "delegation policy does not authorize the exact selected action/version"
        )
    return matches[0]


def _resolve_action_inputs(
    spec: Mapping[str, Any],
    raw_inputs: Mapping[str, str | Path] | None,
) -> dict[str, str]:
    required = tuple(str(item) for item in spec["request_inputs"])
    provided = dict(raw_inputs or {})
    missing = sorted(set(required) - set(provided))
    unknown = sorted(set(provided) - set(required))
    if missing:
        raise PolicyRequestInputBindingRequired(
            "action-specific input binding is required; compiler will not guess: "
            + ", ".join(missing)
        )
    if unknown:
        raise PolicyRequestCompilerError(
            "action_inputs contains fields outside the typed request contract: "
            + ", ".join(unknown)
        )
    return {
        name: str(_resolve_dir(provided[name], f"action_inputs.{name}"))
        for name in required
    }


def _registry_input_names(contract: Mapping[str, Any]) -> tuple[str, ...]:
    raw_inputs = contract.get("required_inputs")
    if not isinstance(raw_inputs, list):
        raise PolicyRequestCompilerError(
            "execution registry required_inputs are malformed"
        )
    result: list[str] = []
    for item in raw_inputs:
        if not isinstance(item, Mapping):
            raise PolicyRequestCompilerError(
                "execution registry required input is malformed"
            )
        result.append(_nonempty_text(item.get("name"), "registry input name"))
    return tuple(result)


def _verify_registry_input_contract(
    spec: Mapping[str, Any], contract: Mapping[str, Any]
) -> None:
    observed = _registry_input_names(contract)
    expected = tuple(str(item) for item in spec["registry_inputs"])
    if observed != expected:
        raise PolicyRequestCompilerError(
            "execution registry required-input contract drifted: "
            f"expected {expected}, got {observed}"
        )
    aliases = spec.get("input_aliases")
    if not isinstance(aliases, Mapping):
        raise PolicyRequestCompilerError("hardcoded input alias contract is malformed")
    request_inputs = set(str(item) for item in spec["request_inputs"])
    for registry_name, request_name in aliases.items():
        if registry_name not in expected or request_name not in request_inputs:
            raise PolicyRequestCompilerError(
                "hardcoded registry/request input alias contract is malformed"
            )


def _verify_selected_action(
    authorization: Mapping[str, Any],
    *,
    repository_root: Path,
    planning_registry_path: Path,
    policy: Mapping[str, Any],
) -> tuple[
    str,
    str,
    Mapping[str, Any],
    dict[str, Any],
    Path,
    Mapping[str, Any],
]:
    if (
        authorization.get("authorization_status")
        != "ready_for_explicit_execution_request"
    ):
        raise PolicyRequestCompilerError(
            "current planner/registry/budget state is not ready for an explicit request"
        )
    selected = authorization.get("selected_action")
    auth_contract = authorization.get("execution_contract")
    if not isinstance(selected, Mapping) or not isinstance(auth_contract, Mapping):
        raise PolicyRequestCompilerError(
            "authorization omitted selected action execution contract"
        )
    action_type = _nonempty_text(
        selected.get("action_type"), "selected_action.action_type"
    )
    action_version = _nonempty_text(
        selected.get("action_version"), "selected_action.action_version"
    )
    if action_type in _HARD_DENIED_ACTIONS:
        raise PolicyRequestCompilerError(
            f"action is hard-denied for machine request authorship: {action_type}"
        )
    spec = _SAFE_TYPED_ACTIONS.get(action_type)
    if spec is None:
        raise PolicyRequestCompilerError(
            "action is outside the hardcoded bounded-local request allowlist: "
            f"{action_type}"
        )
    if action_version != spec["version"]:
        raise PolicyRequestCompilerError(
            "planner-selected version does not match hardcoded typed executor version"
        )

    execution_registry_path = _resolve_repo_file(
        auth_contract.get("registry_path"),
        root=repository_root,
        field="authorization.execution_contract.registry_path",
    )
    selected_registry_path = _resolve_repo_file(
        selected.get("execution_registry_path"),
        root=repository_root,
        field="selected_action.execution_registry_path",
    )
    if selected_registry_path != execution_registry_path:
        raise PolicyRequestCompilerError(
            "selected action and authorization disagree on execution registry path"
        )
    execution_registry = load_action_registry(
        execution_registry_path,
        repository_root=repository_root,
    )
    expected_registry_id = _nonempty_text(
        selected.get("execution_registry_id"),
        "selected_action.execution_registry_id",
    )
    expected_registry_sha = _sha256_text(
        selected.get("execution_registry_sha256"),
        "selected_action.execution_registry_sha256",
    )
    if execution_registry["registry_id"] != expected_registry_id:
        raise PolicyRequestCompilerError(
            "selected execution registry ID differs from current registry"
        )
    if execution_registry["registry_sha256"] != expected_registry_sha:
        raise PolicyRequestCompilerError(
            "selected execution registry checksum differs from current registry"
        )
    if auth_contract.get("registry_id") != expected_registry_id:
        raise PolicyRequestCompilerError(
            "authorization execution registry ID differs from selected action"
        )
    if auth_contract.get("registry_sha256") != expected_registry_sha:
        raise PolicyRequestCompilerError(
            "authorization execution registry checksum differs from selected action"
        )

    contract = describe_action(execution_registry, action_type)
    checks = {
        "version": spec["version"],
        "availability": "available",
        "category": spec["category"],
        "cost_units": spec["cost_units"],
    }
    for key, expected in checks.items():
        if contract.get(key) != expected:
            raise PolicyRequestCompilerError(
                f"execution registry contract drifted on {key}"
            )
    if selected.get("availability") != "available":
        raise PolicyRequestCompilerError(
            "planner-selected action is not available"
        )
    if selected.get("cost_units") != spec["cost_units"]:
        raise PolicyRequestCompilerError(
            "planner-selected cost differs from bounded-local policy"
        )
    if contract.get("binding") != spec["binding"]:
        raise PolicyRequestCompilerError(
            "execution registry binding differs from hardcoded typed surface"
        )
    if auth_contract.get("binding") != spec["binding"]:
        raise PolicyRequestCompilerError(
            "authorization binding differs from hardcoded typed surface"
        )
    verifier_checks = contract.get("verifier_checks")
    if not isinstance(verifier_checks, list) or not verifier_checks:
        raise PolicyRequestCompilerError(
            "bounded-local action must retain verifier checks"
        )
    _verify_registry_input_contract(spec, contract)

    delegated = _policy_action(policy, action_type, action_version)
    if spec["cost_units"] > int(policy["max_cost_units_per_request"]):
        raise PolicyRequestCompilerError(
            "selected action exceeds policy max_cost_units_per_request"
        )
    if spec["cost_units"] > int(delegated["max_cost_units"]):
        raise PolicyRequestCompilerError(
            "selected action exceeds delegated per-action cost"
        )

    # The planning registry path remains an independent input to planner selection.
    # It may differ from the selected execution registry when an audited override is
    # used for a planned action.
    if not planning_registry_path.is_file():
        raise PolicyRequestCompilerError("planning registry disappeared")
    return (
        action_type,
        action_version,
        spec,
        execution_registry,
        execution_registry_path,
        selected,
    )


def _action_id(
    *,
    policy_sha256: str,
    mission_sha256: str,
    planning_registry_file_sha256: str,
    execution_registry_file_sha256: str,
    ledger_sha256: str,
    selected_action_sha256: str,
    action_type: str,
    action_version: str,
    action_inputs: Mapping[str, str],
) -> str:
    digest = _canonical_digest(
        {
            "policy_sha256": policy_sha256,
            "mission_sha256": mission_sha256,
            "planning_registry_file_sha256": planning_registry_file_sha256,
            "execution_registry_file_sha256": execution_registry_file_sha256,
            "ledger_sha256": ledger_sha256,
            "selected_action_sha256": selected_action_sha256,
            "action_type": action_type,
            "action_version": action_version,
            "action_inputs": dict(action_inputs),
        }
    )
    return f"policy-{digest[:40]}"


def compile_policy_authorized_request(
    adapter_id: str,
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    delegation_policy_path: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    output_dir: str | Path,
    action_inputs: Mapping[str, str | Path] | None = None,
) -> dict[str, Any]:
    """Compile one exact typed request; do not execute or upgrade evidence."""
    adapter = _nonempty_text(adapter_id, "adapter_id")
    root = _resolve_dir(repository_root, "repository_root")
    mission_file = _resolve_file(mission_path, "mission_path")
    policy_file = _resolve_file(delegation_policy_path, "delegation_policy_path")
    run = _resolve_dir(research_run, "research_run")
    planning_registry_path = _resolve_file(
        action_registry_path, "action_registry_path"
    )

    mission_value, mission_raw, mission_sha = _snapshot_json(mission_file)
    mission = validate_research_mission(mission_value)
    autonomy = mission.get("autonomy_policy")
    if (
        not isinstance(autonomy, Mapping)
        or autonomy.get("typed_computational_actions") != "explicit_request"
    ):
        raise PolicyRequestCompilerError(
            "bounded request compilation requires explicit-request mission policy"
        )
    policy, policy_binding = _load_delegation_policy(
        policy_file,
        mission_path=mission_file,
        mission_sha256=mission_sha,
        adapter_id=adapter,
    )

    planning_registry_before = load_action_registry(
        planning_registry_path,
        repository_root=root,
    )
    planning_file_sha_before = _file_sha256(planning_registry_path)
    state_before = load_research_state(run)
    ledger_before = _sha256_text(
        state_before.get("ledger_sha256"), "research_state.ledger_sha256"
    )
    authorization = assess_current_action_authorization(
        adapter,
        repository_root=root,
        research_run=run,
        action_registry_path=planning_registry_path,
    )
    (
        action_type,
        action_version,
        spec,
        execution_registry,
        execution_registry_path,
        selected,
    ) = _verify_selected_action(
        authorization,
        repository_root=root,
        planning_registry_path=planning_registry_path,
        policy=policy,
    )
    resolved_inputs = _resolve_action_inputs(spec, action_inputs)

    # Re-read mutable authority immediately before compilation. A compiled request is
    # not execution authority, but stale planner/ledger state should still fail early.
    state_after = load_research_state(run)
    ledger_after = _sha256_text(
        state_after.get("ledger_sha256"), "research_state.ledger_sha256"
    )
    if ledger_after != ledger_before:
        raise PolicyRequestCompilerError(
            "research ledger changed during request compilation"
        )
    planning_registry_after = load_action_registry(
        planning_registry_path,
        repository_root=root,
    )
    planning_file_sha_after = _file_sha256(planning_registry_path)
    if (
        planning_registry_after["registry_sha256"]
        != planning_registry_before["registry_sha256"]
        or planning_file_sha_after != planning_file_sha_before
    ):
        raise PolicyRequestCompilerError(
            "planning registry changed during request compilation"
        )
    execution_file_sha = _file_sha256(execution_registry_path)
    selected_sha = _canonical_digest(dict(selected))
    action_id = _action_id(
        policy_sha256=str(policy_binding["sha256"]),
        mission_sha256=mission_sha,
        planning_registry_file_sha256=planning_file_sha_before,
        execution_registry_file_sha256=execution_file_sha,
        ledger_sha256=ledger_after,
        selected_action_sha256=selected_sha,
        action_type=action_type,
        action_version=action_version,
        action_inputs=resolved_inputs,
    )
    actions = state_after.get("actions")
    if not isinstance(actions, list):
        raise PolicyRequestCompilerError("research state actions are malformed")
    if any(
        isinstance(item, Mapping) and item.get("action_id") == action_id
        for item in actions
    ):
        raise PolicyRequestCompilerError(
            "deterministic policy action_id already exists in research ledger"
        )

    request: dict[str, Any] = {
        "schema_version": "1.0",
        "action_id": action_id,
        "action_type": action_type,
        "research_run": str(run),
        **resolved_inputs,
        "registry": str(execution_registry_path),
        "repository_root": str(root),
        "expected_registry_sha256": execution_registry["registry_sha256"],
    }
    request_raw = _canonical_json_bytes(request)
    request_sha = hashlib.sha256(request_raw).hexdigest()

    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise PolicyRequestCompilerError(f"output_dir already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent)
    )
    request_path = temporary / "execution_request.json"
    manifest_path = temporary / "policy_request_manifest.json"
    final_request_path = output / request_path.name
    final_manifest_path = output / manifest_path.name
    try:
        request_path.write_bytes(request_raw)
        manifest: dict[str, Any] = {
            "schema_version": POLICY_REQUEST_SCHEMA_VERSION,
            "compiler_policy_version": POLICY_REQUEST_COMPILER_VERSION,
            "compilation_status": "compiled_bounded_local_request_not_executed",
            "adapter_id": adapter,
            "policy_binding": dict(policy_binding),
            "mission_binding": {
                "path": str(mission_file),
                "sha256": mission_sha,
                "bytes": len(mission_raw),
            },
            "research_state_binding": {
                "research_run": str(run),
                "ledger_sha256": ledger_after,
            },
            "planning_registry_binding": {
                "path": str(planning_registry_path),
                "registry_id": planning_registry_after["registry_id"],
                "registry_sha256": planning_registry_after["registry_sha256"],
                "file_sha256": planning_file_sha_after,
            },
            "execution_registry_binding": {
                "path": str(execution_registry_path),
                "registry_id": execution_registry["registry_id"],
                "registry_sha256": execution_registry["registry_sha256"],
                "file_sha256": execution_file_sha,
            },
            "selected_action_binding": {
                "sha256": selected_sha,
                "action_type": action_type,
                "action_version": action_version,
                "category": spec["category"],
                "cost_units": spec["cost_units"],
            },
            "request_binding": {
                "path": str(final_request_path),
                "sha256": request_sha,
                "bytes": len(request_raw),
            },
            "action_inputs": dict(resolved_inputs),
            "registry_input_aliases": dict(spec["input_aliases"]),
            "autonomy_boundary": {
                "request_authorship_delegated": True,
                "execution_authorized_by_compiler": False,
                "human_acknowledgement_generated": False,
                "network_access_authorized": False,
                "physical_experiment_execution_authorized": False,
                "generic_command_execution_authorized": False,
                "model_fitting_authorized": False,
                "scientific_evidence_upgraded": False,
            },
        }
        manifest_path.write_bytes(_canonical_json_bytes(manifest))
        os.replace(temporary, output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return {
        **manifest,
        "manifest_binding": {
            "path": str(final_manifest_path),
            "sha256": hashlib.sha256(final_manifest_path.read_bytes()).hexdigest(),
        },
    }


__all__ = [
    "DELEGATION_POLICY_SCHEMA_VERSION",
    "POLICY_REQUEST_COMPILER_VERSION",
    "POLICY_REQUEST_SCHEMA_VERSION",
    "PolicyRequestCompilerError",
    "PolicyRequestInputBindingRequired",
    "compile_policy_authorized_request",
]
