from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.materials_project_external_evidence_requirement import (
    MaterialsProjectExternalEvidenceRequirementError,
    build_materials_project_external_evidence_requirement,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs/research/materials_project_external_evidence_requirement.v1.json"


def _readiness() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "readiness_id": "materials-project-v1-3-same-source-new-cohort-readiness-v1",
        "execution_status": "same_source_identity_inventory_completed",
        "scientific_evidence_level": "DevelopmentDiagnostic",
        "source_outcome": "no_new_same_source_identity_cohort",
        "materials_project_database_version": "2026.04.13",
        "cohort_independence": {
            "same_source_system": True,
            "source_system": "Materials Project",
            "material_id_disjoint_from_original_benchmark": True,
            "source_independence_established": False,
            "external_validation_ready": False,
            "basis": "fixture",
        },
        "current_identity_query": {
            "rows": 838,
            "unique_material_ids": 838,
            "chemical_system_groups": 167,
            "identity_fields_only": True,
            "target_property_queried": False,
            "policy_executed": False,
            "model_fit": False,
        },
        "original_benchmark": {
            "benchmark_id": "materials-project-v1-3-retrospective-closed-loop-v1",
            "rows": 838,
            "unique_material_ids": 838,
            "chemical_system_groups": 167,
        },
        "overlap": {
            "original_ids_still_present": 838,
            "original_ids_absent_from_current_query": 0,
            "new_material_ids_after_original_exclusion": 0,
        },
        "independent_candidate_inventory": {
            "rows": 0,
            "chemical_system_groups": 0,
            "candidate_ranking_performed": False,
            "target_values_used": False,
            "adequacy_threshold_applied": False,
        },
        "policy_v2_freeze_authorized": False,
        "independent_benchmark_execution_authorized": False,
    }


def _write_readiness(tmp_path: Path, payload: dict[str, object] | None = None) -> Path:
    path = tmp_path / "independent_source_readiness.json"
    path.write_text(
        json.dumps(payload or _readiness(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def test_requirement_is_bound_to_zero_new_id_readiness(tmp_path: Path) -> None:
    readiness = _write_readiness(tmp_path)
    output = tmp_path / "requirement"

    result = build_materials_project_external_evidence_requirement(
        readiness_path=readiness,
        config_path=CONFIG_PATH,
        output_dir=output,
    )

    assert result["requirement_id"] == (
        "materials-project-v1-3-source-disjoint-stability-evidence-v1"
    )
    assert result["source_independence_required"] is True
    assert result["automatic_acquisition_authorized"] is False
    assert result["model_fit_authorized"] is False
    assert result["external_validation_claim_authorized"] is False
    assert result["domain_requirements"]["target_contract"]["name"] == "energy_above_hull"
    assert result["domain_requirements"]["target_contract"]["unit"] == "eV/atom"
    assert result["source_binding"]["materials_project_database_version"] == "2026.04.13"
    assert result["source_binding"]["original_benchmark_rows"] == 838
    assert result["source_binding"]["current_identity_rows"] == 838
    assert result["source_binding"]["new_same_source_material_ids"] == 0
    assert result["source_binding"]["readiness_sha256"] == hashlib.sha256(
        readiness.read_bytes()
    ).hexdigest()
    assert (output / "external_evidence_requirement.json").is_file()


def test_new_same_source_ids_block_source_disjoint_exhaustion_claim(tmp_path: Path) -> None:
    payload = _readiness()
    overlap = payload["overlap"]
    assert isinstance(overlap, dict)
    overlap["new_material_ids_after_original_exclusion"] = 2
    payload["source_outcome"] = "new_same_source_identity_cohort_available"

    with pytest.raises(
        MaterialsProjectExternalEvidenceRequirementError,
        match="only valid after no new same-source cohort",
    ):
        build_materials_project_external_evidence_requirement(
            readiness_path=_write_readiness(tmp_path, payload),
            config_path=CONFIG_PATH,
            output_dir=tmp_path / "requirement",
        )


def test_shrunken_current_inventory_is_not_misread_as_exhaustion(tmp_path: Path) -> None:
    payload = _readiness()
    current = payload["current_identity_query"]
    overlap = payload["overlap"]
    assert isinstance(current, dict)
    assert isinstance(overlap, dict)
    current["rows"] = 837
    current["unique_material_ids"] = 837
    overlap["original_ids_still_present"] = 837
    overlap["original_ids_absent_from_current_query"] = 1

    with pytest.raises(
        MaterialsProjectExternalEvidenceRequirementError,
        match="scope differs from the historical benchmark universe",
    ):
        build_materials_project_external_evidence_requirement(
            readiness_path=_write_readiness(tmp_path, payload),
            config_path=CONFIG_PATH,
            output_dir=tmp_path / "requirement",
        )


def test_readiness_target_query_blocks_requirement_generation(tmp_path: Path) -> None:
    payload = _readiness()
    current = payload["current_identity_query"]
    assert isinstance(current, dict)
    current["target_property_queried"] = True

    with pytest.raises(
        MaterialsProjectExternalEvidenceRequirementError,
        match="target_property_queried",
    ):
        build_materials_project_external_evidence_requirement(
            readiness_path=_write_readiness(tmp_path, payload),
            config_path=CONFIG_PATH,
            output_dir=tmp_path / "requirement",
        )


def test_external_validation_ready_claim_is_rejected(tmp_path: Path) -> None:
    payload = _readiness()
    independence = payload["cohort_independence"]
    assert isinstance(independence, dict)
    independence["external_validation_ready"] = True

    with pytest.raises(
        MaterialsProjectExternalEvidenceRequirementError,
        match="external-validation readiness",
    ):
        build_materials_project_external_evidence_requirement(
            readiness_path=_write_readiness(tmp_path, payload),
            config_path=CONFIG_PATH,
            output_dir=tmp_path / "requirement",
        )
