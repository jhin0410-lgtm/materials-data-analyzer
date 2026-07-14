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


def build_scientific_evidence_graph(
    *,
    constraints: list[dict[str, Any]],
    knowledge_packs: list[dict[str, Any]],
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a small graph for scientific metadata contracts.

    This helper is intentionally metadata-only. It does not evaluate equations,
    read datasets, or infer physical mechanisms.
    """

    graph = EvidenceGraph()
    graph.add_node("scientific_registry", "scientific_registry")
    for pack in knowledge_packs:
        pack_id = str(pack["pack_id"])
        graph.add_node(f"knowledge_pack:{pack_id}", "domain_knowledge_pack", domain=pack.get("domain"), status=pack.get("status"))
        graph.add_edge("scientific_registry", f"knowledge_pack:{pack_id}", "contains")
        for constraint_id in pack.get("constraint_ids", []):
            graph.add_edge(f"knowledge_pack:{pack_id}", f"constraint:{constraint_id}", "references")
    for constraint in constraints:
        constraint_id = str(constraint["constraint_id"])
        graph.add_node(
            f"constraint:{constraint_id}",
            "scientific_constraint",
            domain=constraint.get("domain"),
            category=constraint.get("category"),
            status=constraint.get("status"),
            evaluator_id=constraint.get("evaluator_id"),
        )
        graph.add_edge("scientific_registry", f"constraint:{constraint_id}", "contains")
        for variable in constraint.get("required_variables", []):
            variable_id = str(variable["name"])
            graph.add_node(f"variable:{variable_id}", "scientific_variable", dimension=variable.get("dimension"), expected_unit=variable.get("expected_unit"))
            graph.add_edge(f"constraint:{constraint_id}", f"variable:{variable_id}", "requires")
        for unit in constraint.get("expected_units", {}).values():
            graph.add_node(f"unit:{unit}", "unit")
            graph.add_edge(f"constraint:{constraint_id}", f"unit:{unit}", "expects_unit")
    for finding in findings or []:
        finding_id = str(finding["finding_id"])
        graph.add_node(f"scientific_finding:{finding_id}", "scientific_finding", status=finding.get("status"), severity=finding.get("severity"), category=finding.get("category"))
        graph.add_edge(f"scientific_finding:{finding_id}", f"constraint:{finding['constraint_id']}", "evaluates")
    return graph.to_dict()


def build_scientific_execution_evidence_graph(
    *,
    execution_id: str,
    knowledge_pack: dict[str, Any],
    constraints: list[dict[str, Any]],
    inputs: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    claim_evaluations: list[dict[str, Any]],
    trust_policy_id: str | None = None,
) -> dict[str, Any]:
    """Build a small graph for one bounded scientific execution."""

    graph = EvidenceGraph()
    execution_node = f"scientific_execution:{execution_id}"
    graph.add_node(execution_node, "scientific_execution")
    pack_node = f"knowledge_pack:{knowledge_pack['pack_id']}"
    graph.add_node(pack_node, "domain_knowledge_pack", domain=knowledge_pack.get("domain"))
    graph.add_edge(execution_node, pack_node, "uses")
    if trust_policy_id:
        policy_node = f"trust_policy:{trust_policy_id}"
        graph.add_node(policy_node, "trust_policy")
        graph.add_edge(execution_node, policy_node, "governed_by")
    for constraint in constraints:
        constraint_node = f"constraint:{constraint['constraint_id']}"
        graph.add_node(constraint_node, "scientific_constraint", evaluator_id=constraint.get("evaluator_id"))
        graph.add_edge(execution_node, constraint_node, "evaluates")
        if constraint.get("evaluator_id"):
            evaluator_node = f"evaluator:{constraint['evaluator_id']}"
            graph.add_node(evaluator_node, "scientific_evaluator")
            graph.add_edge(constraint_node, evaluator_node, "implemented_by")
    for item in inputs:
        variable_node = f"variable:{item['variable_id']}"
        graph.add_node(variable_node, "scientific_variable", semantic_status=item.get("semantic_status"))
        graph.add_edge(variable_node, execution_node, "provides")
        if item.get("unit"):
            unit_node = f"unit:{item['unit']}"
            graph.add_node(unit_node, "unit")
            graph.add_edge(variable_node, unit_node, "has_unit")
    for finding in findings:
        finding_node = f"scientific_finding:{finding['finding_id']}"
        graph.add_node(finding_node, "scientific_finding", status=finding.get("status"), severity=finding.get("severity"))
        graph.add_edge(finding_node, f"constraint:{finding['constraint_id']}", "derived_from")
        for evidence_ref in finding.get("evidence_refs", []):
            if evidence_ref.startswith("scientific_evidence:"):
                graph.add_edge(finding_node, f"claim:{evidence_ref.split(':', 1)[1]}", "supports_or_limits")
    for claim in claim_evaluations:
        claim_node = f"claim:{claim['claim_id']}"
        graph.add_node(claim_node, "claim", status=claim.get("status"))
        if trust_policy_id:
            graph.add_edge(claim_node, f"trust_policy:{trust_policy_id}", "governed_by")
    return graph.to_dict()
