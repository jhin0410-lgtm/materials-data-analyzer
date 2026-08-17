from __future__ import annotations

import json
from pathlib import Path

FRONTIER = Path("configs/research/in625_external_physical_source_frontier.v1.json")


def test_mds2_2923_is_machine_actionable_but_not_scientifically_promoted() -> None:
    frontier = json.loads(FRONTIER.read_text(encoding="utf-8"))
    candidate = next(
        item
        for item in frontier["candidates"]
        if item["candidate_id"] == "nist-mds2-2923-cross-sectional-micrographs"
    )

    assert candidate["identifier"] == "10.18434/mds2-2923"
    assert candidate["issue_76_eligible"] is False
    assert candidate["automatic_acquisition_plan"] == {
        "adapter": "nist_pdr",
        "product_id": "mds2-2923",
        "filepaths": [
            "2923_README.txt",
            "Master_TrackList_Measurements.xlsx",
        ],
        "approval_mode": "automatic_when_public_checksum_bound_policy_passes",
        "human_review_is_exception_only": True,
    }
    assert candidate["acquisition_status"] == (
        "authoritative_public_machine_downloadable_path_implemented_"
        "live_bytes_not_yet_authenticated_in_this_environment"
    )
    assert any(
        "do not relabel programmed power" in requirement.lower()
        for requirement in candidate["promotion_requirements"]
    )
