from __future__ import annotations

import csv
import json
from pathlib import Path


PROCESSED = Path("data/processed")
V2_2_4_OUTPUTS = [
    PROCESSED / "materials_project_v2_2_4_structure_enrichment_summary.json",
    PROCESSED / "materials_project_v2_2_4_snapshot_alignment_summary.csv",
    PROCESSED / "materials_project_v2_2_4_structure_coverage_summary.csv",
    PROCESSED / "materials_project_v2_2_4_descriptor_definition_snapshot.csv",
    PROCESSED / "materials_project_v2_2_4_descriptor_coverage_summary.csv",
    PROCESSED / "materials_project_v2_2_4_graph_eligibility_summary.csv",
    PROCESSED / "materials_project_v2_2_4_operator_snapshot.json",
]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_v2_2_4_compact_outputs_parse_and_preserve_boundaries() -> None:
    for path in V2_2_4_OUTPUTS:
        assert path.exists(), path
        if path.suffix == ".json":
            payload = json.loads(_read_text(path))
            assert payload["schema_version"] == "2.2.4"
        else:
            rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
            assert rows, path
            assert None not in rows[0]

    summary = json.loads(_read_text(PROCESSED / "materials_project_v2_2_4_structure_enrichment_summary.json"))
    assert summary["requested_material_id_count"] == 838
    assert summary["api_returned_document_count"] == 838
    assert summary["snapshot_aligned_count"] == 838
    assert summary["target_drift_count"] == 0
    assert summary["original_target_overwritten"] is False
    assert summary["structure_aware_model_trained"] is False
    assert summary["predictive_improvement_claimed"] is False
    assert summary["gnn_execution"] is False
    assert summary["decision_status"] == "structure_prediction_ready_with_restrictions"


def test_v2_2_4_tracked_outputs_do_not_contain_row_level_structures_or_secrets() -> None:
    forbidden_snippets = [
        "mp-aaaa",
        '"fractional_coordinates":',
        '"sites": [',
        "MP_API_KEY=",
        "KAGGLE_KEY",
        "C:/",
        "C:\\",
        "/Users/",
    ]
    for path in V2_2_4_OUTPUTS:
        text = _read_text(path)
        for snippet in forbidden_snippets:
            assert snippet not in text, f"{snippet!r} leaked into {path}"

    for csv_path in [path for path in V2_2_4_OUTPUTS if path.suffix == ".csv"]:
        with csv_path.open(encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle))
        assert "material_id" not in header
        assert "original_target" not in header
        assert "current_target" not in header
