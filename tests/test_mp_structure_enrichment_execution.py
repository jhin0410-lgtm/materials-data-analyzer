import json
from pathlib import Path

import pandas as pd
import pytest

from src.platform_core.materials_project_structure_enrichment import (
    plan_existing_id_structure_enrichment,
    preview_structure_enrichment,
    run_structure_enrichment,
)


class _FakeSummary:
    def __init__(self, calls):
        self.calls = calls

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return [
            {
                "material_id": material_id,
                "formula_pretty": "FeSi",
                "composition_reduced": {"Fe": 1, "Si": 1},
                "energy_above_hull": 0.1,
                "density": 5.2,
                "volume": 22.0,
                "symmetry": {"number": 221, "crystal_system": "cubic"},
                "structure": {
                    "lattice": {"matrix": [[2.8, 0, 0], [0, 2.8, 0], [0, 0, 2.8]]},
                    "sites": [
                        {"species": [{"element": "Fe", "occu": 1}], "abc": [0, 0, 0]},
                        {"species": [{"element": "Si", "occu": 1}], "abc": [0.5, 0.5, 0.5]},
                    ],
                },
            }
            for material_id in kwargs["material_ids"]
        ]


class _FakeClient:
    def __init__(self, calls):
        self.materials = type("Materials", (), {"summary": _FakeSummary(calls)})()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


def _root(tmp_path: Path) -> Path:
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    pd.DataFrame(
        [
            {"material_id": "mp-1", "formula_pretty": "FeSi", "composition_reduced": '{"Fe":1,"Si":1}', "energy_above_hull": 0.1},
            {"material_id": "mp-2", "formula_pretty": "FeSi", "composition_reduced": '{"Fe":1,"Si":1}', "energy_above_hull": 0.2},
        ]
    ).to_csv(processed / "materials_project_v1_3_acquired.csv", index=False)
    return tmp_path


def test_existing_id_plan_rejects_unknown_and_unbounded_ids(tmp_path):
    root = _root(tmp_path)
    config = {"mode": "enrich_existing_ids", "material_ids": ["mp-1"], "max_records": 2}

    plan = plan_existing_id_structure_enrichment(config, root=root)

    assert plan.material_ids == ("mp-1",)
    assert plan.to_dict()["broad_query_allowed"] is False
    with pytest.raises(ValueError, match="outside the existing"):
        plan_existing_id_structure_enrichment({"material_ids": ["mp-new"], "max_records": 2}, root=root)
    with pytest.raises(ValueError, match="max_records"):
        plan_existing_id_structure_enrichment({"max_records": 3}, root=root)


def test_preview_works_without_local_id_table_from_tracked_summary(tmp_path):
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    (processed / "materials_project_v2_2_acquisition_scope_summary.json").write_text(
        json.dumps({"unique_material_id_count": 838}),
        encoding="utf-8",
    )

    preview = preview_structure_enrichment({"max_records": 838}, root=tmp_path)

    assert preview["status"] == "preview_only_no_network_missing_local_id_table"
    assert preview["network_called"] is False
    assert preview["query_plan"]["material_id_count"] == 838


def test_execute_uses_material_ids_only_and_writes_local_chunks(tmp_path):
    root = _root(tmp_path)
    calls = []
    config = {
        "mode": "enrich_existing_ids",
        "max_records": 2,
        "chunk_size": 1,
        "output_root": "outputs/materials_project_structure_v2_2",
    }

    manifest = run_structure_enrichment(config, root=root, execute=True, client_factory=lambda: _FakeClient(calls))

    assert manifest["status"] == "success"
    assert manifest["network_called"] is True
    assert len(calls) == 2
    assert all("material_ids" in call for call in calls)
    assert all("elements" not in call and "chemsys" not in call for call in calls)
    chunk_dir = root / "outputs" / "materials_project_structure_v2_2" / "acquisition" / "chunks"
    assert len(list(chunk_dir.glob("structure_chunk_*.jsonl"))) == 2


def test_execute_rejects_unexpected_returned_material_ids(tmp_path):
    class BadSummary(_FakeSummary):
        def search(self, **kwargs):
            self.calls.append(kwargs)
            return [
                {
                    "material_id": "mp-new",
                    "formula_pretty": "FeSi",
                    "composition_reduced": {"Fe": 1, "Si": 1},
                    "energy_above_hull": 0.1,
                    "structure": {
                        "lattice": {"matrix": [[2.8, 0, 0], [0, 2.8, 0], [0, 0, 2.8]]},
                        "sites": [{"species": [{"element": "Fe", "occu": 1}], "abc": [0, 0, 0]}],
                    },
                }
            ]

    class BadClient(_FakeClient):
        def __init__(self, calls):
            self.materials = type("Materials", (), {"summary": BadSummary(calls)})()

    root = _root(tmp_path)
    calls = []
    manifest = run_structure_enrichment(
        {"mode": "enrich_existing_ids", "material_ids": ["mp-1"], "max_records": 1},
        root=root,
        execute=True,
        client_factory=lambda: BadClient(calls),
    )

    assert manifest["status"] == "failed"
    assert manifest["returned_count"] == 0
    assert any("unexpected_material_ids_returned" in error for error in manifest["errors"])


def test_execute_rejects_conflicting_existing_chunk_cache(tmp_path):
    root = _root(tmp_path)
    chunk_dir = root / "outputs" / "materials_project_structure_v2_2" / "acquisition" / "chunks"
    chunk_dir.mkdir(parents=True)
    (chunk_dir / "structure_chunk_00001.jsonl").write_text('{"material_id":"mp-2"}\n', encoding="utf-8")
    (chunk_dir / "structure_chunk_00001.manifest.json").write_text(
        json.dumps({"requested_ids_checksum": "different"}),
        encoding="utf-8",
    )

    manifest = run_structure_enrichment(
        {"mode": "enrich_existing_ids", "material_ids": ["mp-1"], "max_records": 1},
        root=root,
        execute=True,
        client_factory=lambda: _FakeClient([]),
    )

    assert manifest["status"] == "failed"
    assert manifest["returned_count"] == 0
    assert any("existing_chunk_query_mismatch" in error for error in manifest["errors"])
