from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.scientific_critic import (
    ScientificCriticError,
    build_scientific_critic_report,
)


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def _write_json(path: Path, value: object) -> Path:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _program(*, reasoning: str = "schema_validated") -> dict[str, object]:
    return {
        "mission": {
            "autonomy_policy": {
                "reasoning_proposals": reasoning,
            }
        },
        "mission_binding": {"path": "/mission.json", "sha256": "m" * 64},
        "runtime_context_binding": None,
        "workstreams": [
            {
                "workstream_id": "ws",
                "planning_state": {
                    "evidence_bindings": [
                        {
                            "role": "immutable_measurement_bundle",
                            "sha256": "e" * 64,
                        }
                    ]
                },
            }
        ],
    }


def _artifact_binding(path: Path, role: str = "result") -> dict[str, str]:
    return {"role": role, "path": str(path), "sha256": _sha(path)}


def _target(*, scope: str = "structural") -> dict[str, object]:
    return {
        "node_id": "h1",
        "node_type": "hypothesis",
        "statement": "The bounded target remains scientifically defensible.",
        "metadata": {"claim_scope": scope},
    }


def _analysis_node(tmp_path: Path, node_id: str = "a1") -> dict[str, object]:
    artifact = _write(tmp_path / f"{node_id}.json", b'{"result":"bounded"}\n')
    return {
        "node_id": node_id,
        "node_type": "analysis",
        "statement": "A bounded analysis result.",
        "execution_status": "completed",
        "artifact_bindings": [_artifact_binding(artifact)],
    }


def _simulation_node(tmp_path: Path, node_id: str = "s1") -> dict[str, object]:
    artifact = _write(tmp_path / f"{node_id}.json", b'{"simulation":"structural"}\n')
    return {
        "node_id": node_id,
        "node_type": "simulation",
        "statement": "A structural simulation result.",
        "execution_status": "completed",
        "artifact_bindings": [_artifact_binding(artifact)],
    }


def _verified_edge(
    tmp_path: Path,
    *,
    edge_id: str,
    source: str,
    relation: str,
) -> dict[str, object]:
    verifier = _write(tmp_path / f"{edge_id}-verifier.json", b'{"domain_verified":true}\n')
    return {
        "edge_id": edge_id,
        "source_node_id": source,
        "target_node_id": "h1",
        "relation": relation,
        "assessment_level": "domain_verified",
        "rationale": "Independent domain verification accepted this bounded relation.",
        "active": True,
        "verification_artifact": _artifact_binding(verifier, "domain_verification"),
    }


def _proposal_edge(*, edge_id: str, source: str, relation: str = "tests") -> dict[str, object]:
    return {
        "edge_id": edge_id,
        "source_node_id": source,
        "target_node_id": "h1",
        "relation": relation,
        "assessment_level": "proposal",
        "rationale": "Recorded for later scientific interpretation.",
        "active": True,
    }


def _graph(tmp_path: Path, *, nodes: list[dict[str, object]], edges: list[dict[str, object]]) -> Path:
    return _write_json(
        tmp_path / "graph.json",
        {
            "schema_version": "1.0",
            "graph_id": "critic-test-graph",
            "research_scope": "bounded scientific critic contract test",
            "nodes": nodes,
            "edges": edges,
        },
    )


def _target_report(result: dict[str, object]) -> dict[str, object]:
    reports = result["target_reports"]
    assert isinstance(reports, list) and len(reports) == 1
    report = reports[0]
    assert isinstance(report, dict)
    return report


def _codes(report: dict[str, object]) -> set[str]:
    findings = report["critic_findings"]
    assert isinstance(findings, list)
    return {str(item["code"]) for item in findings}


def _actions(report: dict[str, object]) -> list[dict[str, object]]:
    actions = report["discriminating_actions"]
    assert isinstance(actions, list)
    return [item for item in actions if isinstance(item, dict)]


def test_reasoning_policy_disabled_rejects_critic(tmp_path: Path) -> None:
    graph = _graph(tmp_path, nodes=[_target()], edges=[])
    with pytest.raises(ScientificCriticError, match="does not permit"):
        build_scientific_critic_report(
            graph,
            program_state=_program(reasoning="disabled"),
            artifact_root=tmp_path,
        )


def test_graph_duplicate_keys_are_rejected_before_critique(tmp_path: Path) -> None:
    graph = tmp_path / "graph.json"
    graph.write_text(
        '{"schema_version":"1.0","graph_id":"a","graph_id":"b","research_scope":"x","nodes":[],"edges":[]}\n',
        encoding="utf-8",
    )
    with pytest.raises(ScientificCriticError, match="duplicate JSON key"):
        build_scientific_critic_report(
            graph,
            program_state=_program(),
            artifact_root=tmp_path,
        )


def test_no_counterevidence_creates_counterexample_search_not_support(tmp_path: Path) -> None:
    analysis = _analysis_node(tmp_path)
    graph = _graph(
        tmp_path,
        nodes=[_target(), analysis],
        edges=[_verified_edge(tmp_path, edge_id="support-1", source="a1", relation="supports")],
    )
    result = build_scientific_critic_report(
        graph,
        program_state=_program(),
        artifact_root=tmp_path,
        target_node_ids=["h1"],
    )
    report = _target_report(result)
    assert "NO_DOMAIN_VERIFIED_COUNTEREVIDENCE" in _codes(report)
    assert "SUPPORT_SOURCE_CONCENTRATION" in _codes(report)
    actions = _actions(report)
    external = next(item for item in actions if item["action_class"] == "external_evidence_search")
    assert external["execution_mode"] == "explicit_authorization_required"
    assert external["automatic_execution_authorized"] is False
    assert result["autonomy_boundary"]["scientific_status_changed"] is False
    assert report["epistemic_assessment"]["status"] == "provisionally_supported"


def test_verified_conflict_is_not_collapsed_to_scalar_confidence(tmp_path: Path) -> None:
    a1 = _analysis_node(tmp_path, "a1")
    a2 = _analysis_node(tmp_path, "a2")
    graph = _graph(
        tmp_path,
        nodes=[_target(), a1, a2],
        edges=[
            _verified_edge(tmp_path, edge_id="support-1", source="a1", relation="supports"),
            _verified_edge(tmp_path, edge_id="contra-1", source="a2", relation="contradicts"),
        ],
    )
    result = build_scientific_critic_report(
        graph,
        program_state=_program(),
        artifact_root=tmp_path,
    )
    report = _target_report(result)
    assert "VERIFIED_EVIDENCE_CONFLICT" in _codes(report)
    assert report["epistemic_assessment"]["status"] == "contested"
    assert result["autonomy_boundary"]["probability_or_confidence_estimated"] is False
    stratify = next(
        item for item in _actions(report) if item["action_id"].endswith("resolve-verified-conflict")
    )
    assert stratify["action_class"] == "existing_data_reanalysis"
    assert stratify["automatic_execution_authorized"] is False


def test_verified_falsification_requires_stop_and_reframe(tmp_path: Path) -> None:
    a1 = _analysis_node(tmp_path)
    graph = _graph(
        tmp_path,
        nodes=[_target(), a1],
        edges=[_verified_edge(tmp_path, edge_id="falsify-1", source="a1", relation="falsifies")],
    )
    result = build_scientific_critic_report(
        graph,
        program_state=_program(),
        artifact_root=tmp_path,
    )
    report = _target_report(result)
    assert "VERIFIED_FALSIFICATION_PRESENT" in _codes(report)
    assert report["epistemic_assessment"]["status"] == "falsified_within_verified_scope"
    stop = report["stop_recommendation"]
    assert stop["recommendation"] == "stop_and_reframe_current_target"
    assert stop["automatic_stop_authorized"] is False
    assert stop["positive_scientific_closeout_granted"] is False


def test_empirical_target_with_only_simulation_support_requests_empirical_validation(
    tmp_path: Path,
) -> None:
    sim = _simulation_node(tmp_path)
    graph = _graph(
        tmp_path,
        nodes=[_target(scope="empirical"), sim],
        edges=[_verified_edge(tmp_path, edge_id="support-sim", source="s1", relation="supports")],
    )
    result = build_scientific_critic_report(
        graph,
        program_state=_program(),
        artifact_root=tmp_path,
    )
    report = _target_report(result)
    assert "SIMULATION_ONLY_SUPPORT_FOR_EMPIRICAL_SCOPE" in _codes(report)
    action = next(
        item for item in _actions(report) if item["action_id"].endswith("design-empirical-validation")
    )
    assert action["action_class"] == "physical_experiment_design"
    assert action["execution_mode"] == "plan_only"
    assert action["automatic_execution_authorized"] is False
    assert result["autonomy_boundary"]["physical_experiment_execution_authorized"] is False


def test_completed_test_without_directional_relation_stays_uninterpreted(tmp_path: Path) -> None:
    analysis = _analysis_node(tmp_path)
    graph = _graph(
        tmp_path,
        nodes=[_target(), analysis],
        edges=[_proposal_edge(edge_id="tests-1", source="a1")],
    )
    result = build_scientific_critic_report(
        graph,
        program_state=_program(),
        artifact_root=tmp_path,
    )
    report = _target_report(result)
    assert "COMPLETED_TESTS_WITHOUT_DIRECTIONAL_INTERPRETATION" in _codes(report)
    assert report["epistemic_assessment"]["status"] == "inconclusive"
    review = next(
        item for item in _actions(report) if item["action_id"].endswith("interpret-recorded-tests")
    )
    assert review["execution_mode"] == "plan_only"
    assert result["autonomy_boundary"]["scientific_evidence_created"] is False


def test_all_critic_actions_remain_non_authoritative(tmp_path: Path) -> None:
    analysis = _analysis_node(tmp_path)
    graph = _graph(
        tmp_path,
        nodes=[_target(), analysis],
        edges=[_verified_edge(tmp_path, edge_id="support-1", source="a1", relation="supports")],
    )
    result = build_scientific_critic_report(
        graph,
        program_state=_program(),
        artifact_root=tmp_path,
    )
    report = _target_report(result)
    assert _actions(report)
    assert all(item["automatic_execution_authorized"] is False for item in _actions(report))
    assert all(
        item["information_gain_is_calibrated_probability"] is False for item in _actions(report)
    )
    boundary = result["autonomy_boundary"]
    assert boundary["automatic_action_execution_authorized"] is False
    assert boundary["network_access_authorized"] is False
    assert boundary["physical_experiment_execution_authorized"] is False
    assert boundary["positive_scientific_closeout_granted"] is False


def test_report_binds_exact_graph_and_program_state(tmp_path: Path) -> None:
    graph = _graph(tmp_path, nodes=[_target()], edges=[])
    program = _program()
    result = build_scientific_critic_report(
        graph,
        program_state=program,
        artifact_root=tmp_path,
    )
    assert result["graph_binding"]["sha256"] == _sha(graph)
    canonical = json.dumps(
        program,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    assert result["program_state_sha256"] == hashlib.sha256(canonical).hexdigest()


def test_unknown_target_is_rejected(tmp_path: Path) -> None:
    graph = _graph(tmp_path, nodes=[_target()], edges=[])
    with pytest.raises(ScientificCriticError, match="must be assessed"):
        build_scientific_critic_report(
            graph,
            program_state=_program(),
            artifact_root=tmp_path,
            target_node_ids=["missing"],
        )
