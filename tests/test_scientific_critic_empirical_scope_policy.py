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


def _verification(
    tmp_path: Path,
    *,
    inference_scope: str,
    omit_field: str | None = None,
) -> Path:
    value: dict[str, object] = {
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
    }
    if omit_field is not None:
        value.pop(omit_field)
    return _write_json(tmp_path / f"verify-{inference_scope}.json", value)


def _graph(
    tmp_path: Path,
    verification: Path,
    *,
    inference_scope: str,
    lineage_proposal_sha256: str | None = None,
    injected_inference_edge_id: str | None = None,
) -> Path:
    decision = json.loads(verification.read_text(encoding="utf-8"))
    proposal_sha = str(decision.get("proposal_sha256", "p" * 64))
    base_graph_sha = str(decision.get("base_graph_sha256", "b" * 64))

    if inference_scope == "empirical_direct":
        source_node: dict[str, object] = {
            "node_id": "a1",
            "node_type": "experiment",
            "statement": "Bound physical experiment result.",
            "metadata": {
                "result_origin": "external_physical_experiment",
                "transition_id": "transition-1",
                "input_evidence_bindings": [],
            },
        }
    else:
        source_node = {
            "node_id": "a1",
            "node_type": "analysis",
            "statement": "Bound analysis result.",
            "metadata": {
                "result_origin": "authorized_local_analysis",
                "transition_id": "transition-1",
                "input_evidence_bindings": [
                    {
                        "workstream_id": "ws",
                        "role": "unclassified_input",
                        "sha256": "e" * 64,
                    }
                ],
            },
        }

    lineage: dict[str, object] = {
        "transition_id": "transition-1",
        "parent_graph_id": "g0",
        "parent_graph_sha256": base_graph_sha,
        "proposal_sha256": (
            proposal_sha if lineage_proposal_sha256 is None else lineage_proposal_sha256
        ),
        "verification_decision_sha256": _sha(verification),
        "result_node_id": "a1",
    }
    if injected_inference_edge_id is not None:
        # Graph metadata is opaque in schema v1.0. This field is intentionally injected
        # to prove that its mere presence cannot grant scientific authority.
        lineage["inference_edge_id"] = injected_inference_edge_id

    return _write_json(
        tmp_path / "graph.json",
        {
            "schema_version": "1.0",
            "graph_id": "g1",
            "research_scope": "critic empirical-scope policy test",
            "nodes": [
                {
                    "node_id": "h1",
                    "node_type": "hypothesis",
                    "statement": "Empirical target.",
                    "metadata": {"claim_scope": "empirical"},
                },
                source_node,
            ],
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
            "metadata": {"transition_lineage": [lineage]},
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
                    "verified_contradiction_edges": [],
                    "verified_falsification_edges": [],
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


def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    inference_scope: str,
    lineage_proposal_sha256: str | None = None,
    injected_inference_edge_id: str | None = None,
    omit_verification_field: str | None = None,
) -> tuple[dict[str, object], Path]:
    verification = _verification(
        tmp_path,
        inference_scope=inference_scope,
        omit_field=omit_verification_field,
    )
    graph = _graph(
        tmp_path,
        verification,
        inference_scope=inference_scope,
        lineage_proposal_sha256=lineage_proposal_sha256,
        injected_inference_edge_id=injected_inference_edge_id,
    )
    monkeypatch.setattr(module, "_build_base_report", lambda *args, **kwargs: _base_report(graph))
    result = module.build_policy_hardened_scientific_critic_report(
        graph,
        program_state=_program(),
        artifact_root=tmp_path,
    )
    return result, verification


def test_computational_scope_does_not_satisfy_empirical_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = _run(tmp_path, monkeypatch, inference_scope="computational")

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
    assert action["availability_asserted"] is False
    assert report["epistemic_assessment"]["status"] == "provisionally_supported"


def test_empirical_derived_remains_unestablished_with_unclassified_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = _run(tmp_path, monkeypatch, inference_scope="empirical_derived")

    assert "EMPIRICAL_SUPPORT_SCOPE_NOT_ESTABLISHED" in _codes(result)
    boundary = result["autonomy_boundary"]
    assert boundary["empirical_derived_scope_inferred_from_unclassified_input_bindings"] is False


def test_empirical_direct_remains_unestablished_under_transition_v1_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = _run(tmp_path, monkeypatch, inference_scope="empirical_direct")

    assert "EMPIRICAL_SUPPORT_SCOPE_NOT_ESTABLISHED" in _codes(result)
    boundary = result["autonomy_boundary"]
    assert boundary[
        "empirical_support_scope_accepted_without_authenticated_inference_edge_identity"
    ] is False


def test_injected_opaque_inference_edge_id_cannot_grant_empirical_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = _run(
        tmp_path,
        monkeypatch,
        inference_scope="empirical_direct",
        injected_inference_edge_id="support-1",
    )

    assert "EMPIRICAL_SUPPORT_SCOPE_NOT_ESTABLISHED" in _codes(result)
    assert result["autonomy_boundary"]["opaque_graph_metadata_treated_as_scientific_authority"] is False


def test_even_wrong_injected_edge_id_is_not_consumed_as_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = _run(
        tmp_path,
        monkeypatch,
        inference_scope="empirical_direct",
        injected_inference_edge_id="different-edge",
    )

    assert "EMPIRICAL_SUPPORT_SCOPE_NOT_ESTABLISHED" in _codes(result)


def test_malformed_verification_decision_schema_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ScientificCriticError, match="missing required keys: verifier_id"):
        _run(
            tmp_path,
            monkeypatch,
            inference_scope="empirical_direct",
            omit_verification_field="verifier_id",
        )


def test_bound_verification_decision_checksum_drift_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verification = _verification(tmp_path, inference_scope="computational")
    graph = _graph(tmp_path, verification, inference_scope="computational")
    base = _base_report(graph)
    verification.write_text('{"tampered":true}\n', encoding="utf-8")
    monkeypatch.setattr(module, "_build_base_report", lambda *args, **kwargs: base)

    with pytest.raises(ScientificCriticError, match="changed after graph verification"):
        module.build_policy_hardened_scientific_critic_report(
            graph,
            program_state=_program(),
            artifact_root=tmp_path,
        )


def test_mismatched_proposal_lineage_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ScientificCriticError, match="proposal_sha256 does not match"):
        _run(
            tmp_path,
            monkeypatch,
            inference_scope="empirical_direct",
            lineage_proposal_sha256="q" * 64,
        )
