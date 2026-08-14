from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.epistemic_graph import (
    EpistemicGraphError,
    evaluate_epistemic_graph,
    validate_epistemic_graph,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _program_state() -> dict[str, object]:
    return {
        "workstreams": [
            {
                "workstream_id": "nist",
                "planning_state": {
                    "evidence_bindings": [
                        {
                            "role": "design_readiness",
                            "path": "configs/readiness.json",
                            "sha256": "a" * 64,
                        }
                    ]
                },
            }
        ]
    }


def _evidence_node() -> dict[str, object]:
    return {
        "node_id": "e1",
        "node_type": "evidence",
        "statement": "The verified design audit records the current structural state.",
        "evidence_binding": {
            "workstream_id": "nist",
            "role": "design_readiness",
            "sha256": "a" * 64,
        },
        "evidence_quality": "supported",
    }


def _hypothesis_node() -> dict[str, object]:
    return {
        "node_id": "h1",
        "node_type": "hypothesis",
        "statement": "The augmented design is structurally identifiable for the interaction term.",
    }


def _graph(edge: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "graph_id": "g1",
        "research_scope": "NIST design-readiness hypothesis test",
        "nodes": [_evidence_node(), _hypothesis_node()],
        "edges": [edge],
    }


def _edge(
    *,
    relation: str,
    assessment_level: str,
    verifier: Path | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "edge_id": f"edge-{relation}-{assessment_level}",
        "source_node_id": "e1",
        "target_node_id": "h1",
        "relation": relation,
        "assessment_level": assessment_level,
        "rationale": "The relation is assessed under the frozen design-readiness rule.",
        "active": True,
    }
    if verifier is not None:
        result["verification_artifact"] = {
            "role": "domain_verifier",
            "path": verifier.name,
            "sha256": _sha(verifier),
        }
    return result


def test_proposal_support_does_not_change_epistemic_status(tmp_path: Path) -> None:
    result = evaluate_epistemic_graph(
        _graph(_edge(relation="supports", assessment_level="proposal")),
        program_state=_program_state(),
        artifact_root=tmp_path,
    )

    assessment = result["assessments"][0]
    assert assessment["status"] == "inconclusive"
    assert assessment["final_positive_support_granted"] is False
    assert result["autonomy_boundary"]["proposal_relations_affect_status"] is False


def test_domain_verified_support_is_only_provisional(tmp_path: Path) -> None:
    verifier = tmp_path / "verification.json"
    verifier.write_text('{"rank_verified": true}\n', encoding="utf-8")

    result = evaluate_epistemic_graph(
        _graph(
            _edge(
                relation="supports",
                assessment_level="domain_verified",
                verifier=verifier,
            )
        ),
        program_state=_program_state(),
        artifact_root=tmp_path,
    )

    assessment = result["assessments"][0]
    assert assessment["status"] == "provisionally_supported"
    assert assessment["final_positive_support_granted"] is False
    assert assessment["domain_closeout_required_for_positive_conclusion"] is True
    assert assessment["confidence_score"] is None


def test_verified_support_and_contradiction_are_contested(tmp_path: Path) -> None:
    support = tmp_path / "support.json"
    contradiction = tmp_path / "contradiction.json"
    support.write_text("support\n", encoding="utf-8")
    contradiction.write_text("contradiction\n", encoding="utf-8")
    graph = _graph(
        _edge(
            relation="supports",
            assessment_level="domain_verified",
            verifier=support,
        )
    )
    graph["edges"].append(  # type: ignore[index]
        {
            **_edge(
                relation="contradicts",
                assessment_level="domain_verified",
                verifier=contradiction,
            ),
            "edge_id": "edge-contradiction",
        }
    )

    result = evaluate_epistemic_graph(
        graph,
        program_state=_program_state(),
        artifact_root=tmp_path,
    )

    assessment = result["assessments"][0]
    assert assessment["status"] == "contested"
    assert result["conflict_count"] == 1


def test_verified_falsification_is_first_class_and_dominates_support(tmp_path: Path) -> None:
    support = tmp_path / "support.json"
    falsifier = tmp_path / "falsifier.json"
    support.write_text("support\n", encoding="utf-8")
    falsifier.write_text("falsified\n", encoding="utf-8")
    graph = _graph(
        _edge(
            relation="supports",
            assessment_level="domain_verified",
            verifier=support,
        )
    )
    graph["edges"].append(  # type: ignore[index]
        {
            **_edge(
                relation="falsifies",
                assessment_level="domain_verified",
                verifier=falsifier,
            ),
            "edge_id": "edge-falsifier",
        }
    )

    result = evaluate_epistemic_graph(
        graph,
        program_state=_program_state(),
        artifact_root=tmp_path,
    )

    assert result["assessments"][0]["status"] == "falsified_within_verified_scope"
    assert result["falsified_count"] == 1


def test_domain_verified_relation_requires_checksum_bound_verifier(tmp_path: Path) -> None:
    with pytest.raises(EpistemicGraphError, match="require verification_artifact"):
        validate_epistemic_graph(
            _graph(_edge(relation="supports", assessment_level="domain_verified")),
            program_state=_program_state(),
            artifact_root=tmp_path,
        )


def test_verifier_checksum_mismatch_is_rejected(tmp_path: Path) -> None:
    verifier = tmp_path / "verification.json"
    verifier.write_text("verified\n", encoding="utf-8")
    edge = _edge(
        relation="supports",
        assessment_level="domain_verified",
        verifier=verifier,
    )
    edge["verification_artifact"]["sha256"] = "b" * 64  # type: ignore[index]

    with pytest.raises(EpistemicGraphError, match="checksum mismatch"):
        validate_epistemic_graph(
            _graph(edge),
            program_state=_program_state(),
            artifact_root=tmp_path,
        )


def test_evidence_node_must_bind_verified_program_evidence(tmp_path: Path) -> None:
    graph = _graph(_edge(relation="supports", assessment_level="proposal"))
    graph["nodes"][0]["evidence_binding"]["sha256"] = "b" * 64  # type: ignore[index]

    with pytest.raises(EpistemicGraphError, match="not present in the verified mission program state"):
        validate_epistemic_graph(
            graph,
            program_state=_program_state(),
            artifact_root=tmp_path,
        )


def test_completed_simulation_requires_result_artifact(tmp_path: Path) -> None:
    graph = {
        "schema_version": "1.0",
        "graph_id": "g-sim",
        "research_scope": "simulation boundary",
        "nodes": [
            {
                "node_id": "s1",
                "node_type": "simulation",
                "statement": "A bounded design simulation was executed.",
                "execution_status": "completed",
                "artifact_bindings": [],
            },
            _hypothesis_node(),
        ],
        "edges": [],
    }

    with pytest.raises(EpistemicGraphError, match="require artifact_bindings"):
        validate_epistemic_graph(
            graph,
            program_state=_program_state(),
            artifact_root=tmp_path,
        )


def test_diagnostic_relation_is_reported_but_not_promoted(tmp_path: Path) -> None:
    result = evaluate_epistemic_graph(
        _graph(_edge(relation="contradicts", assessment_level="diagnostic")),
        program_state=_program_state(),
        artifact_root=tmp_path,
    )

    assessment = result["assessments"][0]
    assert assessment["status"] == "inconclusive"
    assert assessment["diagnostic_relation_edges"]
    assert result["autonomy_boundary"]["diagnostic_relations_affect_verified_status"] is False
