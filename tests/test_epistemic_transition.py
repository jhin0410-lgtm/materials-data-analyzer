from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.epistemic_transition import (
    EpistemicTransitionError,
    apply_epistemic_transition_files,
)


def _write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _program_state(*, with_evidence: bool = False) -> dict[str, object]:
    if not with_evidence:
        return {"workstreams": []}
    return {
        "workstreams": [
            {
                "workstream_id": "benchmark",
                "planning_state": {
                    "evidence_bindings": [
                        {"role": "measured_source", "sha256": "a" * 64}
                    ]
                },
            }
        ]
    }


def _base_graph(*, claim_scope: str = "structural", with_verified_support: bool = False) -> dict[str, object]:
    graph: dict[str, object] = {
        "schema_version": "1.0",
        "graph_id": "graph-v1",
        "research_scope": "bounded transition regression",
        "nodes": [
            {
                "node_id": "question-1",
                "node_type": "research_question",
                "statement": "What does the bounded result establish?",
            },
            {
                "node_id": "hypothesis-1",
                "node_type": "hypothesis",
                "statement": "The target proposition holds within the declared scope.",
                "metadata": {"claim_scope": claim_scope},
            },
        ],
        "edges": [
            {
                "edge_id": "motivation-1",
                "source_node_id": "question-1",
                "target_node_id": "hypothesis-1",
                "relation": "motivates",
                "assessment_level": "proposal",
                "rationale": "The question motivates the hypothesis.",
                "active": True,
            }
        ],
    }
    if with_verified_support:
        graph["nodes"].append(
            {
                "node_id": "prior-simulation",
                "node_type": "simulation",
                "statement": "Prior structural simulation result.",
                "execution_status": "completed",
                "artifact_bindings": [],
            }
        )
    return graph


def _proposal(
    *,
    base_sha: str,
    node_type: str = "simulation",
    origin: str = "authorized_local_simulation",
    action_class: str = "simulation",
    execution_mode: str = "typed_local_action",
    relation: str = "supports",
    input_evidence: list[dict[str, str]] | None = None,
    result_sha: str,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "transition_id": "transition-1",
        "base_graph_id": "graph-v1",
        "base_graph_sha256": base_sha,
        "new_graph_id": "graph-v2",
        "target_node_id": "hypothesis-1",
        "source_action": {
            "action_id": "action-1",
            "action_class": action_class,
            "action_version": "1.0",
            "execution_mode": execution_mode,
        },
        "result_node": {
            "node_id": "result-1",
            "node_type": node_type,
            "statement": "A bounded research result was completed.",
            "artifact_bindings": [
                {"role": "primary_result", "path": "result.json", "sha256": result_sha}
            ],
            "metadata": {"result_origin": origin},
        },
        "input_evidence_bindings": input_evidence or [],
        "proposed_inference": {
            "tests_edge_id": "tests-1",
            "inference_edge_id": "inference-1",
            "relation": relation,
            "rationale": "The result bears on the target under its declared scope.",
        },
        "limitations": ["The result is bounded to this regression scope."],
    }


def _verification(
    *,
    proposal_sha: str,
    base_sha: str,
    relation: str = "supports",
    inference_scope: str = "structural",
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "decision_id": "verification-1",
        "transition_id": "transition-1",
        "proposal_sha256": proposal_sha,
        "base_graph_sha256": base_sha,
        "result_node_id": "result-1",
        "target_node_id": "hypothesis-1",
        "relation": relation,
        "inference_scope": inference_scope,
        "verifier_id": "bounded-domain-verifier-v1",
        "rationale": "The exact result artifact satisfies the declared structural verification rule.",
        "limitations": ["No final positive scientific truth is granted."],
        "domain_verified": True,
    }


def _fixture_files(tmp_path: Path, *, claim_scope: str = "structural", relation: str = "supports") -> tuple[Path, Path, str, str]:
    result_file = tmp_path / "result.json"
    result_sha = _write_json(result_file, {"rank_before": 3, "rank_after": 4})
    base_file = tmp_path / "base_graph.json"
    base_sha = _write_json(base_file, _base_graph(claim_scope=claim_scope))
    proposal_file = tmp_path / "proposal.json"
    proposal_sha = _write_json(
        proposal_file,
        _proposal(base_sha=base_sha, relation=relation, result_sha=result_sha),
    )
    return base_file, proposal_file, base_sha, proposal_sha


def test_proposal_only_result_is_recorded_without_verified_status_change(tmp_path: Path) -> None:
    base_file, proposal_file, _, _ = _fixture_files(tmp_path)

    result = apply_epistemic_transition_files(
        base_graph_path=base_file,
        proposal_path=proposal_file,
        program_state=_program_state(),
        artifact_root=tmp_path,
        output_dir=tmp_path / "out",
    )

    assert result["domain_verification_applied"] is False
    assert result["inference_assessment_level"] == "proposal"
    assert result["target_before"]["status"] == "inconclusive"
    assert result["target_after"]["status"] == "inconclusive"
    assert result["autonomy_boundary"]["result_execution_success_treated_as_scientific_verification"] is False


def test_verified_structural_simulation_support_is_only_provisional(tmp_path: Path) -> None:
    base_file, proposal_file, base_sha, proposal_sha = _fixture_files(tmp_path)
    verification_file = tmp_path / "verification.json"
    _write_json(
        verification_file,
        _verification(proposal_sha=proposal_sha, base_sha=base_sha),
    )

    result = apply_epistemic_transition_files(
        base_graph_path=base_file,
        proposal_path=proposal_file,
        verification_decision_path=verification_file,
        program_state=_program_state(),
        artifact_root=tmp_path,
        output_dir=tmp_path / "out",
    )

    assert result["domain_verification_applied"] is True
    assert result["inference_assessment_level"] == "domain_verified"
    assert result["target_after"]["status"] == "provisionally_supported"
    assert result["target_after"]["final_positive_support_granted"] is False


def test_verified_simulation_cannot_validate_empirical_claim(tmp_path: Path) -> None:
    base_file, proposal_file, base_sha, proposal_sha = _fixture_files(
        tmp_path, claim_scope="empirical"
    )
    verification_file = tmp_path / "verification.json"
    _write_json(
        verification_file,
        _verification(
            proposal_sha=proposal_sha,
            base_sha=base_sha,
            inference_scope="structural",
        ),
    )

    with pytest.raises(EpistemicTransitionError, match="incompatible with target claim_scope"):
        apply_epistemic_transition_files(
            base_graph_path=base_file,
            proposal_path=proposal_file,
            verification_decision_path=verification_file,
            program_state=_program_state(),
            artifact_root=tmp_path,
            output_dir=tmp_path / "out",
        )
    assert not (tmp_path / "out").exists()


def test_simulation_cannot_receive_empirical_inference_scope(tmp_path: Path) -> None:
    base_file, proposal_file, base_sha, proposal_sha = _fixture_files(
        tmp_path, claim_scope="empirical"
    )
    verification_file = tmp_path / "verification.json"
    _write_json(
        verification_file,
        _verification(
            proposal_sha=proposal_sha,
            base_sha=base_sha,
            inference_scope="empirical_derived",
        ),
    )

    with pytest.raises(EpistemicTransitionError, match="simulation results cannot receive empirical"):
        apply_epistemic_transition_files(
            base_graph_path=base_file,
            proposal_path=proposal_file,
            verification_decision_path=verification_file,
            program_state=_program_state(),
            artifact_root=tmp_path,
            output_dir=tmp_path / "out",
        )


def test_empirical_derived_analysis_requires_bound_input_evidence(tmp_path: Path) -> None:
    result_file = tmp_path / "result.json"
    result_sha = _write_json(result_file, {"analysis": "derived"})
    base_file = tmp_path / "base_graph.json"
    base_sha = _write_json(base_file, _base_graph(claim_scope="empirical"))
    proposal_file = tmp_path / "proposal.json"
    proposal_sha = _write_json(
        proposal_file,
        _proposal(
            base_sha=base_sha,
            node_type="analysis",
            origin="authorized_local_analysis",
            action_class="existing_data_reanalysis",
            relation="supports",
            result_sha=result_sha,
        ),
    )
    verification_file = tmp_path / "verification.json"
    _write_json(
        verification_file,
        _verification(
            proposal_sha=proposal_sha,
            base_sha=base_sha,
            inference_scope="empirical_derived",
        ),
    )

    with pytest.raises(EpistemicTransitionError, match="requires bound empirical input evidence"):
        apply_epistemic_transition_files(
            base_graph_path=base_file,
            proposal_path=proposal_file,
            verification_decision_path=verification_file,
            program_state=_program_state(),
            artifact_root=tmp_path,
            output_dir=tmp_path / "out",
        )


def test_empirical_derived_analysis_can_verify_with_bound_input_evidence(tmp_path: Path) -> None:
    result_file = tmp_path / "result.json"
    result_sha = _write_json(result_file, {"analysis": "derived"})
    base_file = tmp_path / "base_graph.json"
    base_sha = _write_json(base_file, _base_graph(claim_scope="empirical"))
    input_binding = {"workstream_id": "benchmark", "role": "measured_source", "sha256": "a" * 64}
    proposal_file = tmp_path / "proposal.json"
    proposal_sha = _write_json(
        proposal_file,
        _proposal(
            base_sha=base_sha,
            node_type="analysis",
            origin="authorized_local_analysis",
            action_class="existing_data_reanalysis",
            input_evidence=[input_binding],
            result_sha=result_sha,
        ),
    )
    verification_file = tmp_path / "verification.json"
    _write_json(
        verification_file,
        _verification(
            proposal_sha=proposal_sha,
            base_sha=base_sha,
            inference_scope="empirical_derived",
        ),
    )

    result = apply_epistemic_transition_files(
        base_graph_path=base_file,
        proposal_path=proposal_file,
        verification_decision_path=verification_file,
        program_state=_program_state(with_evidence=True),
        artifact_root=tmp_path,
        output_dir=tmp_path / "out",
    )
    assert result["target_after"]["status"] == "provisionally_supported"


def test_verified_falsification_becomes_first_class_epistemic_state(tmp_path: Path) -> None:
    base_file, proposal_file, base_sha, proposal_sha = _fixture_files(
        tmp_path, relation="falsifies"
    )
    verification_file = tmp_path / "verification.json"
    _write_json(
        verification_file,
        _verification(
            proposal_sha=proposal_sha,
            base_sha=base_sha,
            relation="falsifies",
        ),
    )

    result = apply_epistemic_transition_files(
        base_graph_path=base_file,
        proposal_path=proposal_file,
        verification_decision_path=verification_file,
        program_state=_program_state(),
        artifact_root=tmp_path,
        output_dir=tmp_path / "out",
    )
    assert result["target_after"]["status"] == "falsified_within_verified_scope"


def test_proposal_base_graph_sha_mismatch_fails_before_output(tmp_path: Path) -> None:
    base_file, proposal_file, _, _ = _fixture_files(tmp_path)
    proposal = json.loads(proposal_file.read_text(encoding="utf-8"))
    proposal["base_graph_sha256"] = "0" * 64
    _write_json(proposal_file, proposal)

    with pytest.raises(EpistemicTransitionError, match="base_graph_sha256"):
        apply_epistemic_transition_files(
            base_graph_path=base_file,
            proposal_path=proposal_file,
            program_state=_program_state(),
            artifact_root=tmp_path,
            output_dir=tmp_path / "out",
        )
    assert not (tmp_path / "out").exists()


def test_verifier_must_bind_exact_proposal_bytes(tmp_path: Path) -> None:
    base_file, proposal_file, base_sha, _ = _fixture_files(tmp_path)
    verification_file = tmp_path / "verification.json"
    _write_json(
        verification_file,
        _verification(proposal_sha="f" * 64, base_sha=base_sha),
    )

    with pytest.raises(EpistemicTransitionError, match="proposal_sha256"):
        apply_epistemic_transition_files(
            base_graph_path=base_file,
            proposal_path=proposal_file,
            verification_decision_path=verification_file,
            program_state=_program_state(),
            artifact_root=tmp_path,
            output_dir=tmp_path / "out",
        )


def test_result_artifact_checksum_mismatch_fails_before_output(tmp_path: Path) -> None:
    base_file, proposal_file, _, _ = _fixture_files(tmp_path)
    proposal = json.loads(proposal_file.read_text(encoding="utf-8"))
    proposal["result_node"]["artifact_bindings"][0]["sha256"] = "0" * 64
    _write_json(proposal_file, proposal)

    with pytest.raises(EpistemicTransitionError, match="result artifact checksum mismatch"):
        apply_epistemic_transition_files(
            base_graph_path=base_file,
            proposal_path=proposal_file,
            program_state=_program_state(),
            artifact_root=tmp_path,
            output_dir=tmp_path / "out",
        )
    assert not (tmp_path / "out").exists()


def test_successor_lineage_binds_parent_proposal_verifier_and_result(tmp_path: Path) -> None:
    base_file, proposal_file, base_sha, proposal_sha = _fixture_files(tmp_path)
    verification_file = tmp_path / "verification.json"
    verification_sha = _write_json(
        verification_file,
        _verification(proposal_sha=proposal_sha, base_sha=base_sha),
    )

    result = apply_epistemic_transition_files(
        base_graph_path=base_file,
        proposal_path=proposal_file,
        verification_decision_path=verification_file,
        program_state=_program_state(),
        artifact_root=tmp_path,
        output_dir=tmp_path / "out",
    )
    successor = json.loads((tmp_path / "out" / "epistemic_graph.json").read_text(encoding="utf-8"))
    lineage = successor["metadata"]["transition_lineage"][-1]
    assert lineage["parent_graph_sha256"] == base_sha
    assert lineage["proposal_sha256"] == proposal_sha
    assert lineage["verification_decision_sha256"] == verification_sha
    assert lineage["result_node_id"] == "result-1"
    assert result["successor_graph"]["sha256"] == hashlib.sha256(
        (tmp_path / "out" / "epistemic_graph.json").read_bytes()
    ).hexdigest()


def test_existing_output_directory_is_rejected_without_mutating_base(tmp_path: Path) -> None:
    base_file, proposal_file, _, _ = _fixture_files(tmp_path)
    before = base_file.read_bytes()
    output = tmp_path / "out"
    output.mkdir()

    with pytest.raises(EpistemicTransitionError, match="must not already exist"):
        apply_epistemic_transition_files(
            base_graph_path=base_file,
            proposal_path=proposal_file,
            program_state=_program_state(),
            artifact_root=tmp_path,
            output_dir=output,
        )
    assert base_file.read_bytes() == before


def test_external_physical_result_is_ingested_not_executed(tmp_path: Path) -> None:
    result_file = tmp_path / "result.json"
    result_sha = _write_json(result_file, {"measurement": 1.0})
    base_file = tmp_path / "base_graph.json"
    base_sha = _write_json(base_file, _base_graph(claim_scope="empirical"))
    proposal_file = tmp_path / "proposal.json"
    proposal_sha = _write_json(
        proposal_file,
        _proposal(
            base_sha=base_sha,
            node_type="experiment",
            origin="external_physical_experiment",
            action_class="physical_experiment",
            execution_mode="external_result_ingest",
            result_sha=result_sha,
        ),
    )
    verification_file = tmp_path / "verification.json"
    _write_json(
        verification_file,
        _verification(
            proposal_sha=proposal_sha,
            base_sha=base_sha,
            inference_scope="empirical_direct",
        ),
    )

    result = apply_epistemic_transition_files(
        base_graph_path=base_file,
        proposal_path=proposal_file,
        verification_decision_path=verification_file,
        program_state=_program_state(),
        artifact_root=tmp_path,
        output_dir=tmp_path / "out",
    )
    assert result["target_after"]["status"] == "provisionally_supported"
    assert result["autonomy_boundary"]["physical_experiment_execution_performed"] is False
