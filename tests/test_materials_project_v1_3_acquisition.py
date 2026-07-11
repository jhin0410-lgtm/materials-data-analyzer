"""Network-free tests for Materials Project v1.3 controlled acquisition."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from connectors.materials_project_acquisition import (
    AcquisitionOutputs,
    AcquisitionStopError,
    build_acquired_table,
    build_exact_query_parameters,
    load_acquisition_spec,
    run_full_acquisition,
    run_preflight,
    validate_materials_project_documents,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACQUISITION_SPEC_PATH = (
    PROJECT_ROOT
    / "data"
    / "case_studies"
    / "materials_project"
    / "acquisition_spec_v1_3.json"
)


class FakeSummary:
    """Fake summary endpoint that records search calls."""

    def __init__(self, docs: list[dict[str, object]], calls: list[dict[str, object]]) -> None:
        self.docs = docs
        self.calls = calls

    def search(self, **kwargs: object) -> list[dict[str, object]]:
        self.calls.append(kwargs)
        return self.docs


class FakeMaterials:
    """Fake materials namespace."""

    def __init__(self, docs: list[dict[str, object]], calls: list[dict[str, object]]) -> None:
        self.summary = FakeSummary(docs, calls)


class FakeClient:
    """Fake MPRester-compatible client."""

    def __init__(self, docs: list[dict[str, object]], calls: list[dict[str, object]]) -> None:
        self.materials = FakeMaterials(docs, calls)

    def get_database_version(self) -> str:
        return "2026.07.01"

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


def _spec() -> dict[str, object]:
    return load_acquisition_spec(ACQUISITION_SPEC_PATH)


def _doc(
    material_id: str,
    *,
    formula: str = "FeSi",
    chemsys: str = "Fe-Si",
    elements: list[str] | None = None,
    nelements: int = 2,
    energy_above_hull: float | None = 0.01,
    deprecated: bool = False,
    theoretical: bool | None = False,
) -> dict[str, object]:
    if elements is None:
        elements = ["Fe", "Si"]
    return {
        "material_id": material_id,
        "formula_pretty": formula,
        "chemsys": chemsys,
        "elements": elements,
        "nelements": nelements,
        "theoretical": theoretical,
        "deprecated": deprecated,
        "energy_above_hull": energy_above_hull,
        "composition": {"Fe": 1, "Si": 1},
        "composition_reduced": {"Fe": 1, "Si": 1},
        "formation_energy_per_atom": -0.3,
        "density": 5.1,
        "volume": 42.0,
        "nsites": 2,
        "band_gap": 0.0,
        "is_metal": True,
        "symmetry": {"number": 221},
        "is_stable": False,
        "origins": [{"name": "fake"}],
        "last_updated": "2026-07-01T00:00:00Z",
        "database_IDs": {},
    }


def _factory(
    docs: list[dict[str, object]],
    calls: list[dict[str, object]],
):
    def create() -> FakeClient:
        return FakeClient(docs, calls)

    return create


def _sequence_factory(
    doc_batches: list[list[dict[str, object]]],
    calls: list[dict[str, object]],
):
    batches = list(doc_batches)

    def create() -> FakeClient:
        docs = batches.pop(0) if batches else []
        return FakeClient(docs, calls)

    return create


def _outputs(tmp_path: Path) -> AcquisitionOutputs:
    return AcquisitionOutputs(
        raw_output=tmp_path / "materials_project_v1_3_raw.jsonl",
        table_output=tmp_path / "materials_project_v1_3_acquired.csv",
        manifest_output=tmp_path / "materials_project_v1_3_acquisition_manifest.json",
        summary_output=tmp_path / "materials_project_v1_3_acquisition_summary.csv",
    )


def test_exact_query_argument_construction_uses_num_elements_not_nelements() -> None:
    spec = _spec()

    params = build_exact_query_parameters(spec, preflight=False)

    assert params["elements"] == ["Fe", "Si"]
    assert params["num_elements"] == (2, 5)
    assert params["deprecated"] is False
    assert params["include_gnome"] is False
    assert params["all_fields"] is False
    assert params["fields"] == spec["requested_fields"]
    assert params["chunk_size"] == spec["chunk_size"]
    assert "nelements" not in params
    assert "theoretical" not in params
    assert "energy_above_hull" not in params
    assert "is_stable" not in params
    assert "num_chunks" not in params


def test_preflight_limits_sample_and_uses_fake_client_only() -> None:
    spec = _spec()
    calls: list[dict[str, object]] = []
    docs = [_doc("mp-2"), _doc("mp-1", formula="Fe2Si", energy_above_hull=0.0)]

    report = run_preflight(
        spec,
        spec_path=ACQUISITION_SPEC_PATH,
        client_factory=_factory(docs, calls),
        validate_signature=False,
    )

    assert report["preflight_status"] == "passed"
    assert report["sample_row_count"] == 2
    assert report["network_called"] is True
    assert report["credential_included"] is False
    assert report["absolute_path_included"] is False
    assert calls == [
        {
            "elements": ["Fe", "Si"],
            "num_elements": (2, 5),
            "deprecated": False,
            "include_gnome": False,
            "fields": spec["requested_fields"],
            "all_fields": False,
            "chunk_size": 5,
            "num_chunks": 1,
        }
    ]


def test_full_acquisition_writes_raw_order_and_sorted_table(tmp_path: Path) -> None:
    spec = _spec()
    calls: list[dict[str, object]] = []
    docs = [
        _doc("mp-3", formula="FeSiO", chemsys="Fe-O-Si", nelements=3, energy_above_hull=0.08),
        _doc("mp-1", formula="FeSi", chemsys="Fe-Si", energy_above_hull=0.0),
        _doc("mp-2", formula="Fe2Si", chemsys="Fe-Si", energy_above_hull=0.04),
    ]
    outputs = _outputs(tmp_path)

    result = run_full_acquisition(
        spec,
        spec_path=ACQUISITION_SPEC_PATH,
        outputs=outputs,
        client_factory=_factory(docs, calls),
        retry_count=0,
        validate_signature=False,
    )

    assert result["execution_status"] == "success"
    assert len(calls) == 2
    assert calls[0]["num_chunks"] == 1
    assert "num_chunks" not in calls[1]
    raw_lines = outputs.raw_output.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["material_id"] for line in raw_lines] == ["mp-3", "mp-1", "mp-2"]
    table = pd.read_csv(outputs.table_output)
    assert table["material_id"].tolist() == ["mp-1", "mp-2", "mp-3"]
    manifest = json.loads(outputs.manifest_output.read_text(encoding="utf-8"))
    assert manifest["raw_row_count"] == 3
    assert manifest["table_row_count"] == 3
    assert manifest["credential_included"] is False
    assert manifest["absolute_path_included"] is False
    assert not Path(manifest["raw_output_path"]).is_absolute()
    assert not Path(manifest["table_output_path"]).is_absolute()
    summary = pd.read_csv(outputs.summary_output)
    assert {"metric", "value", "severity", "description"}.issubset(summary.columns)


def test_failed_preflight_prevents_full_acquisition_outputs(tmp_path: Path) -> None:
    spec = _spec()
    calls: list[dict[str, object]] = []
    docs = [_doc("mp-1", elements=["Fe"], nelements=1)]
    outputs = _outputs(tmp_path)

    with pytest.raises(AcquisitionStopError, match="Preflight failed"):
        run_full_acquisition(
            spec,
            spec_path=ACQUISITION_SPEC_PATH,
            outputs=outputs,
            client_factory=_factory(docs, calls),
            retry_count=0,
            validate_signature=False,
        )

    assert len(calls) == 1
    assert not outputs.raw_output.exists()
    assert not outputs.table_output.exists()
    assert not outputs.manifest_output.exists()
    assert not outputs.summary_output.exists()


def test_failed_scope_validation_keeps_rows_and_marks_status(tmp_path: Path) -> None:
    spec = _spec()
    calls: list[dict[str, object]] = []
    preflight_docs = [
        _doc("mp-preflight-1", formula="FeSi", elements=["Fe", "Si"], nelements=2),
        _doc("mp-preflight-2", formula="Fe2Si", elements=["Fe", "Si"], nelements=2),
    ]
    full_docs = [
        _doc("mp-1", formula="FeSi", elements=["Fe", "Si"], nelements=2, energy_above_hull=0.0),
        _doc("mp-2", formula="FeO", chemsys="Fe-O", elements=["Fe", "O"], nelements=2, energy_above_hull=0.1),
    ]
    outputs = _outputs(tmp_path)

    result = run_full_acquisition(
        spec,
        spec_path=ACQUISITION_SPEC_PATH,
        outputs=outputs,
        client_factory=_sequence_factory([preflight_docs, full_docs], calls),
        retry_count=0,
        validate_signature=False,
    )

    assert result["execution_status"] == "failed_scope_validation"
    table = pd.read_csv(outputs.table_output)
    assert len(table) == 2
    manifest = json.loads(outputs.manifest_output.read_text(encoding="utf-8"))
    assert manifest["required_element_validation"]["missing_required_element_rows"] == 1
    assert "returned rows missing Fe or Si" in manifest["stop_reasons"]


def test_validation_detects_duplicates_and_preserves_missing_target() -> None:
    spec = _spec()
    docs = [
        _doc("mp-1", energy_above_hull=None),
        _doc("mp-1", formula="Fe2Si", energy_above_hull=0.2),
    ]

    validation = validate_materials_project_documents(docs, spec)
    table = build_acquired_table(docs, spec)

    assert validation["duplicate_material_id_count"] == 2
    assert validation["missing_target_count"] == 1
    assert validation["execution_status"] == "failed_identifier_validation"
    assert len(table) == 2


def test_element_count_validation_marks_out_of_range() -> None:
    spec = _spec()
    docs = [_doc("mp-1", elements=["Fe", "Si", "O", "C", "N", "Al"], nelements=6)]

    validation = validate_materials_project_documents(docs, spec)

    assert validation["execution_status"] == "failed_scope_validation"
    assert validation["element_count_validation"]["out_of_range_rows"] == 1


def test_nested_fields_are_compact_json_strings() -> None:
    spec = _spec()

    table = build_acquired_table([_doc("mp-1")], spec)

    assert isinstance(table.loc[0, "symmetry"], str)
    assert table.loc[0, "symmetry"] == '{"number":221}'
    assert isinstance(table.loc[0, "origins"], str)
