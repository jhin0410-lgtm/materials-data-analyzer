from __future__ import annotations

import json
from pathlib import Path

from materials_data_analyzer.research_loop.in625_external_physical_evidence import (
    load_registry,
)
from materials_data_analyzer.research_loop.in625_external_physical_evidence_intake import (
    validate_physical_evidence_records,
)

REGISTRY = Path("configs/research/in625_single_track_external_source_candidates.v1.json")
RECORDS = Path(
    "data/reference/in625_external_physical_evidence/"
    "ghosh_2018_figure1_records.v1.json"
)


def test_ghosh_2018_publication_records_are_real_but_never_issue_76_evidence() -> None:
    registry = load_registry(REGISTRY)
    record_set = json.loads(RECORDS.read_text(encoding="utf-8"))
    records = record_set["records"]

    validated, audit = validate_physical_evidence_records(records, registry, Path("."))

    assert len(validated) == 14
    assert {record["evidence_stratum"] for record in validated} == {
        "publication_derived_physical"
    }
    assert len({record["replication_unit_id"] for record in validated}) == 7
    assert audit["independent_experiment_family_count"] == 1
    assert audit["duplicate_physical_response_views"] == []
    assert audit["issue_76_stage1"]["complete"] is False
    assert all(
        cell["eligible_independent_traces"] == 0
        for cell in audit["issue_76_stage1"]["cells"]
    )


def test_ghosh_2018_transcription_retains_figure_one_case_values() -> None:
    record_set = json.loads(RECORDS.read_text(encoding="utf-8"))
    lookup = {
        (record["source_case"], record["response_name"]): record["response_value"]
        for record in record_set["records"]
    }

    assert lookup[(1, "melt_pool_width")] == 111.0
    assert lookup[(1, "melt_pool_depth")] == 24.0
    assert lookup[(5, "melt_pool_width")] == 259.0
    assert lookup[(5, "melt_pool_depth")] == 109.0
    assert lookup[(7, "melt_pool_width")] == 133.0
    assert lookup[(7, "melt_pool_depth")] == 38.0
