"""Strict deterministic action registry for bounded autonomous research loops."""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any

from .kernel import ResearchLoopError

ACTION_REGISTRY_SCHEMA_VERSION = "1.0"
_ALLOWED_AVAILABILITY = {"available", "planned"}
_ALLOWED_BINDING_KINDS = {"installed_command", "source_script"}
_TOP_LEVEL_KEYS = {"schema_version", "registry_id", "domain", "actions"}
_ACTION_KEYS = {
    "action_type",
    "version",
    "availability",
    "category",
    "scientific_purpose",
    "target_blockers",
    "preconditions",
    "required_inputs",
    "expected_outputs",
    "cost_units",
    "binding",
    "verifier_checks",
    "allowed_outcomes",
    "prohibited_effects",
}
_INPUT_KEYS = {"name", "kind", "required", "description"}
_OUTPUT_KEYS = {"path", "kind", "required", "description"}
_BINDING_KEYS = {"kind", "name", "path", "platform"}


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ResearchLoopError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _require_object(value: Any, *, field: str, exact_keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ResearchLoopError(f"{field} must be a JSON object")
    missing = sorted(exact_keys - set(value))
    unknown = sorted(set(value) - exact_keys)
    if missing:
        raise ResearchLoopError(f"{field} is missing required keys: {', '.join(missing)}")
    if unknown:
        raise ResearchLoopError(f"{field} has unknown keys: {', '.join(unknown)}")
    return value


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchLoopError(f"{field} must be a non-empty string")
    return value.strip()


def _require_unique_strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ResearchLoopError(f"{field} must be a JSON array")
    result = [_require_string(item, f"{field} item") for item in value]
    if len(set(result)) != len(result):
        raise ResearchLoopError(f"{field} must not contain duplicate values")
    return result


def _validate_io_records(value: Any, *, field: str, keys: set[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ResearchLoopError(f"{field} must be a JSON array")
    normalized: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, raw in enumerate(value):
        record = _require_object(raw, field=f"{field}[{index}]", exact_keys=keys)
        name_key = "name" if "name" in record else "path"
        name = _require_string(record[name_key], f"{field}[{index}].{name_key}")
        if name in names:
            raise ResearchLoopError(f"{field} contains duplicate {name_key}: {name}")
        names.add(name)
        if not isinstance(record["required"], bool):
            raise ResearchLoopError(f"{field}[{index}].required must be boolean")
        normalized_record = dict(record)
        normalized_record[name_key] = name
        normalized_record["kind"] = _require_string(
            record["kind"], f"{field}[{index}].kind"
        )
        normalized_record["description"] = _require_string(
            record["description"], f"{field}[{index}].description"
        )
        normalized.append(normalized_record)
    return normalized


def _installed_commands(repository_root: Path) -> set[str]:
    pyproject = repository_root / "pyproject.toml"
    if not pyproject.is_file():
        raise FileNotFoundError(f"pyproject.toml not found: {pyproject}")
    with pyproject.open("rb") as handle:
        payload = tomllib.load(handle)
    scripts = payload.get("project", {}).get("scripts", {})
    if not isinstance(scripts, dict):
        raise ResearchLoopError("project.scripts must be a TOML table")
    return {str(name) for name in scripts}


def _validate_binding(
    raw: Any,
    *,
    availability: str,
    action_type: str,
    repository_root: Path | None,
) -> dict[str, Any] | None:
    if availability == "planned":
        if raw is not None:
            raise ResearchLoopError(
                f"planned action {action_type} must not declare an execution binding"
            )
        return None
    if raw is None:
        raise ResearchLoopError(
            f"available action {action_type} must declare an execution binding"
        )
    binding = _require_object(
        raw, field=f"action {action_type} binding", exact_keys=_BINDING_KEYS
    )
    kind = _require_string(binding["kind"], f"action {action_type} binding.kind")
    if kind not in _ALLOWED_BINDING_KINDS:
        raise ResearchLoopError(
            f"action {action_type} binding kind must be one of: "
            + ", ".join(sorted(_ALLOWED_BINDING_KINDS))
        )
    name = binding["name"]
    path = binding["path"]
    platform = binding["platform"]
    for value, field in (
        (name, "name"),
        (path, "path"),
        (platform, "platform"),
    ):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ResearchLoopError(
                f"action {action_type} binding.{field} must be null or non-empty string"
            )

    if kind == "installed_command":
        command = _require_string(name, f"action {action_type} binding.name")
        if path is not None:
            raise ResearchLoopError(
                f"installed command action {action_type} must not declare binding.path"
            )
        if repository_root is not None and command not in _installed_commands(repository_root):
            raise ResearchLoopError(
                f"action {action_type} references undeclared installed command: {command}"
            )
    else:
        relative_path = _require_string(path, f"action {action_type} binding.path")
        if name is not None:
            raise ResearchLoopError(
                f"source script action {action_type} must not declare binding.name"
            )
        candidate = Path(relative_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ResearchLoopError(
                f"action {action_type} source script path must be repository-relative"
            )
        if repository_root is not None and not (repository_root / candidate).is_file():
            raise ResearchLoopError(
                f"action {action_type} source script does not exist: {relative_path}"
            )
    return {
        "kind": kind,
        "name": name,
        "path": path,
        "platform": platform,
    }


def validate_action_registry(
    value: Any,
    *,
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    """Validate a complete action registry without executing any action."""
    top = _require_object(value, field="action registry", exact_keys=_TOP_LEVEL_KEYS)
    if top["schema_version"] != ACTION_REGISTRY_SCHEMA_VERSION:
        raise ResearchLoopError(
            f"unsupported action registry schema_version: {top['schema_version']!r}"
        )
    root = Path(repository_root).resolve() if repository_root is not None else None
    registry_id = _require_string(top["registry_id"], "registry_id")
    domain = _require_string(top["domain"], "domain")
    if not isinstance(top["actions"], list) or not top["actions"]:
        raise ResearchLoopError("actions must be a non-empty JSON array")

    actions: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for index, raw in enumerate(top["actions"]):
        action = _require_object(
            raw, field=f"actions[{index}]", exact_keys=_ACTION_KEYS
        )
        action_type = _require_string(action["action_type"], f"actions[{index}].action_type")
        if action_type in identifiers:
            raise ResearchLoopError(f"duplicate action_type: {action_type}")
        identifiers.add(action_type)
        availability = _require_string(
            action["availability"], f"action {action_type} availability"
        )
        if availability not in _ALLOWED_AVAILABILITY:
            raise ResearchLoopError(
                f"action {action_type} availability must be one of: "
                + ", ".join(sorted(_ALLOWED_AVAILABILITY))
            )
        cost_units = action["cost_units"]
        if isinstance(cost_units, bool) or not isinstance(cost_units, int) or cost_units < 0:
            raise ResearchLoopError(
                f"action {action_type} cost_units must be a non-negative integer"
            )
        normalized = {
            "action_type": action_type,
            "version": _require_string(action["version"], f"action {action_type} version"),
            "availability": availability,
            "category": _require_string(action["category"], f"action {action_type} category"),
            "scientific_purpose": _require_string(
                action["scientific_purpose"], f"action {action_type} scientific_purpose"
            ),
            "target_blockers": _require_unique_strings(
                action["target_blockers"], f"action {action_type} target_blockers"
            ),
            "preconditions": _require_unique_strings(
                action["preconditions"], f"action {action_type} preconditions"
            ),
            "required_inputs": _validate_io_records(
                action["required_inputs"],
                field=f"action {action_type} required_inputs",
                keys=_INPUT_KEYS,
            ),
            "expected_outputs": _validate_io_records(
                action["expected_outputs"],
                field=f"action {action_type} expected_outputs",
                keys=_OUTPUT_KEYS,
            ),
            "cost_units": cost_units,
            "binding": _validate_binding(
                action["binding"],
                availability=availability,
                action_type=action_type,
                repository_root=root,
            ),
            "verifier_checks": _require_unique_strings(
                action["verifier_checks"], f"action {action_type} verifier_checks"
            ),
            "allowed_outcomes": _require_unique_strings(
                action["allowed_outcomes"], f"action {action_type} allowed_outcomes"
            ),
            "prohibited_effects": _require_unique_strings(
                action["prohibited_effects"], f"action {action_type} prohibited_effects"
            ),
        }
        if availability == "available" and not normalized["verifier_checks"]:
            raise ResearchLoopError(
                f"available action {action_type} must declare verifier checks"
            )
        actions.append(normalized)

    normalized_registry = {
        "schema_version": ACTION_REGISTRY_SCHEMA_VERSION,
        "registry_id": registry_id,
        "domain": domain,
        "actions": sorted(actions, key=lambda item: item["action_type"]),
    }
    return normalized_registry


def load_action_registry(
    path: str | Path,
    *,
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    registry_path = Path(path).expanduser().resolve(strict=True)
    try:
        with registry_path.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise ResearchLoopError(f"invalid action registry JSON: {exc}") from exc
    registry = validate_action_registry(value, repository_root=repository_root)
    registry["registry_sha256"] = hashlib.sha256(
        _canonical_json(registry).encode("utf-8")
    ).hexdigest()
    registry["registry_path"] = str(registry_path)
    registry["available_action_count"] = sum(
        action["availability"] == "available" for action in registry["actions"]
    )
    registry["planned_action_count"] = sum(
        action["availability"] == "planned" for action in registry["actions"]
    )
    return registry


def describe_action(registry: dict[str, Any], action_type: str) -> dict[str, Any]:
    requested = _require_string(action_type, "action_type")
    for action in registry["actions"]:
        if action["action_type"] == requested:
            return {
                "registry_id": registry["registry_id"],
                "registry_sha256": registry["registry_sha256"],
                **action,
            }
    raise ResearchLoopError(f"unknown action_type: {requested}")


def action_summaries(registry: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "action_type": action["action_type"],
            "version": action["version"],
            "availability": action["availability"],
            "category": action["category"],
            "cost_units": action["cost_units"],
            "scientific_purpose": action["scientific_purpose"],
        }
        for action in registry["actions"]
    ]
