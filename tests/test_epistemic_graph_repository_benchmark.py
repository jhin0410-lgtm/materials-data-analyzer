from __future__ import annotations

from pathlib import Path

from materials_data_analyzer.research_loop import build_research_program
from materials_data_analyzer.research_loop.epistemic_graph import evaluate_epistemic_graph


def test_tracked_nist_readiness_can_seed_a_provenance_bound_claim_graph() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    mission = (
        repository_root
        / "configs"
        / "research"
        / "autonomous_materials_research_mission.v1.json"
    )
    program = build_research_program(mission, repository_root=repository_root)
    nist = next(
        item for item in program["workstreams"] if item["workstream_id"] == "nist-ambench"
    )
    planning_state = nist["planning_state"]
    readiness = next(
        item
        for item in planning_state["evidence_bindings"]
        if item["role"] == "planning_readiness"
    )

    graph = {
        "schema_version": "1.0",
        "graph_id": "nist-current-scope-epistemic-graph-v1",
        "research_scope": "Current NIST AM-Bench stronger-use readiness",
        "nodes": [
            {
                "node_id": "nist-readiness-evidence",
                "node_type": "evidence",
                "statement": (
                    "The frozen NIST planning-readiness artifact bounds the current tracked "
                    "case to Diagnostic/descriptive use."
                ),
                "evidence_binding": {
                    "workstream_id": "nist-ambench",
                    "role": readiness["role"],
                    "sha256": readiness["sha256"],
                },
                "evidence_quality": "supported",
            },
            {
                "node_id": "current-stronger-use-claim",
                "node_type": "claim",
                "statement": (
                    "The current tracked NIST case does not yet justify predictive, causal, "
                    "or engineering use."
                ),
            },
        ],
        "edges": [
            {
                "edge_id": "readiness-supports-current-boundary",
                "source_node_id": "nist-readiness-evidence",
                "target_node_id": "current-stronger-use-claim",
                "relation": "supports",
                "assessment_level": "domain_verified",
                "rationale": (
                    "The frozen planning-readiness artifact is the domain policy artifact "
                    "that records the current stronger-use boundary."
                ),
                "active": True,
                "verification_artifact": {
                    "role": "nist_planning_readiness_verifier",
                    "path": readiness["path"],
                    "sha256": readiness["sha256"],
                },
            }
        ],
    }

    result = evaluate_epistemic_graph(
        graph,
        program_state=program,
        artifact_root=repository_root,
    )

    assessment = result["assessments"][0]
    assert assessment["status"] == "provisionally_supported"
    assert assessment["final_positive_support_granted"] is False
    assert assessment["confidence_score"] is None
