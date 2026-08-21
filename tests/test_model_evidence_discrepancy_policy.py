from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from materials_data_analyzer.research_loop import (
    build_discrepancy_planning_handoff,
    build_model_evidence_discrepancy_report,
    validate_model_evidence_discrepancy_report,
)
from materials_data_analyzer.research_loop.model_evidence_discrepancy_policy import (
    ModelEvidenceDiscrepancyPolicyError,
    _priority_sort,
)


def _fixture_module() -> ModuleType:
    path = Path(__file__).with_name("test_model_evidence_discrepancy.py")
    spec = importlib.util.spec_from_file_location("_model_evidence_fixture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_FIXTURE = _fixture_module()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _replication_proof(root: Path, *, evidence_id: str = "evidence-1") -> Path:
    replicate_bindings = []
    for index in (1, 2):
        path = root / f"replicate-{index}.json"
        path.write_text(
            json.dumps({"replicate": index, "bounded": True}),
            encoding="utf-8",
        )
        replicate_bindings.append(
            {
                "replicate_id": f"replicate-{index}",
                "source_lineage_id": f"independent-lineage-{index}",
                "artifact_binding": {"path": str(path), "sha256": _sha(path)},
            }
        )
    verifier = root / "replication-independence-verifier.json"
    verifier.write_text(
        json.dumps(
            {
                "assessment": "domain_verified",
                "scope": "fixture declares the two source lineages independent",
            }
        ),
        encoding="utf-8",
    )
    proof = root / "replication-verification.json"
    proof.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "evidence_id": evidence_id,
                "target_node_id": "h1",
                "replicates": replicate_bindings,
                "independence_assessment": {
                    "assessment_level": "domain_verified",
                    "verification_artifact": {
                        "path": str(verifier),
                        "sha256": _sha(verifier),
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return proof


def _public_build(
    model: dict[str, object],
    *,
    graph: dict | None = None,
    evidence: Path | None = None,
    spec: dict | None = None,
    previous_report: dict | None = None,
    replication_proof: Path | None = None,
) -> dict:
    root = Path(model["root"])
    graph_value = graph or _FIXTURE._graph()
    evidence_path = evidence or _FIXTURE._empirical(
        root,
        model_value=float(model["model_value"]),
        delta=2.0,
    )
    spec_value = spec or _FIXTURE._comparison_spec(root)
    return build_model_evidence_discrepancy_report(
        model_adapter_id="reference-heat-conduction",
        action_report_path=Path(model["report_path"]),
        execution_request_path=Path(model["execution_request"]),
        empirical_evidence_path=evidence_path,
        comparison_spec=spec_value,
        evaluated_graph=graph_value,
        target_node_id="h1",
        artifact_root=root,
        previous_report=previous_report,
        replication_verification_path=replication_proof,
    )


def _diagnoses(report: dict) -> set[str]:
    return {str(item["diagnosis_type"]) for item in report["diagnoses"]}


def test_public_policy_requires_bound_replication_provenance_for_strong_comparison(
    tmp_path: Path,
) -> None:
    model = _FIXTURE._model_fixture(tmp_path)
    report = _public_build(model)

    assert "insufficient_empirical_evidence" in _diagnoses(report)
    assert "empirical_model_discrepancy" not in _diagnoses(report)
    assert report["quantitative_comparison"]["performed"] is False
    assert report["gates"]["empirical_sufficiency"]["replication_provenance_verified"] is False
    assert report["autonomy_boundary"]["scientific_status_changed"] is False


def test_bound_provenance_disjoint_replicates_unlock_only_the_declared_comparison(
    tmp_path: Path,
) -> None:
    model = _FIXTURE._model_fixture(tmp_path)
    root = Path(model["root"])
    proof = _replication_proof(root)
    graph = _FIXTURE._graph()
    report = _public_build(model, graph=graph, replication_proof=proof)

    assert _diagnoses(report) == {"empirical_model_discrepancy"}
    assert report["quantitative_comparison"]["performed"] is True
    assert report["gates"]["empirical_sufficiency"]["replication_provenance_verified"] is True
    assert (
        report["provenance_hardening"][
            "domain_authority_semantics_independently_adjudicated_by_policy"
        ]
        is False
    )
    verified = validate_model_evidence_discrepancy_report(
        report,
        evaluated_graph=graph,
    )
    assert verified["complete_report_deterministic_rebuild_verified"] is True
    assert verified["replication_provenance_verified"] is True


def test_self_recertified_diagnosis_mutation_fails_deterministic_rebuild(
    tmp_path: Path,
) -> None:
    model = _FIXTURE._model_fixture(tmp_path)
    root = Path(model["root"])
    proof = _replication_proof(root)
    graph = _FIXTURE._graph()
    report = _public_build(model, graph=graph, replication_proof=proof)

    tampered = json.loads(json.dumps(report))
    tampered["diagnoses"][0]["diagnosis_type"] = "agreement_within_declared_tolerance"
    tampered.pop("report_sha256")
    tampered["report_sha256"] = _canonical_sha256(tampered)

    with pytest.raises(
        ModelEvidenceDiscrepancyPolicyError,
        match="differs from deterministic reconstruction",
    ):
        validate_model_evidence_discrepancy_report(
            tampered,
            evaluated_graph=graph,
        )


def test_recursive_ancestry_cannot_cross_graph_identity(tmp_path: Path) -> None:
    model = _FIXTURE._model_fixture(tmp_path)
    root = Path(model["root"])
    proof = _replication_proof(root)
    graph = _FIXTURE._graph()
    first = _public_build(model, graph=graph, replication_proof=proof)

    substituted_graph = json.loads(json.dumps(graph))
    substituted_graph["graph_id"] = "different-graph-same-target"
    with pytest.raises(
        ModelEvidenceDiscrepancyPolicyError,
        match="graph/target ancestry differs",
    ):
        _public_build(
            model,
            graph=substituted_graph,
            previous_report=first,
            replication_proof=proof,
        )


def test_duplicate_replication_lineage_fails_closed(tmp_path: Path) -> None:
    model = _FIXTURE._model_fixture(tmp_path)
    root = Path(model["root"])
    proof = _replication_proof(root)
    payload = json.loads(proof.read_text(encoding="utf-8"))
    payload["replicates"][1]["source_lineage_id"] = payload["replicates"][0][
        "source_lineage_id"
    ]
    proof.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        ModelEvidenceDiscrepancyPolicyError,
        match="not provenance-disjoint",
    ):
        _public_build(model, replication_proof=proof)


def test_priority_sort_prevents_highest_after_high_inversion() -> None:
    actions = [
        {
            "proposal_id": "model-evidence:high-first",
            "action_class": "sensitivity_analysis",
            "description": "high",
            "rationale": "fixture",
            "information_gain_priority": "high",
            "information_gain_is_calibrated_probability": False,
            "execution_mode": "plan_only",
            "availability_asserted": False,
            "automatic_execution_authorized": False,
            "rank": 1,
        },
        {
            "proposal_id": "model-evidence:highest-second",
            "action_class": "protocol_semantic_reconciliation",
            "description": "highest",
            "rationale": "fixture",
            "information_gain_priority": "highest",
            "information_gain_is_calibrated_probability": False,
            "execution_mode": "plan_only",
            "availability_asserted": False,
            "automatic_execution_authorized": False,
            "rank": 2,
        },
    ]
    ranked = _priority_sort(actions)
    assert ranked[0]["proposal_id"] == "model-evidence:highest-second"
    assert [item["rank"] for item in ranked] == [1, 2]


def test_public_planning_handoff_rejects_self_recertified_source_report(
    tmp_path: Path,
) -> None:
    model = _FIXTURE._model_fixture(tmp_path)
    root = Path(model["root"])
    proof = _replication_proof(root)
    graph = _FIXTURE._graph()
    report = _public_build(model, graph=graph, replication_proof=proof)
    tampered = json.loads(json.dumps(report))
    tampered["ranked_next_actions"][0]["description"] = "tampered but self-rehashed"
    tampered.pop("report_sha256")
    tampered["report_sha256"] = _canonical_sha256(tampered)

    with pytest.raises(ModelEvidenceDiscrepancyPolicyError):
        build_discrepancy_planning_handoff(
            tampered,
            evaluated_graph=graph,
        )
