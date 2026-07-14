"""Small in-memory evidence graph for diagnostic reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvidenceGraph:
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: list[dict[str, str]] = field(default_factory=list)

    def add_node(self, node_id: str, node_type: str, **metadata: Any) -> None:
        self.nodes[node_id] = {"node_id": node_id, "node_type": node_type, **metadata}

    def add_edge(self, source: str, target: str, edge_type: str) -> None:
        self.edges.append({"source": source, "target": target, "edge_type": edge_type})

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [self.nodes[key] for key in sorted(self.nodes)],
            "edges": sorted(self.edges, key=lambda edge: (edge["source"], edge["target"], edge["edge_type"])),
        }


def build_evidence_graph(
    *,
    run: dict[str, Any],
    artifacts: list[dict[str, Any]],
    validation_policy_id: str | None,
    trust_policy_id: str | None,
    claim_ids: tuple[str, ...],
) -> dict[str, Any]:
    graph = EvidenceGraph()
    run_id = str(run["run_id"])
    graph.add_node(run_id, "run", status=run.get("status"), stage=run.get("stage"))
    if run.get("code_commit"):
        node_id = f"code:{run['code_commit']}"
        graph.add_node(node_id, "code_commit")
        graph.add_edge(run_id, node_id, "governed_by")
    if run.get("config_sha256"):
        node_id = f"config:{run['config_sha256']}"
        graph.add_node(node_id, "config")
        graph.add_edge(run_id, node_id, "governed_by")
    if validation_policy_id:
        node_id = f"policy:{validation_policy_id}"
        graph.add_node(node_id, "validation")
        graph.add_edge(run_id, node_id, "validated_by")
    if trust_policy_id:
        node_id = f"policy:{trust_policy_id}"
        graph.add_node(node_id, "trust_status")
        graph.add_edge(run_id, node_id, "governed_by")
    for artifact in artifacts:
        node_id = f"artifact:{artifact['artifact_record_id']}"
        graph.add_node(node_id, "artifact", artifact_id=artifact["artifact_id"], role=artifact["role"])
        graph.add_edge(run_id, node_id, "consumed" if artifact["role"] == "input" else "produced")
    for claim_id in claim_ids:
        node_id = f"claim:{claim_id}"
        graph.add_node(node_id, "claim")
        if trust_policy_id:
            graph.add_edge(f"policy:{trust_policy_id}", node_id, "supports")
        else:
            graph.add_edge(run_id, node_id, "requires")
    return graph.to_dict()
