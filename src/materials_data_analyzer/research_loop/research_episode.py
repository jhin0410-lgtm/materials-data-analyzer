"""Persistent, checksum-bound research episodes for resumable autonomous inquiry.

An episode is a control-plane checkpoint. It records references to planner/evidence
artifacts and unresolved blockers but never reinterprets those artifacts or upgrades a
scientific claim. Checkpoints are canonical-JSON hashed and atomically replaced.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .kernel import ResearchLoopError

RESEARCH_EPISODE_SCHEMA_VERSION = "1.0"
RESEARCH_EPISODE_CHECKPOINT_SCHEMA_VERSION = "1.0"
_ALLOWED_STATUS = {"active", "blocked", "concluded", "stopped"}


class ResearchEpisodeError(ResearchLoopError):
    """Raised when an episode checkpoint cannot be trusted or resumed."""


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchEpisodeError(f"{field} must be non-empty text")
    if value != value.strip():
        raise ResearchEpisodeError(f"{field} must not contain edge whitespace")
    return value


def _unique_text_list(
    value: object,
    field: str,
    *,
    allow_empty: bool = True,
) -> list[str]:
    if not isinstance(value, list):
        raise ResearchEpisodeError(f"{field} must be a list")
    if not allow_empty and not value:
        raise ResearchEpisodeError(f"{field} must not be empty")
    result: list[str] = []
    for raw in value:
        text = _text(raw, f"{field} item")
        if text in result:
            raise ResearchEpisodeError(f"{field} must not contain duplicates")
        result.append(text)
    return result


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ResearchEpisodeError(
            "episode state must be canonical-JSON serializable"
        ) from exc


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha(value: object, field: str) -> str:
    text = _text(value, field).lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ResearchEpisodeError(f"{field} must be lowercase SHA-256")
    return text


def create_research_episode(
    *,
    episode_id: str,
    research_question: str,
    mission_id: str,
    objectives: Sequence[str],
    max_iterations: int,
    cost_budget: float,
) -> dict[str, Any]:
    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, int)
        or max_iterations < 1
    ):
        raise ResearchEpisodeError("max_iterations must be a positive integer")
    if (
        isinstance(cost_budget, bool)
        or not isinstance(cost_budget, (int, float))
        or cost_budget < 0
    ):
        raise ResearchEpisodeError("cost_budget must be non-negative")
    objective_list = [_text(item, "objective") for item in objectives]
    if not objective_list or len(set(objective_list)) != len(objective_list):
        raise ResearchEpisodeError("objectives must be non-empty and unique")
    state = {
        "schema_version": RESEARCH_EPISODE_SCHEMA_VERSION,
        "episode_id": _text(episode_id, "episode_id"),
        "research_question": _text(research_question, "research_question"),
        "mission_id": _text(mission_id, "mission_id"),
        "objectives": objective_list,
        "status": "active",
        "iteration": 0,
        "budgets": {
            "max_iterations": max_iterations,
            "cost_budget": float(cost_budget),
            "cost_consumed": 0.0,
        },
        "hypothesis_refs": [],
        "evidence_refs": [],
        "unresolved_gaps": [],
        "review_queue": [],
        "action_history": [],
        "blockers": [],
        "conclusion": None,
        "parent_checkpoint_sha256": None,
    }
    return validate_episode_state(state)


def validate_episode_state(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ResearchEpisodeError("episode state must be an object")
    required = {
        "schema_version",
        "episode_id",
        "research_question",
        "mission_id",
        "objectives",
        "status",
        "iteration",
        "budgets",
        "hypothesis_refs",
        "evidence_refs",
        "unresolved_gaps",
        "review_queue",
        "action_history",
        "blockers",
        "conclusion",
        "parent_checkpoint_sha256",
    }
    unknown = sorted(set(value) - required)
    missing = sorted(required - set(value))
    if missing or unknown:
        raise ResearchEpisodeError(
            f"episode keys mismatch; missing={missing}, unknown={unknown}"
        )
    if value["schema_version"] != RESEARCH_EPISODE_SCHEMA_VERSION:
        raise ResearchEpisodeError("unsupported episode schema_version")
    for field in ("episode_id", "research_question", "mission_id"):
        _text(value[field], field)
    _unique_text_list(value["objectives"], "objectives", allow_empty=False)
    status = _text(value["status"], "status")
    if status not in _ALLOWED_STATUS:
        raise ResearchEpisodeError(f"status must be one of {sorted(_ALLOWED_STATUS)}")
    iteration = value["iteration"]
    if isinstance(iteration, bool) or not isinstance(iteration, int) or iteration < 0:
        raise ResearchEpisodeError("iteration must be a non-negative integer")
    budgets = value["budgets"]
    if not isinstance(budgets, dict) or set(budgets) != {
        "max_iterations",
        "cost_budget",
        "cost_consumed",
    }:
        raise ResearchEpisodeError("budgets has invalid keys")
    max_iterations = budgets["max_iterations"]
    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, int)
        or max_iterations < 1
    ):
        raise ResearchEpisodeError("budgets.max_iterations must be positive")
    for field in ("cost_budget", "cost_consumed"):
        raw = budgets[field]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw < 0:
            raise ResearchEpisodeError(f"budgets.{field} must be non-negative")
    if float(budgets["cost_consumed"]) > float(budgets["cost_budget"]):
        raise ResearchEpisodeError("cost_consumed cannot exceed cost_budget")
    for field in (
        "hypothesis_refs",
        "evidence_refs",
        "unresolved_gaps",
        "review_queue",
        "blockers",
    ):
        _unique_text_list(value[field], field)
    history = value["action_history"]
    if not isinstance(history, list):
        raise ResearchEpisodeError("action_history must be a list")
    for index, item in enumerate(history):
        if not isinstance(item, dict) or set(item) != {
            "iteration",
            "planner_record_sha256",
            "artifact_refs",
            "cost_units",
            "status",
        }:
            raise ResearchEpisodeError(f"action_history[{index}] has invalid keys")
        if item["iteration"] != index + 1:
            raise ResearchEpisodeError(
                "action_history iteration sequence is not contiguous"
            )
        _sha(item["planner_record_sha256"], "planner_record_sha256")
        _unique_text_list(item["artifact_refs"], "artifact_refs")
        cost = item["cost_units"]
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
            raise ResearchEpisodeError("action_history cost_units must be non-negative")
        _text(item["status"], "action_history status")
    parent = value["parent_checkpoint_sha256"]
    if parent is not None:
        _sha(parent, "parent_checkpoint_sha256")
    conclusion = value["conclusion"]
    if conclusion is not None and not isinstance(conclusion, Mapping):
        raise ResearchEpisodeError("conclusion must be null or an object")
    return json.loads(_canonical_bytes(value).decode("utf-8"))


def record_episode_iteration(
    state: Mapping[str, Any],
    *,
    planner_record: object,
    artifact_refs: Sequence[str] = (),
    cost_units: float = 0.0,
    status: str = "completed",
    evidence_refs: Sequence[str] = (),
    unresolved_gaps: Sequence[str] | None = None,
    review_queue: Sequence[str] | None = None,
    blockers: Sequence[str] | None = None,
    episode_status: str | None = None,
    conclusion: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    current = validate_episode_state(dict(state))
    parent_checkpoint_sha = canonical_sha256(current)
    if current["status"] in {"concluded", "stopped"}:
        raise ResearchEpisodeError("terminal episode cannot record another iteration")
    next_iteration = current["iteration"] + 1
    if next_iteration > current["budgets"]["max_iterations"]:
        raise ResearchEpisodeError("episode max_iterations exhausted")
    if (
        isinstance(cost_units, bool)
        or not isinstance(cost_units, (int, float))
        or cost_units < 0
    ):
        raise ResearchEpisodeError("cost_units must be non-negative")
    new_cost = float(current["budgets"]["cost_consumed"]) + float(cost_units)
    if new_cost > float(current["budgets"]["cost_budget"]):
        raise ResearchEpisodeError("episode cost budget would be exceeded")
    current["iteration"] = next_iteration
    current["budgets"]["cost_consumed"] = new_cost
    current["action_history"].append(
        {
            "iteration": next_iteration,
            "planner_record_sha256": canonical_sha256(planner_record),
            "artifact_refs": [_text(item, "artifact_ref") for item in artifact_refs],
            "cost_units": float(cost_units),
            "status": _text(status, "iteration status"),
        }
    )
    for ref in evidence_refs:
        text = _text(ref, "evidence_ref")
        if text not in current["evidence_refs"]:
            current["evidence_refs"].append(text)
    for field, replacement in (
        ("unresolved_gaps", unresolved_gaps),
        ("review_queue", review_queue),
        ("blockers", blockers),
    ):
        if replacement is not None:
            current[field] = [_text(item, field) for item in replacement]
    if episode_status is not None:
        if episode_status not in _ALLOWED_STATUS:
            raise ResearchEpisodeError("invalid episode_status")
        current["status"] = episode_status
    if conclusion is not None:
        current["conclusion"] = json.loads(
            _canonical_bytes(conclusion).decode("utf-8")
        )
    current["parent_checkpoint_sha256"] = parent_checkpoint_sha
    return validate_episode_state(current)


def checkpoint_episode(path: Path, state: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_episode_state(dict(state))
    state_sha = canonical_sha256(validated)
    envelope = {
        "checkpoint_schema_version": RESEARCH_EPISODE_CHECKPOINT_SCHEMA_VERSION,
        "state_sha256": state_sha,
        "state": validated,
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    try:
        tmp.write_bytes(_canonical_bytes(envelope) + b"\n")
        os.replace(tmp, target)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise ResearchEpisodeError(
            f"could not write episode checkpoint: {target}"
        ) from exc
    return envelope


def resume_episode(path: Path) -> dict[str, Any]:
    target = Path(path)
    try:
        raw = target.read_bytes()
        envelope = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchEpisodeError(
            f"could not read episode checkpoint: {target}"
        ) from exc
    if not isinstance(envelope, dict) or set(envelope) != {
        "checkpoint_schema_version",
        "state_sha256",
        "state",
    }:
        raise ResearchEpisodeError("episode checkpoint envelope is invalid")
    if (
        envelope["checkpoint_schema_version"]
        != RESEARCH_EPISODE_CHECKPOINT_SCHEMA_VERSION
    ):
        raise ResearchEpisodeError("unsupported checkpoint schema_version")
    state = validate_episode_state(envelope["state"])
    expected = _sha(envelope["state_sha256"], "state_sha256")
    actual = canonical_sha256(state)
    if actual != expected:
        raise ResearchEpisodeError("episode state SHA-256 mismatch")
    return state


__all__ = [
    "RESEARCH_EPISODE_CHECKPOINT_SCHEMA_VERSION",
    "RESEARCH_EPISODE_SCHEMA_VERSION",
    "ResearchEpisodeError",
    "canonical_sha256",
    "checkpoint_episode",
    "create_research_episode",
    "record_episode_iteration",
    "resume_episode",
    "validate_episode_state",
]
