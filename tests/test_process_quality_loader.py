"""Tests for generic process-quality row-position loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from loaders.process_quality import (
    ProcessQualityLoadConfig,
    build_row_position_aligned_table,
    load_ordered_label_timestamp_rows,
)


def _config() -> ProcessQualityLoadConfig:
    return ProcessQualityLoadConfig(
        feature_prefix="process_feature_",
        target_mapping={-1: 0, 1: 1},
        timestamp_format="%d/%m/%Y %H:%M:%S",
        timestamp_dayfirst=True,
    )


def test_row_count_mismatch_stops(tmp_path: Path) -> None:
    feature_path = tmp_path / "features.data"
    label_path = tmp_path / "labels.data"
    feature_path.write_text("1 2\n3 4\n", encoding="utf-8")
    label_path.write_text("-1 01/02/2020 00:00:00\n", encoding="utf-8")

    with pytest.raises(ValueError, match="row counts do not match"):
        build_row_position_aligned_table(feature_path, label_path, _config())


def test_no_independent_sorting_before_join_and_source_order_preserved(tmp_path: Path) -> None:
    feature_path = tmp_path / "features.data"
    label_path = tmp_path / "labels.data"
    feature_path.write_text("10 100\n20 200\n30 300\n", encoding="utf-8")
    label_path.write_text(
        "\n".join(
            [
                "1 03/02/2020 00:00:00",
                "-1 01/02/2020 00:00:00",
                "1 02/02/2020 00:00:00",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = build_row_position_aligned_table(feature_path, label_path, _config())

    assert result["sample_index"].tolist() == [0, 1, 2]
    assert result["source_order_index"].tolist() == [0, 1, 2]
    assert result["process_feature_000"].tolist() == [10, 20, 30]
    assert result["target_raw"].tolist() == [1, -1, 1]
    assert result["target_failure"].tolist() == [1, 0, 1]
    assert result["chronological_rank"].tolist() == [2, 0, 1]


def test_unknown_target_is_rejected(tmp_path: Path) -> None:
    label_path = tmp_path / "labels.data"
    label_path.write_text("0 01/02/2020 00:00:00\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unexpected raw target"):
        load_ordered_label_timestamp_rows(label_path, _config())


def test_day_first_ambiguous_timestamp_parsing(tmp_path: Path) -> None:
    label_path = tmp_path / "labels.data"
    label_path.write_text('-1 "03/04/2020 05:06:07"\n', encoding="utf-8")

    labels = load_ordered_label_timestamp_rows(label_path, _config())

    assert labels.loc[0, "source_timestamp_raw"] == "03/04/2020 05:06:07"
    assert str(labels.loc[0, "observation_timestamp"]) == "2020-04-03 05:06:07"


def test_equal_timestamp_chronological_rank_uses_source_order_tiebreak(tmp_path: Path) -> None:
    feature_path = tmp_path / "features.data"
    label_path = tmp_path / "labels.data"
    feature_path.write_text("10\n20\n30\n", encoding="utf-8")
    label_path.write_text(
        "\n".join(
            [
                "-1 01/02/2020 00:00:00",
                "1 01/02/2020 00:00:00",
                "-1 02/02/2020 00:00:00",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = build_row_position_aligned_table(feature_path, label_path, _config())

    assert result["chronological_rank"].tolist() == [0, 1, 2]
