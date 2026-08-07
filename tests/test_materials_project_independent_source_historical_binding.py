from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ACQUISITION_MANIFEST = (
    REPO_ROOT / "data/processed/materials_project_v1_3_acquisition_manifest.json"
)
BENCHMARK_CONFIG = (
    REPO_ROOT / "configs/research/materials_project_retrospective_benchmark.v1.json"
)
READINESS_CONFIG = (
    REPO_ROOT / "configs/research/materials_project_independent_source_readiness.v1.json"
)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_historical_canonical_acquisition_is_the_full_838_row_benchmark_universe():
    acquisition = _load(ACQUISITION_MANIFEST)
    benchmark = _load(BENCHMARK_CONFIG)
    readiness = _load(READINESS_CONFIG)

    assert acquisition["execution_status"] == "success"
    assert acquisition["partial_download"] is False
    assert acquisition["raw_row_count"] == 838
    assert acquisition["table_row_count"] == 838
    assert acquisition["unique_material_id_count"] == 838
    assert acquisition["duplicate_material_id_count"] == 0
    assert acquisition["missing_material_id_count"] == 0
    assert benchmark["expected_source"]["row_count"] == 838

    query = acquisition["exact_query_parameters"]
    assert query["elements"] == ["Fe", "Si"]
    assert query["num_elements"] == [2, 5]
    assert query["deprecated"] is False
    assert query["include_gnome"] is False
    assert "energy_above_hull" not in {
        key for key in query if key != "fields"
    }
    assert "is_stable" not in {
        key for key in query if key != "fields"
    }

    rules = readiness["decision_rules"]
    assert rules["historical_canonical_acquisition_must_equal_benchmark_universe"] is True
    assert rules["same_source_id_disjointness_must_not_be_called_source_independence"] is True
    assert rules["same_source_cohort_must_not_be_called_external_validation"] is True
