"""Resumable control-plane orchestration for bounded autonomous research episodes.

This module deliberately does not implement a second scientific authority.  It persists
exact references to one-step planner/executor results using :mod:`research_episode` and
lets a caller resume after process interruption without replaying completed iterations.
Scientific promotion remains the responsibility of the existing authenticated transition
and intake layers.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .research_episode import (
    ResearchEpisodeError,
    checkpoint_episode,
    create_research_episode,
    record_episode_iteration,
    resume_episode,
)

PERSISTENT_AUTONOMOUS_EPISODE_POLICY_VERSION = "1.0"
_TERMINAL = {"concluded", "stopped"}


class PersistentAutonomousEpisodeError(ResearchEpisodeError):
    """Raised when a persistent episode step violates the control-plane contract."""


StepHandler = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PersistentAutonomousEpisodeError(f"{field} must be non-empty text")
    if value != value.strip():
        raise PersistentAutonomousEpisodeError(f"{field} must not contain edge whitespace")
    return value


def _text_list(value: object, field: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise PersistentAutonomousEpisodeError(f"{field} must be a sequence of text")
    result: list[str] = []
    for raw in value:
        text = _text(raw, f"{field} item")
        if text in result:
            raise PersistentAutonomousEpisodeError(f"{field} must not contain duplicates")
        result.append(text)
    return result


def open_or_create_episode(
    checkpoint_path: Path,
    *,
    episode_id: str,
    research_question: str,
    mission_id: str,
    objectives: Sequence[str],
    max_iterations: int,
    cost_budget: float,
) -> dict[str, Any]:
    """Resume an exact checkpoint or atomically create it when absent."""
    target = Path(checkpoint_path)
    if target.exists():
        state = resume_episode(target)
        expected = {
            "episode_id": _text(episode_id, "episode_id"),
            "research_question": _text(research_question, "research_question"),
            "mission_id": _text(mission_id, "mission_id"),
            "objectives": list(objectives),
            "max_iterations": max_iterations,
            "cost_budget": float(cost_budget),
        }
        actual = {
            "episode_id": state["episode_id"],
            "research_question": state["research_question"],
            "mission_id": state["mission_id"],
            "objectives": state["objectives"],
            "max_iterations": state["budgets"]["max_iterations"],
            "cost_budget": float(state["budgets"]["cost_budget"]),
        }
        if actual != expected:
            raise PersistentAutonomousEpisodeError(
                "existing checkpoint identity or immutable budget differs from request"
            )
        return state

    state = create_research_episode(
        episode_id=episode_id,
        research_question=research_question,
        mission_id=mission_id,
        objectives=objectives,
        max_iterations=max_iterations,
        cost_budget=cost_budget,
    )
    checkpoint_episode(target, state)
    return state


def validate_step_result(value: object) -> dict[str, Any]:
    """Validate one deterministic autonomous step without interpreting its science."""
    if not isinstance(value, Mapping):
        raise PersistentAutonomousEpisodeError("step result must be an object")
    expected = {
        "planner_record",
        "artifact_refs",
        "evidence_refs",
        "unresolved_gaps",
        "review_queue",
        "blockers",
        "cost_units",
        "iteration_status",
        "episode_status",
        "conclusion",
    }
    if set(value) != expected:
        missing = sorted(expected - set(value))
        unknown = sorted(set(value) - expected)
        raise PersistentAutonomousEpisodeError(
            f"step result keys mismatch; missing={missing}, unknown={unknown}"
        )
    planner_record = value["planner_record"]
    if not isinstance(planner_record, Mapping):
        raise PersistentAutonomousEpisodeError("planner_record must be an object")
    cost = value["cost_units"]
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
        raise PersistentAutonomousEpisodeError("cost_units must be non-negative")
    episode_status = _text(value["episode_status"], "episode_status")
    if episode_status not in {"active", "blocked", "concluded", "stopped"}:
        raise PersistentAutonomousEpisodeError("invalid episode_status")
    conclusion = value["conclusion"]
    if conclusion is not None and not isinstance(conclusion, Mapping):
        raise PersistentAutonomousEpisodeError("conclusion must be null or an object")
    if episode_status == "concluded" and conclusion is None:
        raise PersistentAutonomousEpisodeError("concluded step requires a conclusion")
    return {
        "planner_record": dict(planner_record),
        "artifact_refs": _text_list(value["artifact_refs"], "artifact_refs"),
        "evidence_refs": _text_list(value["evidence_refs"], "evidence_refs"),
        "unresolved_gaps": _text_list(value["unresolved_gaps"], "unresolved_gaps"),
        "review_queue": _text_list(value["review_queue"], "review_queue"),
        "blockers": _text_list(value["blockers"], "blockers"),
        "cost_units": float(cost),
        "iteration_status": _text(value["iteration_status"], "iteration_status"),
        "episode_status": episode_status,
        "conclusion": None if conclusion is None else dict(conclusion),
    }


def apply_persistent_step(
    checkpoint_path: Path,
    state: Mapping[str, Any],
    step_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Commit one validated step and checkpoint it before returning."""
    result = validate_step_result(step_result)
    next_state = record_episode_iteration(
        state,
        planner_record=result["planner_record"],
        artifact_refs=result["artifact_refs"],
        evidence_refs=result["evidence_refs"],
        unresolved_gaps=result["unresolved_gaps"],
        review_queue=result["review_queue"],
        blockers=result["blockers"],
        cost_units=result["cost_units"],
        status=result["iteration_status"],
        episode_status=result["episode_status"],
        conclusion=result["conclusion"],
    )
    checkpoint_episode(Path(checkpoint_path), next_state)
    return next_state


def run_persistent_episode(
    checkpoint_path: Path,
    *,
    episode_id: str,
    research_question: str,
    mission_id: str,
    objectives: Sequence[str],
    max_iterations: int,
    cost_budget: float,
    step_handler: StepHandler,
) -> dict[str, Any]:
    """Run bounded steps, resuming from the last committed checkpoint.

    The handler receives the current verified episode state.  A completed step is persisted
    before another handler invocation.  Restarting this function therefore resumes at the
    next iteration rather than replaying committed work.
    """
    state = open_or_create_episode(
        checkpoint_path,
        episode_id=episode_id,
        research_question=research_question,
        mission_id=mission_id,
        objectives=objectives,
        max_iterations=max_iterations,
        cost_budget=cost_budget,
    )
    while state["status"] not in _TERMINAL:
        if state["iteration"] >= state["budgets"]["max_iterations"]:
            break
        if float(state["budgets"]["cost_consumed"]) >= float(
            state["budgets"]["cost_budget"]
        ):
            break
        step = step_handler(state)
        state = apply_persistent_step(checkpoint_path, state, step)
        if state["status"] == "blocked":
            break
    return {
        "policy_version": PERSISTENT_AUTONOMOUS_EPISODE_POLICY_VERSION,
        "episode": state,
        "checkpoint_path": str(Path(checkpoint_path)),
        "resumable": state["status"] not in _TERMINAL,
        "scientific_status_changed_by_persistence": False,
        "physical_experiment_executed": False,
    }


__all__ = [
    "PERSISTENT_AUTONOMOUS_EPISODE_POLICY_VERSION",
    "PersistentAutonomousEpisodeError",
    "apply_persistent_step",
    "open_or_create_episode",
    "run_persistent_episode",
    "validate_step_result",
]
