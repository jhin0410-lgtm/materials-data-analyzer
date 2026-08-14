from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer import research_program_cli
from materials_data_analyzer.research_loop import policy_authorized_closed_loop as module


def _write_json(path: Path, value: object) -> Path:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_graph(path: Path) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "1.0",
            "graph_id": "graph-v1",
            "research_scope": "bounded test scope",
            "nodes": [
                {
                    "node_id": "h1",
                    "node_type": "hypothesis",
                    "statement": "A bounded hypothesis under test.",
                    "metadata": {"claim_scope": "structural"},
                }
            ],
            "edges": [],
        },
    )


def _program_state() -> dict[str, object]:
    return {"workstreams": []}


def _record(
    *,
    record_id: str = "r1",
    request_id: str = "q1",
    action_type: str = "target_reference_sensitivity",
    version: str = "1.0",
    node_id: str = "result-1",
) -> dict[str, object]:
    return {
        "record_id": record_id,
        "request_id": request_id,
        "expected_action_type": action_type,
        "expected_action_version": version,
        "target_node_id": "h1",
        "result_node_id": node_id,
        "result_node_type": "analysis",
        "result_origin": "authorized_local_analysis",
        "action_class": "sensitivity_analysis",
        "statement": "The authorized local analysis completed.",
        "limitations": ["Execution success is not scientific verification."],
    }


def test_record_only_transition_appends_result_without_directional_inference(
    tmp_path: Path,
) -> None:
    graph = _base_graph(tmp_path / "graph.json")
    report = _write_json(tmp_path / "action_result.json", {"status": "complete"})
    request_path = _write_json(tmp_path / "request.json", {"action_id": "a1"})
    request = {"request_id": "q1", "path": str(request_path), "sha256": _sha(request_path)}
    execution = {
        "action_type": "target_reference_sensitivity",
        "action_version": "1.0",
        "ledger_action_id": "a1",
        "action_report": str(report),
        "request_binding": {
            "path": str(request_path),
            "sha256": request["sha256"],
            "size_bytes": request_path.stat().st_size,
        },
        "scientific_evidence_upgraded_by_orchestrator": False,
        "network_access_initiated_by_orchestrator": False,
    }

    result = module.apply_record_only_action_result(
        base_graph_path=graph,
        program_state=_program_state(),
        artifact_root=tmp_path,
        output_dir=tmp_path / "out",
        record=_record(),
        request=request,
        execution=execution,
    )

    successor = json.loads(Path(result["successor_graph"]["path"]).read_text("utf-8"))
    assert successor["nodes"][-1]["node_id"] == "result-1"
    assert successor["edges"][-1]["relation"] == "tests"
    assert not any(
        edge["relation"] in {"supports", "contradicts", "falsifies"}
        for edge in successor["edges"]
    )
    assert result["target_before"]["status"] == "inconclusive"
    assert result["target_after"]["status"] == "inconclusive"
    assert result["directional_inference_generated"] is False
    assert result["domain_verification_generated"] is False
    assert result["autonomy_boundary"]["scientific_status_upgraded"] is False


def test_result_record_plan_rejects_external_or_physical_result_semantics(
    tmp_path: Path,
) -> None:
    request = _write_json(tmp_path / "request.json", {"action_id": "a1"})
    queue = {
        "adapter_id": "nasa-battery",
        "requests": [
            {
                "request_id": "q1",
                "path": str(request),
                "sha256": _sha(request),
                "expected_action_type": "target_reference_sensitivity",
                "expected_action_version": "1.0",
            }
        ],
    }
    bad = _record()
    bad["result_node_type"] = "experiment"
    bad["result_origin"] = "external_physical_experiment"
    bad["action_class"] = "physical_experiment"
    plan = _write_json(
        tmp_path / "record_plan.json",
        {
            "schema_version": "1.0",
            "plan_id": "plan-1",
            "adapter_id": "nasa-battery",
            "records": [bad],
        },
    )

    with pytest.raises(
        module.PolicyAuthorizedClosedLoopError,
        match="only authorized local analysis or simulation",
    ):
        module.load_result_record_plan(plan, request_queue=queue)


def test_closed_loop_uses_successor_graph_for_next_gate_and_records_each_action(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run = tmp_path / "run"
    run.mkdir()
    registry = _write_json(tmp_path / "registry.json", {"registry": "stub"})
    context = _write_json(
        tmp_path / "context.json",
        {
            "schema_version": "1.0",
            "workstreams": {
                "nasa-battery": {
                    "research_run": str(run),
                    "action_registry_path": str(registry),
                }
            },
        },
    )
    mission = _write_json(tmp_path / "mission.json", {"mission": "stub"})
    graph = _base_graph(tmp_path / "graph.json")

    request_paths: list[Path] = []
    requests: list[dict[str, str]] = []
    records: list[dict[str, object]] = []
    action_types = ["target_reference_sensitivity", "protocol_stratification"]
    for index, action_type in enumerate(action_types, start=1):
        request_path = _write_json(
            tmp_path / f"request-{index}.json", {"action_id": f"a{index}"}
        )
        request_paths.append(request_path)
        request_id = f"q{index}"
        requests.append(
            {
                "request_id": request_id,
                "path": request_path.name,
                "sha256": _sha(request_path),
                "expected_action_type": action_type,
                "expected_action_version": "1.0",
            }
        )
        records.append(
            _record(
                record_id=f"r{index}",
                request_id=request_id,
                action_type=action_type,
                node_id=f"result-{index}",
            )
        )
    queue = _write_json(
        tmp_path / "queue.json",
        {
            "schema_version": "1.0",
            "queue_id": "queue-1",
            "adapter_id": "nasa-battery",
            "requests": requests,
        },
    )
    plan = _write_json(
        tmp_path / "record-plan.json",
        {
            "schema_version": "1.0",
            "plan_id": "record-plan-1",
            "adapter_id": "nasa-battery",
            "records": records,
        },
    )
    reports = [
        _write_json(tmp_path / f"report-{index}.json", {"cycle": index})
        for index in (1, 2)
    ]

    gated_graphs: list[Path] = []

    def gate(**kwargs):
        graph_path = Path(kwargs["graph_path"]).resolve()
        gated_graphs.append(graph_path)
        return {
            "runtime_context_binding": {
                "path": str(context.resolve()),
                "sha256": _sha(context),
            },
            "directive": {
                "directive": "continue_discriminating_research",
                "automatic_execution_permitted": True,
            },
        }

    monkeypatch.setattr(module, "evaluate_epistemic_gate", gate)
    monkeypatch.setattr(
        module,
        "build_research_program",
        lambda *args, **kwargs: _program_state(),
    )

    state = {"cycle": 0}

    def planning_state(selected_type: str | None, marker: int) -> dict[str, object]:
        return {
            "adapter_id": "nasa-battery",
            "current_blocker": {"code": f"b{marker}"},
            "evidence_gap": {"status": "missing", "requirements": []},
            "selected_action": (
                None
                if selected_type is None
                else {"action_type": selected_type, "action_version": "1.0"}
            ),
            "stop_state": {"status": "continue"},
            "budget": {"used": marker},
            "evidence_bindings": [],
        }

    def research_cycle(*args, **kwargs):
        index = state["cycle"]
        if kwargs["request_path"] is None:
            action_type = action_types[index]
            return {
                "cycle_status": "explicit_request_required",
                "authorization": {
                    "selected_action": {
                        "action_type": action_type,
                        "action_version": "1.0",
                    }
                },
                "before_planning_state": planning_state(action_type, index),
                "before_transition": {"transition_type": "action_pending_authorization"},
            }

        action_type = action_types[index]
        request_path = Path(kwargs["request_path"]).resolve()
        assert request_path == request_paths[index].resolve()
        request_sha = _sha(request_path)
        next_type = action_types[index + 1] if index + 1 < len(action_types) else None
        after_transition = (
            {"transition_type": "action_pending_authorization"}
            if next_type is not None
            else {"transition_type": "stop_current_scope"}
        )
        state["cycle"] += 1
        return {
            "cycle_status": "one_action_executed",
            "execution": {
                "action_type": action_type,
                "action_version": "1.0",
                "ledger_action_id": f"a{index + 1}",
                "action_report": str(reports[index]),
                "request_binding": {
                    "path": str(request_path),
                    "sha256": request_sha,
                    "size_bytes": request_path.stat().st_size,
                },
                "scientific_evidence_upgraded_by_orchestrator": False,
                "network_access_initiated_by_orchestrator": False,
            },
            "after_planning_state": planning_state(next_type, index + 1),
            "after_transition": after_transition,
        }

    monkeypatch.setattr(module, "run_research_cycle", research_cycle)

    result = module.run_policy_authorized_closed_loop(
        "nasa-battery",
        repository_root=repo,
        mission_path=mission,
        initial_graph_path=graph,
        epistemic_workstream_id="nasa-battery",
        epistemic_target_node_ids=["h1"],
        runtime_context_path=context,
        artifact_root=tmp_path,
        research_run=run,
        action_registry_path=registry,
        request_queue_path=queue,
        request_root=tmp_path,
        result_record_plan_path=plan,
        output_root=tmp_path / "closed-loop-output",
        max_cycles=4,
    )

    assert result["program_status"] == "stopped_current_scope"
    assert result["actions_executed"] == 2
    assert len(gated_graphs) == 2
    assert gated_graphs[0] == graph.resolve()
    assert gated_graphs[1] == (
        tmp_path / "closed-loop-output" / "cycle_001" / "epistemic_graph.json"
    ).resolve()
    final_graph = json.loads(Path(result["final_graph_binding"]["path"]).read_text("utf-8"))
    assert [node["node_id"] for node in final_graph["nodes"][-2:]] == [
        "result-1",
        "result-2",
    ]
    assert [edge["relation"] for edge in final_graph["edges"][-2:]] == ["tests", "tests"]
    assert result["autonomy_boundary"][
        "automatic_directional_inference_generation_available"
    ] is False


def test_research_program_cli_exposes_closed_loop_subcommand() -> None:
    args = research_program_cli.build_parser().parse_args(
        [
            "run-closed-loop",
            "--mission",
            "mission.json",
            "--repository-root",
            ".",
            "--context",
            "context.json",
            "--base-graph",
            "graph.json",
            "--epistemic-workstream",
            "nasa-battery",
            "--epistemic-target",
            "h1",
            "--research-run",
            "run",
            "--action-registry",
            "registry.json",
            "--request-queue",
            "queue.json",
            "--result-record-plan",
            "records.json",
            "--output",
            "out",
        ]
    )
    assert args.command == "run-closed-loop"
    assert args.epistemic_targets == ["h1"]
