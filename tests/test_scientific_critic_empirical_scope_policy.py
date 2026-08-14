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


def _verification(tmp_path: Path, *, inference_scope: str) -> Path:
    return _write_json(
        tmp_path / f"verify-{inference_scope}.json",
        {
            "schema_version": "1.0",
            "decision_id": f"verify-{inference_scope}",
            "transition_id": "transition-1",
            "proposal_sha256": "p" * 64,
            "base_graph_sha256": "b" * 64,
            "result_node_id": "a1",
            "target_node_id": "h1",
            "relation": "supports",
            "inference_scope": inference_scope,
            "verifier_id": "domain-verifier",
            "rationale": "Bound scope test decision.",
            "limitations": [],
            "domain_verified": True,
        },
    )


def _graph(tmp_path: Path, verification: Path) -> Path:
    return _write_json(
        tmp_path / "graph.json",
        {
            "schema_version": "1.0",
            "graph_id": "g1",
            "research_scope": "critic empirical-scope policy test",
            "nodes": [],
            "edges": [
                {
                    "edge_id": "support-1",
                    "source_node_id": "a1",
                    "target_node_id": "h1",
                    "relation": "supports",
                    "assessment_level": "domain_verified",
                    "rationale": "Bound support edge.",
                    "active": True,
                    "verification_artifact": {
                        "role": "domain_verification_decision",
                        "path": str(verification),
                        "sha256": _sha(verification),
                    },
                }
            ],
        },
    )


def _base_report(graph: Path) -> dict[str, object]:
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
                    "status": "provisionally_supported",
                    "verified_support_edges": ["support-1"],
                },
                "critic_findings": [],
                "methodological_alternatives": [],
                "discriminating_actions": [],
            }
        ],
        "summary": {
            "findings": 0,
            "methodological_alternatives": 0,
            "discriminating_actions": 0,
        },
        "autonomy_boundary": {},
    }


def _program() -> dict[str, object]:
    return {"generated_goals": []}


def _codes(result: dict[str, object]) -> set[str]:
    reports = result["target_reports"]
    assert isinstance(reports, list) and len(reports) == 1
    findings = reports[0]["critic_findings"]
    return {str(item["code"]) for item in findings}


def test_empirical_target_with_only_computational_scope_support_is_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verification = _verification(tmp_path, inference_scope="computational")
    graph = _graph(tmp_path, verification)
    monkeypatch.setattr(module, "_build_base_report", lambda *args, **kwargs: _base_report(graph))

    result = module.build_policy_hardened_scientific_critic_report(
        graph,
        program_state=_program(),
        artifact_root=tmp_path,
    )

    assert "EMPIRICAL_SUPPORT_SCOPE_NOT_ESTABLISHED" in _codes(result)
    report = result["target_reports"][0]
    action = next(
        item
        for item in report["discriminating_actions"]
        if item["action_id"].endswith("bind-empirical-support-scope")
    )
    assert action["action_class"] == "manual_review"
    assert action["execution_mode"] == "plan_only"
    assert action["automatic_execution_authorized"] is False
    assert report["epistemic_assessment"]["status"] == "provisionally_supported"
    assert result["autonomy_boundary"]["empirical_support_scope_inferred_from_source_node_type"] is False


def test_bound_empirical_derived_scope_satisfies_empirical_scope_obligation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verification = _verification(tmp_path, inference_scope="empirical_derived")
    graph = _graph(tmp_path, verification)
    monkeypatch.setattr(module, "_build_base_report", lambda *args, **kwargs: _base_report(graph))

    result = module.build_policy_hardened_scientific_critic_report(
        graph,
        program_state=_program(),
        artifact_root=tmp_path,
    )

    assert "EMPIRICAL_SUPPORT_SCOPE_NOT_ESTABLISHED" not in _codes(result)
    report = result["target_reports"][0]
    assert report["epistemic_assessment"]["status"] == "provisionally_supported"


def test_bound_verification_decision_checksum_drift_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verification = _verification(tmp_path, inference_scope="computational")
    graph = _graph(tmp_path, verification)
    base = _base_report(graph)
    verification.write_text('{"tampered":true}\n', encoding="utf-8")
    monkeypatch.setattr(module, "_build_base_report", lambda *args, **kwargs: base)

    with pytest.raises(ScientificCriticError, match="changed after graph verification"):
        module.build_policy_hardened_scientific_critic_report(
            graph,
            program_state=_program(),
            artifact_root=tmp_path,
        )
