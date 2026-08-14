from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import scientific_critic_policy as module
from materials_data_analyzer.research_loop.scientific_critic import ScientificCriticError


def _write_json(path: Path, value: object) -> Path:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _program() -> dict[str, object]:
    return {"generated_goals": []}


def _graph(
    tmp_path: Path,
    *,
    relation: str,
    verification_artifact: dict[str, str],
) -> Path:
    return _write_json(
        tmp_path / "graph.json",
        {
            "schema_version": "1.0",
            "graph_id": "negative-directional-policy",
            "research_scope": "negative directional provenance policy test",
            "nodes": [
                {
                    "node_id": "h1",
                    "node_type": "hypothesis",
                    "statement": "Empirical target.",
                    "metadata": {"claim_scope": "empirical"},
                },
                {
                    "node_id": "a1",
                    "node_type": "analysis",
                    "statement": "Bound analysis result.",
                    "execution_status": "completed",
                    "metadata": {
                        "transition_id": "transition-1",
                        "result_origin": "authorized_local_analysis",
                        "input_evidence_bindings": [
                            {
                                "workstream_id": "ws",
                                "role": "input",
                                "sha256": "e" * 64,
                            }
                        ],
                    },
                },
            ],
            "edges": [
                {
                    "edge_id": "negative-1",
                    "source_node_id": "a1",
                    "target_node_id": "h1",
                    "relation": relation,
                    "assessment_level": "domain_verified",
                    "rationale": "Evaluator-visible negative relation.",
                    "active": True,
                    "verification_artifact": verification_artifact,
                }
            ],
            "metadata": {},
        },
    )


def _base_report(
    graph: Path,
    *,
    relation: str,
) -> dict[str, object]:
    contradiction = relation == "contradicts"
    status = (
        "contradicted_within_verified_scope"
        if contradiction
        else "falsified_within_verified_scope"
    )
    core_code = (
        "VERIFIED_CONTRADICTION_PRESENT"
        if contradiction
        else "VERIFIED_FALSIFICATION_PRESENT"
    )
    action_suffix = (
        "reassess-contradicted-scope"
        if contradiction
        else "reframe-falsified-scope"
    )
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
                "claim_scope": "empirical",
                "epistemic_assessment": {
                    "status": status,
                    "verified_support_edges": [],
                    "verified_contradiction_edges": ["negative-1"] if contradiction else [],
                    "verified_falsification_edges": [] if contradiction else ["negative-1"],
                },
                "critic_findings": [
                    {
                        "finding_id": f"critic:h1:{core_code.lower()}",
                        "code": core_code,
                    }
                ],
                "methodological_alternatives": [],
                "discriminating_actions": [
                    {
                        "action_id": f"critic:h1:{action_suffix}",
                        "automatic_execution_authorized": False,
                    }
                ],
                "stop_recommendation": {
                    "recommendation": (
                        "reassess_or_reframe_contradicted_target"
                        if contradiction
                        else "stop_and_reframe_current_target"
                    ),
                    "automatic_stop_authorized": False,
                    "positive_scientific_closeout_granted": False,
                },
            }
        ],
        "summary": {
            "findings": 1,
            "methodological_alternatives": 0,
            "discriminating_actions": 1,
        },
        "autonomy_boundary": {},
    }


def _codes(result: dict[str, object]) -> set[str]:
    reports = result["target_reports"]
    assert isinstance(reports, list) and len(reports) == 1
    findings = reports[0]["critic_findings"]
    assert isinstance(findings, list)
    return {str(item["code"]) for item in findings if isinstance(item, dict)}


@pytest.mark.parametrize(
    ("relation", "core_code", "status"),
    [
        (
            "contradicts",
            "VERIFIED_CONTRADICTION_PRESENT",
            "contradicted_within_verified_scope",
        ),
        (
            "falsifies",
            "VERIFIED_FALSIFICATION_PRESENT",
            "falsified_within_verified_scope",
        ),
    ],
)
def test_unauthed_exact_negative_edge_cannot_drive_critic_reframe_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relation: str,
    core_code: str,
    status: str,
) -> None:
    legacy_verifier = _write_json(tmp_path / "legacy-verifier.json", {"verified": True})
    graph = _graph(
        tmp_path,
        relation=relation,
        verification_artifact={
            "role": "domain_verification",
            "path": str(legacy_verifier),
            "sha256": _sha(legacy_verifier),
        },
    )
    monkeypatch.setattr(
        module,
        "_build_base_report",
        lambda *args, **kwargs: _base_report(graph, relation=relation),
    )

    result = module.build_policy_hardened_scientific_critic_report(
        graph,
        program_state=_program(),
        artifact_root=tmp_path,
    )

    report = result["target_reports"][0]
    assert core_code not in _codes(result)
    assert "NEGATIVE_DIRECTIONAL_PROVENANCE_NOT_ESTABLISHED" in _codes(result)
    assert report["epistemic_assessment"]["status"] == status
    assert (
        report["stop_recommendation"]["recommendation"]
        == "verify_directional_provenance_before_scientific_reframe"
    )
    assert report["stop_recommendation"]["automatic_stop_authorized"] is False
    assert report["stop_recommendation"]["positive_scientific_closeout_granted"] is False

    actions = report["discriminating_actions"]
    review = next(
        item
        for item in actions
        if item["action_id"].endswith("verify-negative-directional-provenance")
    )
    assert review["execution_mode"] == "plan_only"
    assert review["automatic_execution_authorized"] is False
    assert review["availability_asserted"] is False
    assert all(
        not item["action_id"].endswith("reassess-contradicted-scope")
        and not item["action_id"].endswith("reframe-falsified-scope")
        for item in actions
    )
    assert result["autonomy_boundary"][
        "negative_directional_authority_accepted_without_authenticated_inference_edge_identity"
    ] is False


def test_malformed_current_negative_verifier_fails_closed_before_reframe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = _write_json(
        tmp_path / "negative-verifier.json",
        {
            "schema_version": "1.0",
            "decision_id": "negative-decision",
            "transition_id": "transition-1",
            "proposal_sha256": "p" * 64,
            "base_graph_sha256": "b" * 64,
            "result_node_id": "a1",
            "target_node_id": "h1",
            "relation": "contradicts",
            "inference_scope": "empirical_derived",
            # verifier_id intentionally missing
            "rationale": "Malformed negative verifier.",
            "limitations": [],
            "domain_verified": True,
        },
    )
    graph = _graph(
        tmp_path,
        relation="contradicts",
        verification_artifact={
            "role": "domain_verification_decision",
            "path": str(verifier),
            "sha256": _sha(verifier),
        },
    )
    monkeypatch.setattr(
        module,
        "_build_base_report",
        lambda *args, **kwargs: _base_report(graph, relation="contradicts"),
    )

    with pytest.raises(ScientificCriticError, match="missing required keys: verifier_id"):
        module.build_policy_hardened_scientific_critic_report(
            graph,
            program_state=_program(),
            artifact_root=tmp_path,
        )
