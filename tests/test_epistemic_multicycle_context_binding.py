from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import epistemic_multicycle as module


def _gate(context_path: Path) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "adapter_id": "nasa-battery",
        "workstream_id": "nasa-battery",
        "runtime_context_binding": {
            "path": str(context_path.resolve()),
            "sha256": hashlib.sha256(context_path.read_bytes()).hexdigest(),
        },
        "graph_binding": {"path": "graph.json", "sha256": "a" * 64},
        "directive": {
            "directive": "continue_discriminating_research",
            "automatic_execution_permitted": True,
            "target_node_ids": ["h1"],
            "target_statuses": {"h1": "inconclusive"},
        },
    }


def _write_context(path: Path, run: Path, registry: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "workstreams": {
                    "nasa-battery": {
                        "research_run": str(run.resolve()),
                        "action_registry_path": str(registry.resolve()),
                    }
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_runtime_context_mismatch_fails_before_planner_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected_run = tmp_path / "expected-run"
    actual_run = tmp_path / "actual-run"
    expected_run.mkdir()
    actual_run.mkdir()
    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")
    context = tmp_path / "context.json"
    _write_context(context, expected_run, registry)

    monkeypatch.setattr(module, "evaluate_epistemic_gate", lambda **_: _gate(context))
    calls = 0

    def forbidden_cycle(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("planner probe must not run with mismatched gate/execution context")

    monkeypatch.setattr(module, "run_research_cycle", forbidden_cycle)

    with pytest.raises(module.EpistemicMultiCycleError, match="does not match"):
        module.run_epistemically_bounded_multicycle(
            "nasa-battery",
            repository_root=tmp_path,
            mission_path=tmp_path / "mission.json",
            graph_path=tmp_path / "graph.json",
            epistemic_workstream_id="nasa-battery",
            epistemic_target_node_ids=["h1"],
            runtime_context_path=context,
            research_run=actual_run,
            action_registry_path=registry,
            max_cycles=1,
        )

    assert calls == 0


def test_runtime_context_bytes_must_still_match_gate_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")
    context = tmp_path / "context.json"
    _write_context(context, run, registry)
    gate = _gate(context)
    context.write_text(
        json.dumps({"schema_version": "1.0", "workstreams": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "evaluate_epistemic_gate", lambda **_: gate)
    monkeypatch.setattr(
        module,
        "run_research_cycle",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("planner probe must not run after runtime-context mutation")
        ),
    )

    with pytest.raises(module.EpistemicMultiCycleError, match="changed after epistemic gate"):
        module.run_epistemically_bounded_multicycle(
            "nasa-battery",
            repository_root=tmp_path,
            mission_path=tmp_path / "mission.json",
            graph_path=tmp_path / "graph.json",
            epistemic_workstream_id="nasa-battery",
            epistemic_target_node_ids=["h1"],
            runtime_context_path=context,
            research_run=run,
            action_registry_path=registry,
            max_cycles=1,
        )
