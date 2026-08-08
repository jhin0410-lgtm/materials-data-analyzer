from __future__ import annotations

import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.external_evidence_registry import (
    ExternalEvidenceRegistryError,
    audit_external_evidence_registry,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "configs/research/materials_project_external_source_candidates.v1.json"


def _requirement() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "requirement_id": "materials-project-v1-3-source-disjoint-stability-evidence-v1",
        "domain": "materials_phase_stability",
        "objective": "fixture",
        "scientific_evidence_level": "DevelopmentDiagnostic",
        "source_independence_required": True,
        "prohibited_source_systems": ["Materials Project", "Materials Project-derived mirror"],
        "required_metadata_checks": [
            "dataset_identity_and_version",
            "structure_composition_identifiers",
            "calculation_code_and_version",
            "exchange_correlation_functional",
            "pseudopotential_or_basis",
            "energy_correction_scheme",
            "elemental_reference_energies",
            "competing_phase_inventory",
            "hull_construction_method",
        ],
        "required_semantic_checks": [
            "target_definition",
            "target_unit",
            "thermodynamic_reference_state",
            "energy_correction_semantics",
            "hull_construction_semantics",
            "composition_scope",
            "structure_identity_mapping",
        ],
        "domain_requirements": {"target": "energy_above_hull"},
        "automatic_acquisition_authorized": False,
        "model_fit_authorized": False,
        "external_validation_claim_authorized": False,
        "source_binding": {"fixture": True},
        "scientific_boundary": ["fixture"],
    }


def _write_requirement(tmp_path: Path) -> Path:
    path = tmp_path / "external_evidence_requirement.json"
    path.write_text(json.dumps(_requirement(), indent=2) + "\n", encoding="utf-8")
    return path


def _assessments_by_id(result: dict[str, object]) -> dict[str, dict[str, object]]:
    assessments = result["assessments"]
    assert isinstance(assessments, list)
    return {str(item["candidate_id"]): item for item in assessments}


def test_high_priority_candidates_fail_closed_before_target_acquisition(tmp_path: Path) -> None:
    result = audit_external_evidence_registry(
        requirement_path=_write_requirement(tmp_path),
        registry_path=REGISTRY_PATH,
        output_dir=tmp_path / "audit",
    )

    assert result["status"] == "external_source_candidate_screening_completed"
    assert result["candidate_count"] == 4
    assert result["eligible_candidate_count"] == 0
    assert result["disposition_counts"] == {
        "diagnostic_only": 1,
        "scientifically_ineligible": 3,
    }
    assert result["network_access_performed"] is False
    assert result["target_values_retrieved"] is False
    assert result["model_fit_performed"] is False
    assert result["external_validation_claim_authorized"] is False

    assessments = _assessments_by_id(result)

    oqmd = assessments["oqmd-v1-8-phase-stability"]
    assert oqmd["disposition"] == "scientifically_ineligible"
    assert oqmd["source_independence_satisfied"] is True
    assert set(oqmd["mismatches"]) == {
        "energy_correction_semantics",
        "thermodynamic_reference_state",
    }

    jarvis = assessments["nist-jarvis-dft-phase-stability"]
    assert jarvis["disposition"] == "scientifically_ineligible"
    assert jarvis["source_independence_satisfied"] is True
    assert set(jarvis["mismatches"]) == {
        "energy_correction_semantics",
        "thermodynamic_reference_state",
    }

    aflow = assessments["aflow-phase-stability"]
    assert aflow["disposition"] == "scientifically_ineligible"
    assert aflow["source_independence_satisfied"] is True
    assert aflow["mismatches"] == ()

    alexandria = assessments["alexandria-pbe-convex-hull"]
    assert alexandria["disposition"] == "diagnostic_only"
    assert alexandria["source_independence_satisfied"] is False
    assert alexandria["unresolved_metadata"]
    assert alexandria["unresolved_semantics"]

    assert (tmp_path / "audit/external_source_candidate_assessments.json").is_file()
    assert (tmp_path / "audit/external_source_candidate_assessments.csv").is_file()


def test_confirmed_source_dependence_precedes_unresolved_secondary_checks(tmp_path: Path) -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    alexandria = next(
        item
        for item in registry["candidates"]
        if item["candidate_id"] == "alexandria-pbe-convex-hull"
    )
    assert any(value == "unresolved" for value in alexandria["metadata_checks"].values())
    assert any(value == "unresolved" for value in alexandria["semantic_checks"].values())

    only_alexandria = {
        **registry,
        "registry_id": "alexandria-independence-precedence-fixture",
        "candidates": [alexandria],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(only_alexandria, indent=2) + "\n", encoding="utf-8")

    result = audit_external_evidence_registry(
        requirement_path=_write_requirement(tmp_path),
        registry_path=path,
        output_dir=tmp_path / "audit",
    )

    assessment = result["assessments"][0]
    assert assessment["disposition"] == "diagnostic_only"
    assert assessment["eligible_for_requirement"] is False


def test_registry_duplicate_candidate_id_fails_closed(tmp_path: Path) -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    registry["candidates"].append(dict(registry["candidates"][0]))
    duplicate = tmp_path / "registry.json"
    duplicate.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ExternalEvidenceRegistryError, match="duplicate candidate_id"):
        audit_external_evidence_registry(
            requirement_path=_write_requirement(tmp_path),
            registry_path=duplicate,
            output_dir=tmp_path / "audit",
        )


def test_candidate_must_cover_every_requirement_check(tmp_path: Path) -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    del registry["candidates"][0]["semantic_checks"]["structure_identity_mapping"]
    incomplete = tmp_path / "registry.json"
    incomplete.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(
        ExternalEvidenceRegistryError,
        match="does not cover all required checks",
    ):
        audit_external_evidence_registry(
            requirement_path=_write_requirement(tmp_path),
            registry_path=incomplete,
            output_dir=tmp_path / "audit",
        )
