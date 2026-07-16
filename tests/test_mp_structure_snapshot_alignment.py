import pandas as pd

from src.platform_core.materials_project_structure_enrichment import (
    compact_snapshot_alignment_summary,
    snapshot_alignment_rows,
)


def test_snapshot_alignment_marks_exact_tolerance_drift_and_missing():
    existing = pd.DataFrame(
        [
            {"material_id": "mp-1", "energy_above_hull": 0.1},
            {"material_id": "mp-2", "energy_above_hull": 0.2},
            {"material_id": "mp-3", "energy_above_hull": 0.0},
            {"material_id": "mp-4", "energy_above_hull": 0.3},
        ]
    )
    docs = [
        {"material_id": "mp-1", "energy_above_hull": 0.1},
        {"material_id": "mp-2", "energy_above_hull": 0.200000001},
        {"material_id": "mp-3", "energy_above_hull": 0.5},
    ]

    rows = snapshot_alignment_rows(existing, docs)
    status_by_id = {row["material_id"]: row["comparison_status"] for row in rows}

    assert status_by_id["mp-1"] == "target_exact_match"
    assert status_by_id["mp-2"] == "target_within_numeric_tolerance"
    assert status_by_id["mp-3"] == "target_drift"
    assert status_by_id["mp-4"] == "material_id_missing"
    summary = compact_snapshot_alignment_summary(rows)
    assert all(row["original_target_overwritten"] is False for row in summary)
