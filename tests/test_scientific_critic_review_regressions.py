from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import scientific_critic as core
from materials_data_analyzer.research_loop import scientific_critic_policy as policy


def _write_json(path: Path, value: object) -> Path:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _program() -> dict[str, object]:
    return {
        "mission": {"autonomy_policy": {"reasoning_proposals": "schema_validated"}},
        "mission_binding": {"path": "/mission.json", "sha256": "m" * 64},
        "runtime_context_binding": None,
        "workstreams": [],
    }


def _target() -> dict[str, object]:
    return {
        "node_id": "h1",
        "node_type": "hypothesis",
        "statement": "Bounded target.",
        "metadata": {"claim_scope": "structural"},
    }


def _analysis(
    tmp_path: Path,
    *,
    node_id: str = "a1",
    execution_status: str = "completed",
) -> dict[str, object]:
    artifacts: list[dict[str, str]] = []
    if execution_status == "completed":
        artifact = tmp_path / f"{node_id}-result.json"
        artifact.write_text('{"result":"bounded"}\n', encoding="utf-8")
        artifacts.append({"role": "result", "path": str(artifact), "sha256": _sha(artifact)})
    return {
        "node_id": node_id,
        "node_type": "analysis",
        "statement": "Bounded analysis.",
        "execution_status": execution_status,
        "artifact_bindings": artifacts,
    }


def _verified_edge(tmp_path: Path, *, edge_id: str, source: str, relation: str) -> dict[str, object]:
    verifier = tmp_path / f"{edge_id}-verifier.json"
    verifier.write_text('{"domain_verified":true}\n', encoding="utf-8")
    return {
        "edge_id": edge_id,
        "source_node_id": source,
        "target_node_id": "h1",
        "relation": relation,
        "assessment_level": "domain_verified",
        "rationale": "Bound verifier artifact exists.",
        "active": True,
        "verification_artifact": {
            "role": "domain_verification",
            "path": str(verifier),
            "sha256": _sha(verifier),
        },
    }


def _tests_edge(*, source: str) -> dict[str, object]:
    return {
        "edge_id": "tests-1",
        "source_node_id": source,
        "target_node_id": "h1",
        "relation": "tests",
        "assessment_level": "proposal",
        "rationale": "Planned discriminating test.",
        "active": True,
    }


def _graph(tmp_path: Path, *, nodes: list[dict[str, object]], edges: list[dict[str, object]]) -> Path:
    return _write_json(
        tmp_path / "graph.json",
        {
            "schema_version": "1.0",
            "graph_id": "review-regression",
            "research_scope": "critic review regression",
            "nodes": nodes,
            "edges": edges,
        },
    )


def _report(result: dict[str, object]) -> dict[str, object]:
    reports = result["target_reports"]
    assert isinstance(reports, list) and len(reports) == 1
    assert isinstance(reports[0], dict)
    return reports[0]


def _codes(report: dict[str, object]) -> set[str]:
    findings = report["critic_findings"]
    assert isinstance(findings, list)
    return {str(item["code"]) for item in findings if isinstance(item, dict)}


def _actions(report: dict[str, object]) -> list[dict[str, object]]:
    actions = report["discriminating_actions"]
    assert isinstance(actions, list)
    return [item for item in actions if isinstance(item, dict)]


def test_direct_module_public_builder_routes_through_hardened_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = {"policy_hardened": True}
    captured: dict[str, object] = {}

    def fake_policy_builder(graph_path: object, **kwargs: object) -> dict[str, bool]:
        captured["graph_path"] = graph_path
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(policy, "build_policy_hardened_scientific_critic_report", fake_policy_builder)
    graph = tmp_path / "does-not-need-to-exist.json"

    result = core.build_scientific_critic_report(
        graph,
        program_state=_program(),
        artifact_root=tmp_path,
        target_node_ids=["h1"],
    )

    assert result is sentinel
    assert captured["graph_path"] == graph
    assert captured["artifact_root"] == tmp_path
    assert captured["target_node_ids"] == ["h1"]


@pytest.mark.parametrize("execution_status", ["planned", "failed"])
def test_unusable_domain_verified_source_does_not_become_verified_critic_relation(
    tmp_path: Path, execution_status: str
) -> None:
    analysis = _analysis(tmp_path, execution_status=execution_status)
    graph = _graph(
        tmp_path,
        nodes=[_target(), analysis],
        edges=[_verified_edge(tmp_path, edge_id="support-1", source="a1", relation="supports")],
    )

    result = core._build_structural_scientific_critic_report(
        graph,
        program_state=_program(),
        artifact_root=tmp_path,
    )
    report = _report(result)

    assert report["epistemic_assessment"]["status"] == "inconclusive"
    assert "SUPPORT_SOURCE_CONCENTRATION" not in _codes(report)
    assert "VERIFIED_EVIDENCE_CONFLICT" not in _codes(report)
    assert "VERIFIED_FALSIFICATION_PRESENT" not in _codes(report)
    assert "NO_RECORDED_DISCRIMINATING_TEST" in _codes(report)


@pytest.mark.parametrize("execution_status", ["planned", "failed"])
def test_unexecuted_test_edge_does_not_count_as_completed_discriminating_test(
    tmp_path: Path, execution_status: str
) -> None:
    analysis = _analysis(tmp_path, execution_status=execution_status)
    graph = _graph(
        tmp_path,
        nodes=[_target(), analysis],
        edges=[_tests_edge(source="a1")],
    )

    result = core._build_structural_scientific_critic_report(
        graph,
        program_state=_program(),
        artifact_root=tmp_path,
    )
    report = _report(result)

    assert "COMPLETED_TESTS_WITHOUT_DIRECTIONAL_INTERPRETATION" not in _codes(report)
    assert "NO_RECORDED_DISCRIMINATING_TEST" in _codes(report)


def test_standalone_verified_contradiction_remains_explicit_objection(tmp_path: Path) -> None:
    analysis = _analysis(tmp_path)
    graph = _graph(
        tmp_path,
        nodes=[_target(), analysis],
        edges=[_verified_edge(tmp_path, edge_id="contra-1", source="a1", relation="contradicts")],
    )

    result = core._build_structural_scientific_critic_report(
        graph,
        program_state=_program(),
        artifact_root=tmp_path,
    )
    report = _report(result)

    assert report["epistemic_assessment"]["status"] == "contradicted_within_verified_scope"
    assert "VERIFIED_CONTRADICTION_PRESENT" in _codes(report)
    stop = report["stop_recommendation"]
    assert stop["recommendation"] == "reassess_or_reframe_contradicted_target"
    assert stop["positive_scientific_closeout_granted"] is False


def test_unproven_local_work_is_plan_only_and_never_asserts_availability(tmp_path: Path) -> None:
    graph = _graph(tmp_path, nodes=[_target()], edges=[])

    result = core._build_structural_scientific_critic_report(
        graph,
        program_state=_program(),
        artifact_root=tmp_path,
    )
    report = _report(result)
    actions = _actions(report)

    sensitivity = next(item for item in actions if item["action_id"].endswith("robustness-sensitivity"))
    assert sensitivity["execution_mode"] == "plan_only"
    assert all(item["availability_asserted"] is False for item in actions)
    assert all(item["automatic_execution_authorized"] is False for item in actions)
