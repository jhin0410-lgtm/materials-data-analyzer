from __future__ import annotations

import copy
from pathlib import Path

from materials_data_analyzer.research_loop.in625_external_physical_evidence import (
    NIST_STAGE1_TARGETS,
    candidate_stage1_support,
    load_registry,
    registry_audit,
)

REGISTRY = Path("configs/research/in625_single_track_external_source_candidates.v1.json")


def _metadata_complete_exact_candidate() -> tuple[dict[str, object], dict[str, object]]:
    registry = load_registry(REGISTRY)
    candidate = copy.deepcopy(
        next(
            item
            for item in registry["candidates"]
            if item["candidate_id"] == "nist-amb2018-02-mds2-3830"
        )
    )
    candidate["process_points"] = [
        {
            "laser_power_w": power,
            "scan_speed_mm_s": speed,
            "independent_track_count": required,
        }
        for (power, speed), required in NIST_STAGE1_TARGETS.items()
    ]
    registry["candidates"] = [candidate]
    return registry, candidate


def test_exact_candidate_metadata_can_signal_discovery_support_but_not_completion() -> None:
    _, candidate = _metadata_complete_exact_candidate()
    report = candidate_stage1_support(candidate)

    assert report["eligible_for_issue_76"] is True
    assert report["candidate_metadata_completes_stage1"] is True
    assert report["candidate_completes_stage1"] is False
    assert report["scientific_stage1_complete"] is False
    assert all(cell["candidate_metadata_complete"] for cell in report["cells"])
    assert all(cell["eligible_independent_traces"] == 0 for cell in report["cells"])
    assert all(cell["complete"] is False for cell in report["cells"])


def test_registry_audit_never_has_scientific_completion_authority() -> None:
    registry, _ = _metadata_complete_exact_candidate()
    audit = registry_audit(registry)
    stage1 = audit["issue_76_stage1"]

    assert stage1["candidate_metadata_support_complete"] is True
    assert stage1["complete"] is False
    assert stage1["scientific_stage1_complete"] is False
    assert stage1["scientific_completion_authority"] == (
        "source_bound_record_intake_only"
    )
    assert all(cell["eligible_independent_traces"] == 0 for cell in stage1["cells"])
    assert audit["scientific_boundary"]["registry_metadata_can_complete_issue_76"] is False
