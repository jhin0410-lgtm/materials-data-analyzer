from __future__ import annotations

import base64
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import epistemic_graph
from materials_data_analyzer.research_loop import policy_authorized_closed_loop as closed


def _write_json(path: Path, value: object) -> Path:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def test_pinned_mission_disabled_typed_actions_fail_before_execution(tmp_path: Path) -> None:
    mission = _write_json(
        tmp_path / "mission.json",
        {
            "autonomy_policy": {
                "typed_computational_actions": "disabled",
            }
        },
    )
    with pytest.raises(
        closed.PolicyAuthorizedClosedLoopError,
        match="does not authorize explicit typed computational actions",
    ):
        closed._snapshot_static_file(mission, field="mission_path")


def test_pinned_mission_explicit_request_is_accepted(tmp_path: Path) -> None:
    mission = _write_json(
        tmp_path / "mission.json",
        {
            "autonomy_policy": {
                "typed_computational_actions": "explicit_request",
            }
        },
    )
    snapshot = closed._snapshot_static_file(mission, field="mission_path")
    assert snapshot["value"]["autonomy_policy"]["typed_computational_actions"] == "explicit_request"


def test_preflight_rejects_malformed_record_transition_lineage(tmp_path: Path) -> None:
    graph = _write_json(
        tmp_path / "graph.json",
        {
            "schema_version": "1.0",
            "graph_id": "g1",
            "research_scope": "bounded",
            "nodes": [
                {
                    "node_id": "h1",
                    "node_type": "hypothesis",
                    "statement": "target",
                }
            ],
            "edges": [],
            "metadata": {"record_only_transition_lineage": {"not": "a list"}},
        },
    )
    record = {
        "record_id": "r1",
        "target_node_id": "h1",
        "result_node_id": "result-1",
    }
    with pytest.raises(
        closed.PolicyAuthorizedClosedLoopError,
        match="record_only_transition_lineage must be a list",
    ):
        closed._preflight_graph_and_records(
            graph_path=graph,
            records=[record],
            target_ids=["h1"],
        )


def test_failed_report_snapshot_checksum_is_schema_validated(tmp_path: Path) -> None:
    raw = b'{"execution_status":"failed"}\n'
    corrupted = b'{"execution_status":"failed","tampered":true}\n'
    graph = {
        "schema_version": "1.0",
        "graph_id": "g1",
        "research_scope": "bounded",
        "nodes": [
            {
                "node_id": "h1",
                "node_type": "hypothesis",
                "statement": "target",
            },
            {
                "node_id": "a1",
                "node_type": "analysis",
                "statement": "failed bounded analysis",
                "execution_status": "failed",
                "metadata": {
                    "failed_action_report_snapshot": {
                        "encoding": "base64",
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "size_bytes": len(corrupted),
                        "data": base64.b64encode(corrupted).decode("ascii"),
                    }
                },
            },
        ],
        "edges": [],
    }
    with pytest.raises(epistemic_graph.EpistemicGraphError, match="checksum mismatch"):
        epistemic_graph.validate_epistemic_graph(
            graph,
            program_state={"workstreams": []},
            artifact_root=tmp_path,
        )


def test_failed_report_snapshot_valid_bytes_remain_non_evidence(tmp_path: Path) -> None:
    raw = b'{"execution_status":"failed"}\n'
    graph = {
        "schema_version": "1.0",
        "graph_id": "g1",
        "research_scope": "bounded",
        "nodes": [
            {
                "node_id": "h1",
                "node_type": "hypothesis",
                "statement": "target",
            },
            {
                "node_id": "a1",
                "node_type": "analysis",
                "statement": "failed bounded analysis",
                "execution_status": "failed",
                "metadata": {
                    "failed_action_report_snapshot": {
                        "encoding": "base64",
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "size_bytes": len(raw),
                        "data": base64.b64encode(raw).decode("ascii"),
                    }
                },
            },
        ],
        "edges": [],
    }
    validated = epistemic_graph.validate_epistemic_graph(
        graph,
        program_state={"workstreams": []},
        artifact_root=tmp_path,
    )
    failed = validated["nodes"][1]
    assert failed["execution_status"] == "failed"
    assert failed["artifact_bindings"] == []
    assert "failed_action_report_snapshot" in failed["metadata"]


def test_closed_loop_holds_shared_ledger_lock_through_core_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_state = {"held": False}

    @contextmanager
    def fake_lock(research_run: str | Path):
        assert Path(research_run) == tmp_path
        assert lock_state["held"] is False
        lock_state["held"] = True
        try:
            yield tmp_path
        finally:
            lock_state["held"] = False

    def fake_core(*args, **kwargs):
        assert lock_state["held"] is True
        return {
            "closed_loop_policy_version": "old",
            "autonomy_boundary": {},
        }

    monkeypatch.setattr(closed, "shared_research_ledger_transaction_lock", fake_lock)
    monkeypatch.setattr(closed._core, "run_policy_authorized_closed_loop", fake_core)

    result = closed.run_policy_authorized_closed_loop(
        "nasa-battery",
        repository_root=tmp_path,
        mission_path=tmp_path / "mission.json",
        initial_graph_path=tmp_path / "graph.json",
        epistemic_workstream_id="nasa-battery",
        epistemic_target_node_ids=["h1"],
        runtime_context_path=tmp_path / "context.json",
        artifact_root=tmp_path,
        research_run=tmp_path,
        action_registry_path=tmp_path / "registry.json",
        request_queue_path=tmp_path / "queue.json",
        result_record_plan_path=tmp_path / "records.json",
        output_root=tmp_path / "out",
    )

    assert lock_state["held"] is False
    assert result["closed_loop_policy_version"] == closed.CLOSED_LOOP_POLICY_VERSION
    assert result["autonomy_boundary"]["ledger_lock_held_through_successor_ingestion"]
    assert result["autonomy_boundary"][
        "mission_typed_action_policy_enforced_from_pinned_snapshot"
    ]
