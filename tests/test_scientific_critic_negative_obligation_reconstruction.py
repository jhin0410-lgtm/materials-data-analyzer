from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import scientific_critic_policy as module


def _write_json(path: Path, value: object) -> Path:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _legacy_binding(tmp_path: Path) -> dict[str, str]:
    verifier = _write_json(tmp_path / "legacy-verifier.json", {"verified": True})
    return {
        "role": "domain_verification",
        "path": str(verifier),
        "sha256": _sha(verifier),
    }


def _target() -> dict[str, object]:
    return {
        "node_id": "h1",
        "node_type": "hypothesis",
        "statement": "Bound target.",
        "metadata": {"claim_scope": "structural"},
    }


def _analysis(node_id: str) -> dict[str, object]:
    return {
        "node_id": node_id,
        "node_type": "analysis",
        "statement": f"Bound analysis {node_id}.",
        "execution_status": "completed",
    }


def _edge(
    *,
    edge_id: str,
    source: str,
    relation: str,
    binding: dict[str, str],
) -> dict[str, object]:
    return {
        "edge_id": edge_id,
        "source_node_id": source,
        "target_node_id": "h1",
        "relation": relation,
        "assessment_level": "domain_verified",
        "rationale": "Evaluator-visible directional relation.",
        "active": True,
        "verification_artifact": binding,
    }


def _graph(
    tmp_path: Path,
    *,
    nodes: list[dict[str, object]],
    edges: list[dict[str, object]],
) -> Path:
    return _write_json(
        tmp_path / "graph.json",
        {
            "schema_version": "1.0",
            "graph_id": "negative-obligation-reconstruction",
            "research_scope": "critic obligation reconstruction test",
            "nodes": nodes,
            "edges": edges,
        },
    )


def _base_report(
    graph: Path,
    *,
    status: str,
    supports: list[str],
    contradictions: list[str],
    falsifications: list[str],
    findings: list[dict[str, object]],
    alternatives: list[dict[str, object]],
    actions: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "critic_policy_version": "1.0",
        "graph_binding": {
            "path": str(graph.resolve()),
            "sha256": _sha(graph),
            "bytes": graph.stat().st_size,
        },
        "target_reports": [
            {
                "target_node_id": "h1",
                "target_node_type": "hypothesis",
                "target_statement": "Bound target.",
                "claim_scope": "structural",
                "epistemic_assessment": {
                    "node_id": "h1",
                    "status": status,
                    "verified_support_edges": supports,
                    "verified_contradiction_edges": contradictions,
                    "verified_falsification_edges": falsifications,
                    "diagnostic_relation_edges": [],
                    "domain_closeout_required_for_positive_conclusion": bool(supports),
                    "final_positive_support_granted": False,
                    "confidence_score": None,
                },
                "critic_findings": findings,
                "methodological_alternatives": alternatives,
                "discriminating_actions": actions,
                "stop_recommendation": {
                    "recommendation": "continue_discriminating_research",
                    "automatic_stop_authorized": False,
                    "positive_scientific_closeout_granted": False,
                },
            }
        ],
        "summary": {
            "targets_reviewed": 1,
            "findings": len(findings),
            "methodological_alternatives": len(alternatives),
            "discriminating_actions": len(actions),
        },
        "autonomy_boundary": {},
    }


def _codes(result: dict[str, object]) -> set[str]:
    reports = result["target_reports"]
    assert isinstance(reports, list) and len(reports) == 1
    findings = reports[0]["critic_findings"]
    assert isinstance(findings, list)
    return {str(item["code"]) for item in findings if isinstance(item, dict)}


def _action_ids(result: dict[str, object]) -> set[str]:
    report = result["target_reports"][0]
    actions = report["discriminating_actions"]
    assert isinstance(actions, list)
    return {str(item["action_id"]) for item in actions if isinstance(item, dict)}


def test_negative_only_relation_restores_counterevidence_and_no_test_obligations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = _legacy_binding(tmp_path)
    graph = _graph(
        tmp_path,
        nodes=[_target(), _analysis("a1")],
        edges=[
            _edge(
                edge_id="contra-1",
                source="a1",
                relation="contradicts",
                binding=binding,
            )
        ],
    )
    base = _base_report(
        graph,
        status="contradicted_within_verified_scope",
        supports=[],
        contradictions=["contra-1"],
        falsifications=[],
        findings=[
            {
                "finding_id": "critic:h1:verified-contradiction",
                "code": "VERIFIED_CONTRADICTION_PRESENT",
            }
        ],
        alternatives=[],
        actions=[
            {
                "action_id": "critic:h1:reassess-contradicted-scope",
                "automatic_execution_authorized": False,
            }
        ],
    )
    monkeypatch.setattr(module, "_build_base_report", lambda *args, **kwargs: base)

    result = module.build_policy_hardened_scientific_critic_report(
        graph,
        program_state={"generated_goals": []},
        artifact_root=tmp_path,
    )

    report = result["target_reports"][0]
    codes = _codes(result)
    assert "VERIFIED_CONTRADICTION_PRESENT" not in codes
    assert "NEGATIVE_DIRECTIONAL_PROVENANCE_NOT_ESTABLISHED" in codes
    assert "NO_DOMAIN_VERIFIED_COUNTEREVIDENCE" in codes
    assert "NO_RECORDED_DISCRIMINATING_TEST" in codes
    assert report["epistemic_assessment"]["status"] == "contradicted_within_verified_scope"
    assert (
        report["stop_recommendation"]["recommendation"]
        == "verify_directional_provenance_before_scientific_reframe"
    )
    assert "critic:h1:seek-counterexample-evidence" in _action_ids(result)
    assert result["autonomy_boundary"][
        "negative_directional_edges_allowed_to_suppress_research_obligations"
    ] is False


def test_support_plus_unauthenticated_negative_restores_counterevidence_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = _legacy_binding(tmp_path)
    graph = _graph(
        tmp_path,
        nodes=[_target(), _analysis("a1"), _analysis("a2")],
        edges=[
            _edge(
                edge_id="support-1",
                source="a1",
                relation="supports",
                binding=binding,
            ),
            _edge(
                edge_id="contra-1",
                source="a2",
                relation="contradicts",
                binding=binding,
            ),
        ],
    )
    base = _base_report(
        graph,
        status="contested",
        supports=["support-1"],
        contradictions=["contra-1"],
        falsifications=[],
        findings=[
            {
                "finding_id": "critic:h1:verified-conflict",
                "code": "VERIFIED_EVIDENCE_CONFLICT",
            }
        ],
        alternatives=[
            {
                "alternative_id": "critic:h1:scope-heterogeneity",
                "proposal_status": "proposed_not_evidence_upgraded",
            }
        ],
        actions=[
            {
                "action_id": "critic:h1:resolve-verified-conflict",
                "automatic_execution_authorized": False,
            }
        ],
    )
    monkeypatch.setattr(module, "_build_base_report", lambda *args, **kwargs: base)

    result = module.build_policy_hardened_scientific_critic_report(
        graph,
        program_state={"generated_goals": []},
        artifact_root=tmp_path,
    )

    report = result["target_reports"][0]
    codes = _codes(result)
    alternatives = report["methodological_alternatives"]
    assert "VERIFIED_EVIDENCE_CONFLICT" not in codes
    assert "NEGATIVE_DIRECTIONAL_PROVENANCE_NOT_ESTABLISHED" in codes
    assert "NO_DOMAIN_VERIFIED_COUNTEREVIDENCE" in codes
    assert "NO_RECORDED_DISCRIMINATING_TEST" not in codes
    assert "SUPPORT_INDEPENDENCE_NOT_ESTABLISHED" in codes
    assert report["epistemic_assessment"]["status"] == "contested"
    assert all(
        item.get("alternative_id") != "critic:h1:scope-heterogeneity"
        for item in alternatives
        if isinstance(item, dict)
    )
    assert "critic:h1:seek-counterexample-evidence" in _action_ids(result)
    assert "critic:h1:resolve-verified-conflict" not in _action_ids(result)
