"""Tests for Materials Project connector helpers."""

from __future__ import annotations

import pytest

from connectors.materials_project_connector import (
    MaterialsProjectConnector,
    build_materials_project_dataframe,
)


def test_materials_project_missing_api_key_raises_runtime_error(monkeypatch) -> None:
    monkeypatch.delenv("MP_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="MP_API_KEY"):
        MaterialsProjectConnector().fetch(limit=1)


def test_materials_project_fake_docs_convert_to_processed_dataframe() -> None:
    docs = [
        {
            "material_id": "mp-1",
            "formula_pretty": "FeSi",
            "band_gap": 0.5,
            "formation_energy_per_atom": -0.4,
            "energy_above_hull": 0.01,
            "density": 5.1,
            "volume": 20.0,
        }
    ]

    df = build_materials_project_dataframe(docs)

    assert df.columns.tolist() == [
        "material_id",
        "formula",
        "band_gap_ev",
        "formation_energy_ev_atom",
        "energy_above_hull_ev_atom",
        "density_g_cm3",
        "volume_a3",
    ]
    assert df.loc[0, "formula"] == "FeSi"
    assert df.loc[0, "band_gap_ev"] == 0.5
