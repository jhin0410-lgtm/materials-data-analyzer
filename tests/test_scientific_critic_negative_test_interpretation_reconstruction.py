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


def test_unauthenticated_negative_direction_cannot_mark_completed_test_interpreted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = _write_json(tmp_path / "legacy-verifier.json", {"verified": True})
    binding = {
        "role": "domain_verification",
        "path": str(verifier),
        "sha256": _sha(verifier),
    }
    graph = _write_json(
        tmp_path / "graph.json",
        {
            "schema_version": "1.0",
            "graph_id": "negative-test-interpretation",
            "research_scope": "completed test interpretation reconstruction",
            "nodes": [
                {
                    "node_id": "h1",
                    "node_type": "hypothesis",
                    "statement": "Bound target.",
                    "metadata": {"claim_scope": "structural"},
                },
                {
                    "node_id": "a1",
                    "node_type": "analysis",
                    "statement": "Completed bounded test result.",
                    "execution_status": "completed",
                },
            ],
            "edges": [
                {
                    "edge_id": "tests-1",
                    "source_node_id": "a1",
                    "target_node_id": "h1",
                    "relation": "tests",
                    "assessment_level": "proposal",
                    "rationale": "Completed test edge.",
                    "active": True,
                },
                {
                    "edge_id": "contra-1",
                    "source_node_id": "a1",
                    "target_node_id": "h1",
                    "relation": "contradicts",
                    "assessment_level": "domain_verified",
                    "rationale": "Evaluator-visible negative interpretation.",
                    "active": True,
                    "verification_artifact": binding,
                },
            ],
        },
    )
    base = {
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
                    "status": "contradicted_within_verified_scope",
                    "verified_support_edges": [],
                    "verified_contradiction_edges": ["contra-1"],
                    "verified_falsification_edges": [],
                    "diagnostic_relation_edges": [],
                    "domain_closeout_required_for_positive_conclusion": False,
                    "final_positive_support_granted": False,
                    "confidence_score": None,
                },
                "critic_findings": [
                    {
                        "finding_id": "critic:h1:verified-contradiction",
                        "code": "VERIFIED_CONTRADICTION_PRESENT",
                    }
                ],
                "methodological_alternatives": [],
                "discriminating_actions": [],
                "stop_recommendation": {
                    "recommendation": "reassess_or_reframe_contradicted_target",
                    "automatic_stop_authorized": False,
                    "positive_scientific_closeout_granted": False,
                },
            }
        ],
        "summary": {
            "targets_reviewed": 1,
            "findings": 1,
            "methodological_alternatives": 0,
            "discriminating_actions": 0,
        },
        "autonomy_boundary": {},
    }
    monkeypatch.setattr(module, "_build_base_report", lambda *args, **kwargs: base)

    result = module.build_policy_hardened_scientific_critic_report(
        graph,
        program_state={"generated_goals": []},
        artifact_root=tmp_path,
    )

    report = result["target_reports"][0]
    codes = {
        item["code"]
        for item in report["critic_findings"]
        if isinstance(item, dict)
    }
    action_ids = {
        item["action_id"]
        for item in report["discriminating_actions"]
        if isinstance(item, dict)
    }

    assert "VERIFIED_CONTRADICTION_PRESENT" not in codes
    assert "NEGATIVE_DIRECTIONAL_PROVENANCE_NOT_ESTABLISHED" in codes
    assert "COMPLETED_TESTS_WITHOUT_DIRECTIONAL_INTERPRETATION" in codes
    assert "NO_RECORDED_DISCRIMINATING_TEST" not in codes
    assert "critic:h1:interpret-recorded-tests" in action_ids
    assert "critic:h1:verify-negative-directional-provenance" in action_ids
    assert report["epistemic_assessment"]["status"] == "contradicted_within_verified_scope"
