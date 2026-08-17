from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.in625_external_physical_evidence import (
    NIST_STAGE1_TARGETS,
)
from materials_data_analyzer.research_loop.in625_external_physical_evidence_intake import (
    PhysicalEvidenceIntakeError,
    validate_physical_evidence_records,
)


def _targets() -> list[dict[str, object]]:
    return [
        {
            "actual_laser_power_w": power,
            "scan_speed_mm_s": speed,
            "minimum_independent_traces": count,
        }
        for (power, speed), count in NIST_STAGE1_TARGETS.items()
    ]


def _candidate(
    *,
    candidate_id: str = "exact-source",
    family: str = "family-exact",
    machine: str = "nist-ammt",
    material_state: str = "bare_plate",
    power_semantics: str = "achieved_calibrated_actual",
    calibration: str = "authoritative_for_this_experiment",
    extraction_mode: str = "raw_dataset",
    comparability: str = "exact_benchmark",
    point: tuple[float, float] = (137.9, 800.0),
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "title": candidate_id,
        "authority": "pytest",
        "source_reference": f"fixture://{candidate_id}",
        "access_date": "2026-08-17",
        "acquisition_status": "fixture",
        "extraction_mode": extraction_mode,
        "physical_origin": "physical",
        "experiment_family_id": family,
        "machine_id": machine,
        "material_state": material_state,
        "power_semantics": power_semantics,
        "calibration_binding": calibration,
        "spot_size_semantics": "fixture-spot",
        "characterization": "optical_microscopy",
        "replication_semantics": "independent_tracks",
        "process_points": [
            {
                "laser_power_w": point[0],
                "scan_speed_mm_s": point[1],
                "independent_track_count": 3,
            }
        ],
        "comparability_class": comparability,
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


def _registry(*candidates: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "registry_id": "in625-single-track-external-physical-sources-v1",
        "scientific_scope": "pytest cross-source physical evidence",
        "target_material": "IN625",
        "nist_stage1_target_cells": _targets(),
        "candidates": list(candidates) or [_candidate()],
    }


def _artifact(root: Path, name: str = "source.bin") -> dict[str, object]:
    payload = b"authoritative fixture bytes"
    (root / name).write_bytes(payload)
    return {
        "path": name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }


def _record(
    root: Path,
    *,
    record_id: str = "record-1",
    replicate: str = "track-1",
    candidate: dict[str, object] | None = None,
    independent: bool = True,
    point: tuple[float, float] = (137.9, 800.0),
    artifact: dict[str, object] | None = None,
) -> dict[str, object]:
    source = candidate or _candidate()
    value: dict[str, object] = {
        "record_id": record_id,
        "candidate_id": source["candidate_id"],
        "experiment_family_id": source["experiment_family_id"],
        "replication_unit_id": replicate,
        "source_locator": "fixture:row:1",
        "machine_id": source["machine_id"],
        "material": "IN625",
        "material_state": source["material_state"],
        "power_semantics": source["power_semantics"],
        "calibration_binding": source["calibration_binding"],
        "laser_power_w": point[0],
        "scan_speed_mm_s": point[1],
        "response_name": "melt_pool_width",
        "response_value": 101.0,
        "response_unit": "um",
        "independent_physical_replicate": independent,
    }
    if source["extraction_mode"] == "raw_dataset":
        value["source_artifact"] = artifact or _artifact(root)
    return value


def test_three_exact_tracks_complete_only_one_stage1_cell(tmp_path: Path) -> None:
    candidate = _candidate()
    binding = _artifact(tmp_path)
    records = [
        _record(
            tmp_path,
            record_id=f"record-{index}",
            replicate=f"track-{index}",
            candidate=candidate,
            artifact=copy.deepcopy(binding),
        )
        for index in range(1, 4)
    ]

    _, audit = validate_physical_evidence_records(
        records, _registry(candidate), tmp_path
    )
    first = audit["issue_76_stage1"]["cells"][0]
    assert first["eligible_independent_traces"] == 3
    assert first["complete"] is True
    assert audit["issue_76_stage1"]["complete"] is False


def test_record_cannot_invent_process_point_not_predeclared_by_source(tmp_path: Path) -> None:
    candidate = _candidate(point=(137.9, 800.0))
    record = _record(
        tmp_path,
        candidate=candidate,
        point=(137.9, 1200.0),
    )

    with pytest.raises(PhysicalEvidenceIntakeError, match="not declared"):
        validate_physical_evidence_records([record], _registry(candidate), tmp_path)


def test_cross_machine_numeric_match_never_counts_for_issue_76(tmp_path: Path) -> None:
    candidate = _candidate(
        candidate_id="eos-source",
        family="family-eos",
        machine="eos_m270",
        power_semantics="machine_setting",
        calibration="not_amb2018_ammt",
        comparability="machine_stratified",
    )
    record = _record(tmp_path, candidate=candidate)

    validated, audit = validate_physical_evidence_records(
        [record], _registry(candidate), tmp_path
    )
    assert validated[0]["is_exact_stage1_coordinate"] is True
    assert validated[0]["eligible_for_issue_76"] is False
    assert audit["issue_76_stage1"]["cells"][0]["eligible_independent_traces"] == 0


def test_repeated_measurement_on_one_track_does_not_create_replication(tmp_path: Path) -> None:
    candidate = _candidate()
    binding = _artifact(tmp_path)
    records = [
        _record(
            tmp_path,
            record_id="measurement-a",
            replicate="track-1",
            candidate=candidate,
            artifact=copy.deepcopy(binding),
        ),
        _record(
            tmp_path,
            record_id="measurement-b",
            replicate="track-1",
            candidate=candidate,
            artifact=copy.deepcopy(binding),
        ),
    ]

    _, audit = validate_physical_evidence_records(
        records, _registry(candidate), tmp_path
    )
    assert len(audit["duplicate_physical_response_views"]) == 1
    assert audit["issue_76_stage1"]["cells"][0]["eligible_independent_traces"] == 1
    assert audit["naive_cross_source_pooling_allowed"] is False


def test_non_independent_track_never_counts_for_issue_76(tmp_path: Path) -> None:
    candidate = _candidate()
    record = _record(tmp_path, candidate=candidate, independent=False)

    validated, audit = validate_physical_evidence_records(
        [record], _registry(candidate), tmp_path
    )
    assert validated[0]["eligible_for_issue_76"] is False
    assert audit["issue_76_stage1"]["cells"][0]["eligible_independent_traces"] == 0


def test_raw_artifact_checksum_mismatch_fails_closed(tmp_path: Path) -> None:
    candidate = _candidate()
    binding = _artifact(tmp_path)
    binding["sha256"] = "0" * 64
    record = _record(tmp_path, candidate=candidate, artifact=binding)

    with pytest.raises(PhysicalEvidenceIntakeError, match="checksum mismatch"):
        validate_physical_evidence_records([record], _registry(candidate), tmp_path)


def test_raw_artifact_traversal_fails_closed(tmp_path: Path) -> None:
    candidate = _candidate()
    binding = _artifact(tmp_path)
    binding["path"] = "../source.bin"
    record = _record(tmp_path, candidate=candidate, artifact=binding)

    with pytest.raises(PhysicalEvidenceIntakeError, match="escapes"):
        validate_physical_evidence_records([record], _registry(candidate), tmp_path)


def test_record_cannot_relabel_machine_power_semantics(tmp_path: Path) -> None:
    candidate = _candidate()
    record = _record(tmp_path, candidate=candidate)
    record["power_semantics"] = "machine_setting"

    with pytest.raises(PhysicalEvidenceIntakeError, match="power_semantics"):
        validate_physical_evidence_records([record], _registry(candidate), tmp_path)


def test_publication_and_repository_views_of_same_physical_unit_are_detected(
    tmp_path: Path,
) -> None:
    raw = _candidate(candidate_id="raw", family="shared-family")
    paper = _candidate(
        candidate_id="paper",
        family="shared-family",
        extraction_mode="author_table",
    )
    paper["comparability_class"] = "exact_benchmark"
    records = [
        _record(tmp_path, record_id="raw-record", replicate="same-track", candidate=raw),
        _record(
            tmp_path,
            record_id="paper-record",
            replicate="same-track",
            candidate=paper,
        ),
    ]

    validated, audit = validate_physical_evidence_records(
        records, _registry(raw, paper), tmp_path
    )
    assert {row["evidence_stratum"] for row in validated} == {
        "exact_benchmark_compatible",
        "publication_derived_physical",
    }
    assert len(audit["duplicate_physical_response_views"]) == 1
    assert audit["issue_76_stage1"]["cells"][0]["eligible_independent_traces"] == 1
