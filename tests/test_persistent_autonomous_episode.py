from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop.persistent_autonomous_episode import (
    PersistentAutonomousEpisodeError,
    open_or_create_episode,
    run_persistent_episode,
)
from materials_data_analyzer.research_loop.research_episode import resume_episode


def _step(state: dict[str, Any]) -> dict[str, Any]:
    iteration = int(state["iteration"]) + 1
    concluded = iteration >= 2
    return {
        "planner_record": {"action": f"action-{iteration}"},
        "artifact_refs": [f"artifact:{iteration}"],
        "evidence_refs": [f"evidence:{iteration}"],
        "unresolved_gaps": [] if concluded else ["gap:remaining"],
        "review_queue": [],
        "blockers": [],
        "cost_units": 1.0,
        "iteration_status": "completed",
        "episode_status": "concluded" if concluded else "active",
        "conclusion": {"status": "supported"} if concluded else None,
    }


def test_persistent_episode_commits_each_step_and_resumes(tmp_path: Path) -> None:
    checkpoint = tmp_path / "episode.json"
    result = run_persistent_episode(
        checkpoint,
        episode_id="episode-1",
        research_question="Does the evidence support the hypothesis?",
        mission_id="mission-1",
        objectives=["test hypothesis"],
        max_iterations=5,
        cost_budget=10.0,
        step_handler=_step,
    )
    assert result["episode"]["status"] == "concluded"
    assert result["episode"]["iteration"] == 2
    assert result["scientific_status_changed_by_persistence"] is False
    persisted = resume_episode(checkpoint)
    assert persisted["iteration"] == 2
    assert persisted["evidence_refs"] == ["evidence:1", "evidence:2"]

    calls = 0

    def must_not_run(state: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        raise AssertionError("terminal checkpoint must not replay a completed step")

    again = run_persistent_episode(
        checkpoint,
        episode_id="episode-1",
        research_question="Does the evidence support the hypothesis?",
        mission_id="mission-1",
        objectives=["test hypothesis"],
        max_iterations=5,
        cost_budget=10.0,
        step_handler=must_not_run,
    )
    assert again["episode"]["iteration"] == 2
    assert calls == 0


def test_resume_rejects_changed_immutable_identity(tmp_path: Path) -> None:
    checkpoint = tmp_path / "episode.json"
    open_or_create_episode(
        checkpoint,
        episode_id="episode-1",
        research_question="Question A",
        mission_id="mission-1",
        objectives=["objective"],
        max_iterations=3,
        cost_budget=4.0,
    )
    with pytest.raises(PersistentAutonomousEpisodeError):
        open_or_create_episode(
            checkpoint,
            episode_id="episode-1",
            research_question="Question B",
            mission_id="mission-1",
            objectives=["objective"],
            max_iterations=3,
            cost_budget=4.0,
        )
