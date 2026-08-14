from __future__ import annotations

import hashlib
import json
from pathlib import Path

from materials_data_analyzer.research_loop import build_research_program
from materials_data_analyzer.research_loop.epistemic_gate import evaluate_epistemic_gate


ROOT = Path(__file__).resolve().parents[1]
MISSION = ROOT / "configs/research/autonomous_materials_research_mission.v1.json"


def test_real_nist_readiness_positive_boundary_routes_to_domain_closeout(tmp_path: Path) -> None:
    program = build_research_program(MISSION, repository_root=ROOT)
    nist = next(
        item for item in program["workstreams"] if item["workstream_id"] == "nist-ambench"
    )
    readiness = next(
        item
        for item in nist["planning_state"]["evidence_bindings"]
        if item["role"] == "planning_readiness"
    )
    graph = {
        "schema_version": "1.0",
        "graph_id": "nist-gate-benchmark-v1",
        "research_scope": "Current NIST stronger-use boundary",
        "nodes": [
            {
                "node_id": "readiness",
                "node_type": "evidence",
                "statement": "Frozen NIST planning readiness evidence.",
                "evidence_binding": {
                    "workstream_id": "nist-ambench",
                    "role": readiness["role"],
                    "sha256": readiness["sha256"],
                },
                "evidence_quality": "supported",
            },
            {
                "node_id": "stronger-use-boundary",
                "node_type": "claim",
                "statement": (
                    "The current NIST case remains bounded away from predictive, causal, and "
                    "engineering use."
                ),
            },
        ],
        "edges": [
            {
                "edge_id": "readiness-supports-boundary",
                "source_node_id": "readiness",
                "target_node_id": "stronger-use-boundary",
                "relation": "supports",
                "assessment_level": "domain_verified",
                "rationale": "The frozen readiness artifact is the domain verifier for this boundary.",
                "active": True,
                "verification_artifact": {
                    "role": "nist_planning_readiness_verifier",
                    "path": readiness["path"],
                    "sha256": readiness["sha256"],
                },
            }
        ],
    }
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")

    result = evaluate_epistemic_gate(
        adapter_id="nist-ambench-process-characterization",
        workstream_id="nist-ambench",
        target_node_ids=["stronger-use-boundary"],
        mission_path=MISSION,
        graph_path=graph_path,
        repository_root=ROOT,
        artifact_root=ROOT,
    )

    assert result["directive"]["directive"] == "domain_closeout_required"
    assert result["directive"]["automatic_execution_permitted"] is False
    assert result["graph_binding"]["sha256"] == hashlib.sha256(
        graph_path.read_bytes()
    ).hexdigest()
    assert result["autonomy_boundary"]["graph_revalidated_against_current_program_state"] is True
