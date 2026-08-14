from __future__ import annotations

from pathlib import Path

from materials_data_analyzer.research_loop import epistemic_multicycle as module


ROOT = Path(__file__).resolve().parents[1]


def _gate(directive: str, *, permitted: bool) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "adapter_id": "nasa-battery",
        "workstream_id": "nasa-battery",
        "graph_binding": {"path": "graph.json", "sha256": "a" * 64},
        "directive": {
            "directive": directive,
            "automatic_execution_permitted": permitted,
            "target_node_ids": ["h1"],
            "target_statuses": {"h1": "inconclusive"},
        },
    }


def test_falsified_target_stops_before_probe_or_request_consumption(monkeypatch) -> None:
    calls = {"cycle": 0}

    monkeypatch.setattr(
        module,
        "evaluate_epistemic_gate",
        lambda **_: _gate("stop_falsified_target", permitted=False),
    )

    def forbidden_cycle(*args, **kwargs):
        calls["cycle"] += 1
        raise AssertionError("research cycle must not run after verified falsification")

    monkeypatch.setattr(module, "run_research_cycle", forbidden_cycle)

    result = module.run_epistemically_bounded_multicycle(
        "nasa-battery",
        repository_root=ROOT,
        mission_path=ROOT / "configs/research/autonomous_materials_research_mission.v1.json",
        graph_path=ROOT / "configs/research/autonomous_materials_research_mission.v1.json",
        epistemic_workstream_id="nasa-battery",
        epistemic_target_node_ids=["h1"],
        max_cycles=3,
    )

    assert calls["cycle"] == 0
    assert result["program_status"] == "epistemic_falsification_stop"
    assert result["actions_executed"] == 0
    assert result["requests_consumed"] == 0
    assert result["cycles_started"] == 1


def test_contested_target_stops_before_probe(monkeypatch) -> None:
    monkeypatch.setattr(
        module,
        "evaluate_epistemic_gate",
        lambda **_: _gate("manual_discrimination_required", permitted=False),
    )
    monkeypatch.setattr(
        module,
        "run_research_cycle",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("contested target must stop before execution probe")
        ),
    )

    result = module.run_epistemically_bounded_multicycle(
        "nasa-battery",
        repository_root=ROOT,
        mission_path=ROOT / "configs/research/autonomous_materials_research_mission.v1.json",
        graph_path=ROOT / "configs/research/autonomous_materials_research_mission.v1.json",
        epistemic_workstream_id="nasa-battery",
        epistemic_target_node_ids=["h1"],
        max_cycles=2,
    )
    assert result["program_status"] == "epistemic_discrimination_required"
    assert result["actions_executed"] == 0


def test_provisional_support_requires_closeout_before_more_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(
        module,
        "evaluate_epistemic_gate",
        lambda **_: _gate("domain_closeout_required", permitted=False),
    )
    monkeypatch.setattr(
        module,
        "run_research_cycle",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("provisional support must stop before execution probe")
        ),
    )

    result = module.run_epistemically_bounded_multicycle(
        "nasa-battery",
        repository_root=ROOT,
        mission_path=ROOT / "configs/research/autonomous_materials_research_mission.v1.json",
        graph_path=ROOT / "configs/research/autonomous_materials_research_mission.v1.json",
        epistemic_workstream_id="nasa-battery",
        epistemic_target_node_ids=["h1"],
        max_cycles=2,
    )
    assert result["program_status"] == "epistemic_domain_closeout_required"
    assert result["actions_executed"] == 0


def test_inconclusive_target_reaches_existing_explicit_request_boundary(monkeypatch) -> None:
    monkeypatch.setattr(
        module,
        "evaluate_epistemic_gate",
        lambda **_: _gate("continue_discriminating_research", permitted=True),
    )

    def probe(*args, **kwargs):
        assert kwargs["request_path"] is None
        return {
            "cycle_status": "explicit_request_required",
            "authorization": {
                "selected_action": {
                    "action_type": "target_reference_sensitivity",
                    "action_version": "0.1-planned",
                }
            },
            "before_planning_state": {
                "adapter_id": "nasa-battery",
                "current_blocker": {"code": "b"},
                "evidence_gap": {"status": "missing"},
                "selected_action": {
                    "action_type": "target_reference_sensitivity",
                    "action_version": "0.1-planned",
                },
                "stop_state": {"status": "continue"},
                "budget": {},
                "evidence_bindings": [],
            },
            "before_transition": {"transition_type": "action_pending_authorization"},
        }

    monkeypatch.setattr(module, "run_research_cycle", probe)

    result = module.run_epistemically_bounded_multicycle(
        "nasa-battery",
        repository_root=ROOT,
        mission_path=ROOT / "configs/research/autonomous_materials_research_mission.v1.json",
        graph_path=ROOT / "configs/research/autonomous_materials_research_mission.v1.json",
        epistemic_workstream_id="nasa-battery",
        epistemic_target_node_ids=["h1"],
        max_cycles=2,
    )

    assert result["program_status"] == "predeclared_request_required"
    assert result["actions_executed"] == 0
    assert result["cycles"][0]["probe_status"] == "explicit_request_required"
    assert (
        result["cycles"][0]["epistemic_gate"]["directive"]["directive"]
        == "continue_discriminating_research"
    )
