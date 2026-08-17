from __future__ import annotations

import copy
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.in625_external_physical_evidence import (
    PhysicalEvidenceRegistryError,
    candidate_stage1_support,
    classify_candidate,
    experiment_family_overlaps,
    load_registry,
    registry_audit,
    validate_registry,
)

REGISTRY = Path("configs/research/in625_single_track_external_source_candidates.v1.json")


def test_repository_registry_is_valid_and_does_not_complete_issue_76() -> None:
    registry = load_registry(REGISTRY)
    audit = registry_audit(registry)

    assert audit["candidate_count"] >= 5
    assert audit["issue_76_stage1"]["complete"] is False
    assert all(
        cell["eligible_independent_traces"] == 0
        for cell in audit["issue_76_stage1"]["cells"]
    )
    assert audit["scientific_boundary"]["issue_76_acceptance_contract_is_isolated"]


def test_frozen_ambench_source_is_exact_benchmark_but_has_no_missing_cells() -> None:
    registry = load_registry(REGISTRY)
    candidate = next(
        item
        for item in registry["candidates"]
        if item["candidate_id"] == "nist-amb2018-02-mds2-3830"
    )

    assert classify_candidate(candidate) == "exact_benchmark_compatible"
    report = candidate_stage1_support(candidate)
    assert report["eligible_for_issue_76"] is True
    assert report["candidate_completes_stage1"] is False
    assert all(cell["eligible_independent_traces"] == 0 for cell in report["cells"])


def test_mds2_2923_is_not_promoted_to_exact_benchmark() -> None:
    registry = load_registry(REGISTRY)
    candidate = next(
        item
        for item in registry["candidates"]
        if item["candidate_id"] == "nist-mds2-2923-single-track-cross-sections"
    )

    assert classify_candidate(candidate) == "machine_stratified_physical"
    report = candidate_stage1_support(candidate)
    assert report["eligible_for_issue_76"] is False
    assert report["candidate_completes_stage1"] is False


def test_publication_view_of_mds2_2923_is_lower_provenance_and_same_family() -> None:
    registry = load_registry(REGISTRY)
    publication = next(
        item
        for item in registry["candidates"]
        if item["candidate_id"] == "weaver-heigel-lane-2021-spot-size"
    )
    assert classify_candidate(publication) == "publication_derived_physical"

    overlaps = experiment_family_overlaps(registry)
    overlap = next(
        item
        for item in overlaps
        if item["experiment_family_id"] == "nist-mds2-2923-in625"
    )
    assert set(overlap["candidate_ids"]) == {
        "nist-mds2-2923-single-track-cross-sections",
        "weaver-heigel-lane-2021-spot-size",
    }


def test_publication_numeric_match_cannot_become_issue_76_evidence() -> None:
    registry = load_registry(REGISTRY)
    source = next(
        item
        for item in registry["candidates"]
        if item["candidate_id"] == "shrestha-chou-2021-eos-m270-single-track"
    )
    candidate = copy.deepcopy(source)
    candidate["process_points"] = [
        {
            "laser_power_w": 137.9,
            "scan_speed_mm_s": 800.0,
            "independent_track_count": 99,
        }
    ]

    assert classify_candidate(candidate) == "publication_derived_physical"
    report = candidate_stage1_support(candidate)
    assert report["eligible_for_issue_76"] is False
    assert report["cells"][0]["eligible_independent_traces"] == 0


def test_registry_rejects_changed_frozen_stage1_contract() -> None:
    registry = load_registry(REGISTRY)
    changed = copy.deepcopy(registry)
    changed["nist_stage1_target_cells"][0]["actual_laser_power_w"] = 138.0

    with pytest.raises(PhysicalEvidenceRegistryError, match="frozen #76"):
        validate_registry(changed)


def test_registry_rejects_duplicate_candidate_ids() -> None:
    registry = load_registry(REGISTRY)
    changed = copy.deepcopy(registry)
    changed["candidates"].append(copy.deepcopy(changed["candidates"][0]))

    with pytest.raises(PhysicalEvidenceRegistryError, match="candidate_id"):
        validate_registry(changed)
