from src.platform_core.claim_diagnostics import evaluate_claim_id
from src.platform_core.domain_knowledge import build_default_domain_knowledge_registry
from src.platform_core.evidence_graph import build_scientific_evidence_graph
from src.platform_core.scientific_constraint_registry import build_default_scientific_constraint_registry


def test_scientific_claims_require_registered_evidence():
    unsupported = evaluate_claim_id(
        "phase_identification_supported",
        allowed_claims=(),
        prohibited_claims=(),
        available_evidence=(),
    )
    supported_by_policy_but_missing_science = evaluate_claim_id(
        "dimensionally_consistent",
        allowed_claims=("dimensionally consistent",),
        prohibited_claims=(),
        available_evidence=(),
    )

    assert unsupported.status == "unsupported"
    assert unsupported.reason_code == "missing_scientific_constraint_evidence"
    assert supported_by_policy_but_missing_science.status == "unsupported"


def test_scientific_evidence_graph_links_packs_constraints_variables_units_and_findings():
    constraint_registry = build_default_scientific_constraint_registry()
    pack_registry = build_default_domain_knowledge_registry()
    constraints = [constraint_registry.get("xrd.bragg.geometry").to_dict()]
    packs = [pack_registry.get("xrd_crystallography_basic_v1").to_dict()]
    finding = {
        "finding_id": "finding-a",
        "constraint_id": "xrd.bragg.geometry",
        "status": "conditionally_consistent",
        "severity": "info",
        "category": "scientific_consistency",
    }

    graph = build_scientific_evidence_graph(constraints=constraints, knowledge_packs=packs, findings=[finding])

    node_types = {node["node_type"] for node in graph["nodes"]}
    assert {"scientific_registry", "domain_knowledge_pack", "scientific_constraint", "scientific_variable", "unit", "scientific_finding"} <= node_types
    assert graph["edges"] == sorted(graph["edges"], key=lambda edge: (edge["source"], edge["target"], edge["edge_type"]))
