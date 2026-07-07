"""Tests for HTEM connector helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from connectors.htem_connector import HTEMConnector


def test_htem_extract_scalar_fields_excludes_nested_values() -> None:
    connector = HTEMConnector(elements=["Zn", "Sn"])
    sample_json = {
        "sample_id": "sample-1",
        "band_gap": 1.2,
        "is_valid": True,
        "spectrum": [1, 2, 3],
        "metadata": {"nested": "value"},
        "note": None,
    }

    result = connector.extract_scalar_fields(sample_json)

    assert result == {
        "sample_id": "sample-1",
        "band_gap": 1.2,
        "is_valid": True,
        "note": None,
    }


def test_htem_build_sample_property_table_uses_fake_fetch(monkeypatch) -> None:
    connector = HTEMConnector(elements=["Zn", "Sn"])
    test_raw_dir = Path("outputs") / "_connector_tests" / "htem_raw"
    monkeypatch.setattr("connectors.htem_connector.RAW_DIR", test_raw_dir)

    def fake_fetch_sample(sample_id: str) -> dict[str, object]:
        return {
            "sample_id": sample_id,
            "band_gap": 1.5,
            "spectrum": [1, 2, 3],
        }

    monkeypatch.setattr(connector, "fetch_sample", fake_fetch_sample)
    df, raw_paths = connector.build_sample_property_table(
        sample_ids=["s1", "s2"],
        library_id="lib1",
        limit=2,
    )

    assert isinstance(df, pd.DataFrame)
    assert df["sample_id"].tolist() == ["s1", "s2"]
    assert "spectrum" not in df.columns
    assert len(raw_paths) == 2
