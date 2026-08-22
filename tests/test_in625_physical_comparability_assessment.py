from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.in625_physical_comparability_assessment import (
    In625PhysicalComparabilityAssessmentError,
    build_in625_physical_comparability_assessment,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID = "zenodo-20503603-in625-lpbf-publication-supplement"

_TRACKED_FILES = (
    "configs/research/nist_ambench_2018_02_planning_readiness.v1.json",
    "data/case_studies/nist_ambench_2018_02/source_process_conditions.csv",
    "data/case_studies/nist_ambench_2018_02/source_melt_pool_measurements.csv",
    "data/case_studies/nist_ambench_2018_02/README.md",
    "configs/research/in625_tensile_reviewed_intake.v1.json",
    "configs/research/in625_zenodo_20503603_verified_source.v1.json",
    "configs/research/in625_tensile_observed_quality.v1.json",
    "configs/research/in625_external_physical_source_frontier.v1.json",
)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _quality() -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "1.0",
        "quality_status": "verified_observed_source_quality",
        "source_id": SOURCE_ID,
        "measurement_row_count": 200289,
        "complete_numeric_measurement_row_count": 200288,
        "incomplete_numeric_measurement_row_count": 1,
        "known_incomplete_rows": [
            {
                "sheet_name": "AM-AB-H",
                "block_index": 1,
                "excel_row_number": 79,
                "missing_reviewed_numeric_fields": ["load_n"],
                "non_numeric_reviewed_fields": [],
                "raw_anomalous_cell_text": {"load_n": ""},
            }
        ],
        "missing_value_imputation_authorized": False,
        "row_exclusion_authorized": False,
        "direct_nist_condition_comparability_established": False,
        "empirical_model_validation_established": False,
        "hypothesis_truth_established": False,
        "positive_scientific_closeout_established": False,
        "scientific_status_changed": False,
    }
    value["verification_sha256"] = _canonical_sha(value)
    return value


def _rediagnosis() -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "2.0",
        "policy_version": "2.0",
        "current_blocker": {
            "code": "cross_source_physical_comparability_not_established",
        },
        "next_action": {
            "action_class": "reviewed_physical_comparability_assessment",
            "source_quality_constraint": {
                "affected_field": "load_n",
                "affected_row_count": 1,
                "missing_value_imputation_authorized": False,
                "inverse_reconstruction_authorized": False,
                "row_exclusion_authorized": False,
            },
        },
        "scientific_status_changed": False,
    }
    value["rediagnosis_sha256"] = _canonical_sha(value)
    return value


def _copy_repo_evidence(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in _TRACKED_FILES:
        source = REPO_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def test_reviewed_gate_blocks_invalid_direct_tensile_to_geometry_validation() -> None:
    result = build_in625_physical_comparability_assessment(
        repository_root=REPO_ROOT,
        post_acquisition_rediagnosis=_rediagnosis(),
        observed_quality_verification=_quality(),
    )

    statuses = {item["axis"]: item["status"] for item in result["comparability_matrix"]}
    assert statuses["material_identity"] == "comparable"
    assert statuses["specimen_and_material_state"] == "non_comparable"
    assert statuses["response_semantics"] == "non_comparable"
    assert statuses["measurement_protocol_metrology"] == "non_comparable"
    assert statuses["replicate_independence"] == "unknown"

    decision = result["gate_decision"]
    assert decision["material_identity_established"] is True
    assert decision["response_compatibility_established"] is False
    assert decision["direct_nist_condition_comparability_established"] is False
    assert decision["numerical_cross_source_validation_authorized"] is False
    assert decision["scalar_residual_comparison_authorized"] is False
    assert decision["source_globally_unusable_claimed"] is False
    assert decision["source_remains_usable_for_mechanical_property_questions"] is True

    next_action = result["next_action"]
    assert next_action["action_class"] == "nist_mds2_2923_geometry_evidence_acquisition"
    assert next_action["candidate_id"] == "nist-mds2-2923-cross-sectional-micrographs"
    assert next_action["identifier"] == "10.18434/mds2-2923"
    assert next_action["network_access_performed"] is False
    assert next_action["direct_comparability_preestablished"] is False

    constraint = result["source_quality_constraint"]
    assert constraint["known_incomplete_row_count"] == 1
    assert constraint["missing_value_imputation_authorized"] is False
    assert constraint["row_exclusion_authorized"] is False
    assert result["scientific_boundary"]["numerical_cross_source_comparison_performed"] is False
    assert result["scientific_boundary"]["scientific_status_changed"] is False


def test_gate_checksum_binds_all_tracked_evidence_files() -> None:
    result = build_in625_physical_comparability_assessment(
        repository_root=REPO_ROOT,
        post_acquisition_rediagnosis=_rediagnosis(),
        observed_quality_verification=_quality(),
    )
    bindings = result["evidence_bindings"]
    assert len(bindings) == 8
    for binding in bindings.values():
        path = REPO_ROOT / binding["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == binding["sha256"]
        assert path.stat().st_size == binding["bytes"]


def test_target_material_substitution_fails_closed(tmp_path: Path) -> None:
    root = _copy_repo_evidence(tmp_path)
    path = root / "data/case_studies/nist_ambench_2018_02/source_process_conditions.csv"
    path.write_text(path.read_text(encoding="utf-8").replace(",IN625", ",IN718", 1), encoding="utf-8")
    with pytest.raises(In625PhysicalComparabilityAssessmentError, match="NIST row identity drifted"):
        build_in625_physical_comparability_assessment(
            repository_root=root,
            post_acquisition_rediagnosis=_rediagnosis(),
            observed_quality_verification=_quality(),
        )


def test_target_protocol_substitution_fails_closed(tmp_path: Path) -> None:
    root = _copy_repo_evidence(tmp_path)
    path = root / "data/case_studies/nist_ambench_2018_02/README.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "Geometry: individual laser scan tracks on a bare substrate without powder.",
            "Geometry: unspecified.",
        ),
        encoding="utf-8",
    )
    with pytest.raises(In625PhysicalComparabilityAssessmentError, match="experimental-context evidence drifted"):
        build_in625_physical_comparability_assessment(
            repository_root=root,
            post_acquisition_rediagnosis=_rediagnosis(),
            observed_quality_verification=_quality(),
        )


def test_external_response_substitution_fails_closed(tmp_path: Path) -> None:
    root = _copy_repo_evidence(tmp_path)
    path = root / "configs/research/in625_tensile_reviewed_intake.v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["measurement_header"].append("melt_pool_width_um")
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(In625PhysicalComparabilityAssessmentError, match="unexpectedly contains melt-pool response"):
        build_in625_physical_comparability_assessment(
            repository_root=root,
            post_acquisition_rediagnosis=_rediagnosis(),
            observed_quality_verification=_quality(),
        )


def test_rehashed_false_comparability_promotion_fails_closed() -> None:
    quality = _quality()
    quality.pop("verification_sha256")
    quality["direct_nist_condition_comparability_established"] = True
    quality["verification_sha256"] = _canonical_sha(quality)
    with pytest.raises(In625PhysicalComparabilityAssessmentError, match="over-claimed comparability"):
        build_in625_physical_comparability_assessment(
            repository_root=REPO_ROOT,
            post_acquisition_rediagnosis=_rediagnosis(),
            observed_quality_verification=quality,
        )


def test_frontier_candidate_identifier_substitution_fails_closed(tmp_path: Path) -> None:
    root = _copy_repo_evidence(tmp_path)
    path = root / "configs/research/in625_external_physical_source_frontier.v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidate = next(
        item
        for item in payload["candidates"]
        if item["candidate_id"] == "nist-mds2-2923-cross-sectional-micrographs"
    )
    candidate["identifier"] = "10.0000/substituted"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(In625PhysicalComparabilityAssessmentError, match="identifier drifted"):
        build_in625_physical_comparability_assessment(
            repository_root=root,
            post_acquisition_rediagnosis=_rediagnosis(),
            observed_quality_verification=_quality(),
        )
