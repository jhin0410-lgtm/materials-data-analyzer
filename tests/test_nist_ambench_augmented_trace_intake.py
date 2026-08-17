from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from materials_data_analyzer.research_loop.nist_ambench_augmented_trace_intake import (
    CONTRACT_ID,
    IntakeValidationError,
    REQUIRED_STATUS_KEYS,
    TARGET_CELLS,
    TARGET_CELL_IDS,
    combine_with_frozen_baseline,
    structural_audit_input,
    validate_augmented_manifest,
)
from scripts.audit_nist_ambench_2018_02_process_design import audit_process_design


def _status(**updates: bool) -> dict[str, bool]:
    value = {key: False for key in REQUIRED_STATUS_KEYS}
    value.update(updates)
    return value


def _binding(root: Path, name: str, payload: bytes) -> dict[str, object]:
    path = root / name
    path.write_bytes(payload)
    return {
        "path": name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }


def _manifest(
    root: Path,
    *,
    evidence_kind: str = "synthetic_fixture",
) -> dict[str, object]:
    process_artifact = _binding(root, "process-source.bin", b"process-source")
    char_artifact = _binding(root, "characterization-source.bin", b"char-source")
    process_records: list[dict[str, object]] = []
    characterization_records: list[dict[str, object]] = []
    index = 0
    for power, speed in TARGET_CELLS:
        condition_id = TARGET_CELL_IDS[(power, speed)]
        for replicate in range(3):
            index += 1
            sample_id = f"stage1-sample-{index:02d}"
            trace_id = f"stage1-trace-{index:02d}"
            process_records.append(
                {
                    "sample_id": sample_id,
                    "trace_id": trace_id,
                    "condition_id": condition_id,
                    "build_id": "build-01",
                    "run_id": "run-01",
                    "block_id": f"block-{replicate + 1}",
                    "target_laser_power_w": power,
                    "achieved_laser_power_w": power,
                    "power_unit": "W",
                    "scan_speed_mm_s": speed,
                    "speed_unit": "mm/s",
                    "controlled_process_settings_id": "process-settings-v1",
                    "machine_id": "nist-ammt",
                    "optics_config_id": "optics-v1",
                    "calibration_id": "calibration-v1",
                    "calibration_reference": "authority:calibration-v1",
                    "software_config_id": "control-software-v1",
                    "material": "IN625",
                    "material_lot_id": "lot-01",
                    "geometry_id": "geometry-01",
                    "preparation_history_id": "prep-01",
                    "spatial_location": f"trace-location-{index:02d}",
                    "evidence_kind": evidence_kind,
                    "source_kind": "test_fixture",
                    "source_authority": "pytest",
                    "source_record_id": f"process-{index:02d}",
                    "source_reference": "fixture://process",
                    "raw_artifact": copy.deepcopy(process_artifact),
                    "status": _status(),
                }
            )
            characterization_records.append(
                {
                    "sample_id": sample_id,
                    "trace_id": trace_id,
                    "method": "optical_microscopy_metrology",
                    "acquisition_settings_id": "acquisition-v1",
                    "preprocessing_id": "none",
                    "exclusion_policy_id": "retain-all-v1",
                    "measurement_schema_id": "melt-pool-width-v1",
                    "measurements": [
                        {
                            "name": "melt_pool_width_mean",
                            "value": 100.0 + index,
                            "unit": "um",
                        },
                        {
                            "name": "melt_pool_depth_mean",
                            "value": 30.0 + index,
                            "unit": "um",
                        },
                    ],
                    "evidence_kind": evidence_kind,
                    "source_kind": "test_fixture",
                    "source_authority": "pytest",
                    "source_record_id": f"char-{index:02d}",
                    "source_reference": "fixture://characterization",
                    "raw_artifact": copy.deepcopy(char_artifact),
                    "status": _status(),
                }
            )
    return {
        "schema_version": "1.0",
        "contract_id": CONTRACT_ID,
        "process_records": process_records,
        "characterization_records": characterization_records,
    }


def _write_manifest(
    root: Path,
    value: dict[str, object],
    name: str = "manifest.json",
) -> Path:
    path = root / name
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    return path


def _baseline() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    index = 0
    for case_id, power, speed, count in (
        ("A", 137.9, 400.0, 3),
        ("B", 179.2, 800.0, 3),
        ("C", 179.2, 1200.0, 4),
    ):
        for _ in range(count):
            index += 1
            rows.append(
                {
                    "sample_id": f"baseline-{index:02d}",
                    "case_id": case_id,
                    "actual_laser_power_w": power,
                    "scan_speed_mm_s": speed,
                }
            )
    return pd.DataFrame(rows)


def test_valid_synthetic_fixture_reaches_19_trace_structural_audit_without_scientific_promotion(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    joined, intake = validate_augmented_manifest(
        _write_manifest(tmp_path, manifest), tmp_path
    )
    augmented = combine_with_frozen_baseline(_baseline(), joined)
    structural = structural_audit_input(augmented)
    _, audit = audit_process_design(structural)

    interaction = audit["design_models"]["main_effects_plus_interaction"]
    assert len(augmented) == 19
    assert audit["unique_condition_count"] == 6
    assert audit["factor_support"]["factorial_coverage_fraction"] == 1.0
    assert interaction["matrix_rank"] == 4
    assert interaction["sample_level_residual_df"] == 15
    assert audit["readiness"]["interaction_estimation"] == (
        "structurally_estimable_but_not_scientifically_validated"
    )
    assert intake["stage1"]["structural_trace_requirement_complete"] is True
    assert intake["stage1"]["declared_measured_candidate_requirement_complete"] is False
    assert intake["stage1"]["scientific_stage1_complete"] is False


def test_declared_measured_records_never_authenticate_physical_origin_by_self_declaration(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path, evidence_kind="measured_physical_candidate")
    _, report = validate_augmented_manifest(
        _write_manifest(tmp_path, manifest), tmp_path
    )
    assert report["stage1"]["declared_measured_candidate_requirement_complete"] is True
    assert report["stage1"]["physical_origin_authenticated_by_software"] is False
    assert report["stage1"]["scientific_stage1_complete"] is False
    assert report["scientific_boundary"][
        "self_declared_physical_metadata_is_independent_proof"
    ] is False


def test_manifest_order_does_not_change_joined_rows_or_canonical_binding(
    tmp_path: Path,
) -> None:
    first = _manifest(tmp_path)
    first_path = _write_manifest(tmp_path, first, "first.json")
    first_joined, first_report = validate_augmented_manifest(first_path, tmp_path)

    second = copy.deepcopy(first)
    second["process_records"] = list(reversed(second["process_records"]))
    second["characterization_records"] = list(
        reversed(second["characterization_records"])
    )
    for record in second["characterization_records"]:
        record["measurements"] = list(reversed(record["measurements"]))
    second_path = _write_manifest(tmp_path, second, "second.json")
    second_joined, second_report = validate_augmented_manifest(second_path, tmp_path)

    pd.testing.assert_frame_equal(first_joined, second_joined)
    assert first_report["canonical_manifest_sha256"] == second_report[
        "canonical_manifest_sha256"
    ]
    assert first_report["raw_manifest_sha256"] != second_report["raw_manifest_sha256"]


def test_duplicate_identity_fails_closed(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    manifest["process_records"][1]["sample_id"] = manifest["process_records"][0][
        "sample_id"
    ]
    with pytest.raises(IntakeValidationError, match="duplicate sample_id"):
        validate_augmented_manifest(_write_manifest(tmp_path, manifest), tmp_path)


def test_row_order_cannot_substitute_for_explicit_identity_join(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    manifest["characterization_records"][0]["trace_id"] = "wrong-trace-id"
    with pytest.raises(IntakeValidationError, match="identity sets must match exactly"):
        validate_augmented_manifest(_write_manifest(tmp_path, manifest), tmp_path)


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("sha256", "0" * 64, "checksum mismatch"),
        ("size_bytes", 999, "size mismatch"),
    ],
)
def test_artifact_binding_mismatch_fails_closed(
    tmp_path: Path,
    field: str,
    replacement: object,
    message: str,
) -> None:
    manifest = _manifest(tmp_path)
    manifest["process_records"][0]["raw_artifact"][field] = replacement
    with pytest.raises(IntakeValidationError, match=message):
        validate_augmented_manifest(_write_manifest(tmp_path, manifest), tmp_path)


def test_traversal_path_fails_closed(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    manifest["process_records"][0]["raw_artifact"]["path"] = "../escape.bin"
    with pytest.raises(IntakeValidationError, match="escapes the intake root"):
        validate_augmented_manifest(_write_manifest(tmp_path, manifest), tmp_path)


def test_target_power_without_calibration_provenance_fails_closed(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path, evidence_kind="measured_physical_candidate")
    del manifest["process_records"][0]["calibration_reference"]
    with pytest.raises(IntakeValidationError, match="calibration_reference"):
        validate_augmented_manifest(_write_manifest(tmp_path, manifest), tmp_path)


def test_changed_process_units_fail_instead_of_converting(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    manifest["process_records"][0]["power_unit"] = "kW"
    with pytest.raises(IntakeValidationError, match="power_unit"):
        validate_augmented_manifest(_write_manifest(tmp_path, manifest), tmp_path)


def test_changed_characterization_unit_fails_closed(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path, _manifest(tmp_path))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["characterization_records"][0]["measurements"][0]["unit"] = "mm"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(IntakeValidationError, match="unit must be exactly"):
        validate_augmented_manifest(manifest_path, tmp_path)


def test_unapproved_midpoint_condition_cannot_satisfy_stage1(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    manifest["process_records"][0]["target_laser_power_w"] = 158.55
    with pytest.raises(IntakeValidationError, match="not an approved Stage 1 cell"):
        validate_augmented_manifest(_write_manifest(tmp_path, manifest), tmp_path)


def test_censor_failure_state_is_preserved_and_not_structurally_counted(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    manifest["characterization_records"][0]["status"] = _status(censored=True)
    joined, report = validate_augmented_manifest(
        _write_manifest(tmp_path, manifest), tmp_path
    )
    row = joined.loc[joined["sample_id"].eq("stage1-sample-01")].iloc[0]
    assert bool(row["status__censored"]) is True
    assert bool(row["structural_audit_eligible"]) is False
    assert report["stage1"]["structural_trace_requirement_complete"] is False
    assert report["stage1"]["counts"]["stage1_p137_9_v800"][
        "structural_eligible_records"
    ] == 2


def test_fewer_than_three_records_in_one_target_cell_remains_incomplete(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    removed_process = manifest["process_records"].pop()
    removed_char = manifest["characterization_records"].pop()
    assert removed_process["sample_id"] == removed_char["sample_id"]
    _, report = validate_augmented_manifest(
        _write_manifest(tmp_path, manifest), tmp_path
    )
    assert report["stage1"]["structural_trace_requirement_complete"] is False


def test_baseline_three_condition_audit_regression_keeps_existing_gate() -> None:
    _, audit = audit_process_design(_baseline())
    assert audit["sample_count"] == 10
    assert audit["unique_condition_count"] == 3
    assert audit["readiness"]["overall"] == (
        "not_ready_for_predictive_or_causal_modeling"
    )
    assert audit["readiness"]["interaction_estimation"] == "not_identifiable"
    assert audit["blocking_reasons"][:4] == [
        "Only 3 unique process conditions are observed.",
        (
            "The main-effects design is saturated at the condition level, leaving "
            "zero lack-of-fit degrees of freedom."
        ),
        (
            "No scan speed is observed at both laser-power levels, so a direct "
            "matched-speed power contrast is unavailable."
        ),
        "The interaction and quadratic response-surface designs are rank deficient.",
    ]
