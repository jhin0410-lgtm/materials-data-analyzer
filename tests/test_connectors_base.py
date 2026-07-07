"""Tests for connector base dataclasses."""

from __future__ import annotations

from pathlib import Path

from connectors.base import IngestionResult


def test_ingestion_result_defaults_are_empty() -> None:
    result = IngestionResult(source_name="demo")

    assert result.source_name == "demo"
    assert result.raw_paths == []
    assert result.processed_paths == []
    assert result.row_count == 0
    assert result.column_count == 0
    assert result.warnings == []


def test_ingestion_result_keeps_paths_and_counts() -> None:
    result = IngestionResult(
        source_name="demo",
        raw_paths=[Path("raw.json")],
        processed_paths=[Path("processed.csv")],
        row_count=2,
        column_count=3,
        warnings=["demo warning"],
    )

    assert result.raw_paths[0] == Path("raw.json")
    assert result.processed_paths[0] == Path("processed.csv")
    assert result.row_count == 2
    assert result.column_count == 3
    assert result.warnings == ["demo warning"]
