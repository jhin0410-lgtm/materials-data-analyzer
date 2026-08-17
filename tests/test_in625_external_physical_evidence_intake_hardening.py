from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.in625_external_physical_evidence_intake import (
    PhysicalEvidenceIntakeError,
    validate_physical_evidence_records,
)


def _registry() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "registry_id": "in625-single-track-external-physical-sources-v1",
        "scientific_scope": "hardening fixture",
        "target_material": "IN625",
        "nist_stage1_target_cells": [
            {
                "actual_laser_power_w": 137.9,
                "scan_speed_mm_s": 800.0,
                "minimum_independent_traces": 3,
            },
            {
                "actual_laser_power_w": 137.9,
                "scan_speed_mm_s": 1200.0,
                "minimum_independent_traces": 3,
            },
            {
                "actual_laser_power_w": 179.2,
                "scan_speed_mm_s": 400.0,
                "minimum_independent_traces": 3,
            },
        ],
        "candidates": [
            {
                "candidate_id": "fixture-source",
                "title": "fixture",
                "authority": "pytest",
                "source_reference": "fixture://source",
                "access_date": "2026-08-17",
                "acquisition_status": "fixture",
                "extraction_mode": "raw_dataset",
                "physical_origin": "physical",
                "experiment_family_id": "fixture-family",
                "machine_id": "nist-ammt",
                "material_state": "bare_plate",
                "power_semantics": "achieved_calibrated_actual",
                "calibration_binding": "authoritative_for_this_experiment",
                "spot_size_semantics": "fixture",
                "characterization": "optical",
                "replication_semantics": "independent_tracks",
                "process_points": [
                    {
                        "laser_power_w": 137.9,
                        "scan_speed_mm_s": 800.0,
                        "independent_track_count": 3,
                    }
                ],
                "comparability_class": "exact_benchmark",
                "provenance_checks": {
                    "source_identity": "confirmed",
                    "machine": "confirmed",
                    "material": "confirmed",
                    "power": "confirmed",
                    "speed": "confirmed",
                    "calibration": "confirmed",
                },
                "notes": ["fixture"],
            }
        ],
    }


def _artifact(root: Path) -> dict[str, object]:
    payload = b"one immutable source artifact"
    (root / "source.bin").write_bytes(payload)
    return {
        "path": "source.bin",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }


def _record(
    binding: dict[str, object],
    *,
    record_id: str,
    replicate: str,
    response_value: float = 100.0,
) -> dict[str, object]:
    return {
        "record_id": record_id,
        "candidate_id": "fixture-source",
        "experiment_family_id": "fixture-family",
        "replication_unit_id": replicate,
        "source_locator": f"fixture:{replicate}",
        "machine_id": "nist-ammt",
        "material": "IN625",
        "material_state": "bare_plate",
        "power_semantics": "achieved_calibrated_actual",
        "calibration_binding": "authoritative_for_this_experiment",
        "laser_power_w": 137.9,
        "scan_speed_mm_s": 800.0,
        "response_name": "melt_pool_width",
        "response_value": response_value,
        "response_unit": "um",
        "independent_physical_replicate": True,
        "source_artifact": copy.deepcopy(binding),
    }


def test_length_response_must_be_strictly_positive(tmp_path: Path) -> None:
    binding = _artifact(tmp_path)
    for invalid in (0.0, -1.0):
        with pytest.raises(PhysicalEvidenceIntakeError, match="finite and positive"):
            validate_physical_evidence_records(
                [_record(binding, record_id=f"bad-{invalid}", replicate="track", response_value=invalid)],
                _registry(),
                tmp_path,
            )


def test_same_raw_artifact_is_reported_once_for_many_records(tmp_path: Path) -> None:
    binding = _artifact(tmp_path)
    records = [
        _record(binding, record_id=f"record-{index}", replicate=f"track-{index}")
        for index in range(3)
    ]
    _, audit = validate_physical_evidence_records(records, _registry(), tmp_path)

    assert audit["record_count"] == 3
    assert len(audit["verified_source_artifacts"]) == 1
    assert audit["verified_source_artifacts"][0]["path"] == "source.bin"
    assert audit["scientific_boundary"]["raw_artifact_bytes_are_read_once_per_unique_path"] is True
