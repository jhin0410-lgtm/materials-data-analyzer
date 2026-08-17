from __future__ import annotations

import json
from pathlib import Path

FRONTIER = Path("configs/research/in625_external_physical_source_frontier.v1.json")


def test_eos_m290_gasflow_source_preserves_reported_scan_speed_conflict() -> None:
    frontier = json.loads(FRONTIER.read_text(encoding="utf-8"))
    candidate = next(
        item
        for item in frontier["candidates"]
        if item["candidate_id"]
        == "weaver-schlenoff-deisenroth-moylan-2023-eos-m290-gasflow"
    )
    speeds = candidate["reported_scan_speed_semantics"]

    assert speeds["methods_table_1_mm_s"] == [300.0, 960.0, 1200.0]
    assert speeds["results_table_2_and_figures_mm_s"] == [300.0, 960.0, 1500.0]
    assert speeds["status"] == "internal_publication_conflict_unresolved"
    assert candidate["reported_track_measurements"] == {
        "per_scan_speed": 280,
        "total": 840,
    }
    assert candidate["issue_76_eligible"] is False


def test_eos_m290_height_is_not_silently_relabelled_as_depth() -> None:
    frontier = json.loads(FRONTIER.read_text(encoding="utf-8"))
    candidate = next(
        item
        for item in frontier["candidates"]
        if item["candidate_id"]
        == "weaver-schlenoff-deisenroth-moylan-2023-eos-m290-gasflow"
    )

    assert candidate["measurement_semantics"]["height_is_not_bare_plate_depth"] is True
    assert "melt_pool_height" in candidate["responses"]
    assert candidate["row_level_dataset_location"].startswith("not_found")
