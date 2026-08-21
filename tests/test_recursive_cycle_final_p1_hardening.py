from __future__ import annotations

import pytest

import materials_data_analyzer.research_loop.validated_recursive_cycle_planning as planning
from materials_data_analyzer.research_loop.recursive_research_cycle_evidence import _authoritative_portfolio
from materials_data_analyzer.research_loop.recursive_scientific_state import evaluated_graph_scientific_identity_sha256, target_scientific_state_fingerprint
from materials_data_analyzer.research_loop.validated_recursive_cycle_planning import ValidatedRecursivePlanningError


def _evaluated(graph_id: str, *, diagnostic_edge_id: str, verified_sha: str | None = None, artifact_path: str = "/tmp/result-a") -> dict:
    nodes = [{"node_id": "c-1", "node_type": "claim", "statement": "bounded claim", "metadata": {"claim_scope": "structural"}}, {"node_id": "a-1", "node_type": "analysis", "statement": "bounded analysis", "execution_status": "completed", "artifact_bindings": [{"role": "primary", "path": artifact_path, "sha256": "a" * 64, "bytes": 1}], "metadata": {"result_origin": "authorized_local_analysis"}}]
    edges = [{"edge_id": diagnostic_edge_id, "source_node_id": "a-1", "target_node_id": "c-1", "relation": "supports", "assessment_level": "diagnostic", "rationale": "diagnostic only", "active": True}]
    status = "inconclusive"
    supports = []
    if verified_sha is not None:
        edges.append({"edge_id": "verified-1", "source_node_id": "a-1", "target_node_id": "c-1", "relation": "supports", "assessment_level": "domain_verified", "rationale": "verified", "active": True, "verification_artifact": {"role": "domain", "path": "/tmp/verifier", "sha256": verified_sha, "bytes": 1}})
        status = "provisionally_supported"
        supports = ["verified-1"]
    return {"schema_version": "1.0", "graph_policy_version": "1.0", "graph_id": graph_id, "research_scope": "bounded", "nodes": nodes, "edges": edges, "assessments": [{"node_id": "c-1", "node_type": "claim", "status": status, "verified_support_edges": supports, "verified_contradiction_edges": [], "verified_falsification_edges": [], "diagnostic_relation_edges": [diagnostic_edge_id], "final_positive_support_granted": False, "domain_closeout_required_for_positive_conclusion": bool(verified_sha), "confidence_score": None}], "conflict_count": 0, "falsified_count": 0, "autonomy_boundary": {}}


def test_target_scientific_fingerprint_ignores_version_and_diagnostic_bookkeeping() -> None:
    first = _evaluated("g-1", diagnostic_edge_id="diag-1")
    second = _evaluated("g-2", diagnostic_edge_id="diag-2")
    assert target_scientific_state_fingerprint(first, target_node_id="c-1")["fingerprint_sha256"] == target_scientific_state_fingerprint(second, target_node_id="c-1")["fingerprint_sha256"]


def test_target_scientific_fingerprint_changes_on_domain_verified_evidence() -> None:
    first = _evaluated("g-1", diagnostic_edge_id="diag-1")
    second = _evaluated("g-2", diagnostic_edge_id="diag-2", verified_sha="b" * 64)
    assert target_scientific_state_fingerprint(first, target_node_id="c-1")["fingerprint_sha256"] != target_scientific_state_fingerprint(second, target_node_id="c-1")["fingerprint_sha256"]


def test_whole_graph_binding_ignores_only_local_artifact_resolution() -> None:
    first = _evaluated("g-1", diagnostic_edge_id="diag-1", artifact_path="/workspace/a/result.json")
    second = _evaluated("g-1", diagnostic_edge_id="diag-1", artifact_path="/bundle/result.json")
    assert evaluated_graph_scientific_identity_sha256(first) == evaluated_graph_scientific_identity_sha256(second)
    second["nodes"][0]["statement"] = "substituted claim"
    assert evaluated_graph_scientific_identity_sha256(first) != evaluated_graph_scientific_identity_sha256(second)


def test_claim_target_does_not_require_unrelated_hypothesis_portfolio() -> None:
    graph = _evaluated("g-1", diagnostic_edge_id="diag-1")
    portfolio, digest, state = _authoritative_portfolio(evaluated_graph=graph, fresh_plan={}, target={"graph_id": "g-1", "node_id": "c-1", "node_type": "claim", "statement": "bounded claim"}, assessment=graph["assessments"][0])
    assert portfolio is None and digest is None and state is None


def test_raw_predecessor_checkpoint_fails_without_validated_context(monkeypatch) -> None:
    monkeypatch.setattr(planning, "validate_policy_hardened_discrepancy_planning_handoff", lambda *args, **kwargs: {"handoff_sha256": "a" * 64})
    monkeypatch.setattr(planning, "validate_autonomous_inquiry_plan", lambda *args, **kwargs: {"plan_sha256": "b" * 64})
    with pytest.raises(ValidatedRecursivePlanningError, match="raw predecessor checkpoint is not accepted"):
        planning.build_validated_recursive_planning_checkpoint(planning_handoff={}, source_discrepancy_report={}, source_evaluated_graph={}, fresh_plan={}, planner_program_state={}, previous_checkpoint={"checkpoint_sha256": "c" * 64})
