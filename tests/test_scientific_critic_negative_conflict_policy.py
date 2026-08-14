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


def test_unauthed_negative_edge_removes_conflict_derived_alternative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy = _write_json(tmp_path / "legacy-verifier.json", {"verified": True})
    binding = {
        "role": "domain_verification",
        "path": str(legacy),
        "sha256": _sha(legacy),
    }
    graph = _write_json(
        tmp_path / "graph.json",
        {
            "schema_version": "1.0",
            "graph_id": "conflict-policy",
            "research_scope": "conflict provenance isolation",
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
                    "statement": "Positive result.",
                    "execution_status": "completed",
                },
                {
                    "node_id": "a2",
                    "node_type": "analysis",
                    "statement": "Negative result.",
                    "execution_status": "completed",
                },
            ],
            "edges": [
                {
                    "edge_id": "support-1",
                    "source_node_id": "a1",
                    "target_node_id": "h1",
                    "relation": "supports",
                    "assessment_level": "domain_verified",
                    "rationale": "Positive relation.",
                    "active": True,
                    "verification_artifact": binding,
                },
                {
                    "edge_id": "contra-1",
                    "source_node_id": "a2",
                    "target_node_id": "h1",
                    "relation": "contradicts",
                    "assessment_level": "domain_verified",
                    "rationale": "Negative relation.",
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
                "claim_scope": "structural",
                "epistemic_assessment": {
                    "status": "contested",
                    "verified_support_edges": ["support-1"],
                    "verified_contradiction_edges": ["contra-1"],
                    "verified_falsification_edges": [],
                },
                "critic_findings": [
                    {
                        "finding_id": "critic:h1:verified-conflict",
                        "code": "VERIFIED_EVIDENCE_CONFLICT",
                    }
                ],
                "methodological_alternatives": [
                    {
                        "alternative_id": "critic:h1:scope-heterogeneity",
                        "proposal_status": "proposed_not_evidence_upgraded",
                    }
                ],
                "discriminating_actions": [
                    {
                        "action_id": "critic:h1:resolve-verified-conflict",
                        "automatic_execution_authorized": False,
                    }
                ],
                "stop_recommendation": {
                    "recommendation": "continue_discriminating_research",
                    "automatic_stop_authorized": False,
                    "positive_scientific_closeout_granted": False,
                },
            }
        ],
        "summary": {
            "findings": 1,
            "methodological_alternatives": 1,
            "discriminating_actions": 1,
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
    codes = {item["code"] for item in report["critic_findings"]}
    alternative_ids = {
        item["alternative_id"] for item in report["methodological_alternatives"]
    }
    action_ids = {item["action_id"] for item in report["discriminating_actions"]}

    assert "VERIFIED_EVIDENCE_CONFLICT" not in codes
    assert "NEGATIVE_DIRECTIONAL_PROVENANCE_NOT_ESTABLISHED" in codes
    assert "critic:h1:scope-heterogeneity" not in alternative_ids
    assert "critic:h1:resolve-verified-conflict" not in action_ids
    assert report["epistemic_assessment"]["status"] == "contested"
    assert result["summary"]["methodological_alternatives"] == len(
        report["methodological_alternatives"]
    )
