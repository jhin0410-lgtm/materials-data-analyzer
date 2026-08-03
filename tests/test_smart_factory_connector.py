"""Tests for Smart Factory local connector utilities."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import pytest

from connectors.smart_factory import (
    build_schema_inventory,
    build_secom_aligned_frame,
    discover_local_files,
    extract_zip_members,
    load_secom_labels,
    read_bounded_text_preview,
    sha256_file,
)


def test_sha256_file_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "demo.txt"
    path.write_text("same content\n", encoding="utf-8")

    assert sha256_file(path) == sha256_file(path)


def test_bounded_preview_reads_only_requested_lines(tmp_path: Path) -> None:
    path = tmp_path / "preview.txt"
    path.write_text("a\nb\nc\n", encoding="utf-8")

    assert read_bounded_text_preview(path, max_lines=2) == ["a", "b"]


def test_discover_local_files_uses_relative_paths_and_hashes(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    nested = raw_dir / "nested"
    nested.mkdir(parents=True)
    (nested / "secom.data").write_text("1 2 3\n", encoding="utf-8")

    result = discover_local_files(raw_dir, patterns=("*.data",))

    assert result.loc[0, "relative_path"] == "nested/secom.data"
    assert result.loc[0, "file_name"] == "secom.data"
    assert len(result.loc[0, "sha256"]) == 64
    assert str(tmp_path) not in result.to_csv(index=False)


def test_extract_zip_members_does_not_overwrite_existing_file(tmp_path: Path) -> None:
    zip_path = tmp_path / "secom.zip"
    output_dir = tmp_path / "out"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("secom.data", "1 2 3\n")
        archive.writestr("secom_labels.data", "-1 01/01/2020 00:00:00\n")

    extracted = extract_zip_members(
        zip_path,
        output_dir,
        ["secom.data", "secom_labels.data"],
    )
    (output_dir / "secom.data").write_text("local copy\n", encoding="utf-8")
    extract_zip_members(zip_path, output_dir, ["secom.data"], overwrite=False)

    assert {path.name for path in extracted} == {"secom.data", "secom_labels.data"}
    assert (output_dir / "secom.data").read_text(encoding="utf-8") == "local copy\n"


def test_extract_zip_members_reports_missing_member(tmp_path: Path) -> None:
    zip_path = tmp_path / "secom.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("secom.data", "1 2 3\n")

    with pytest.raises(FileNotFoundError, match="secom_labels.data"):
        extract_zip_members(zip_path, tmp_path / "out", ["secom_labels.data"])


def test_secom_feature_label_alignment_and_timestamp_parsing(tmp_path: Path) -> None:
    feature_path = tmp_path / "secom.data"
    label_path = tmp_path / "secom_labels.data"
    feature_path.write_text("1.0 NaN 3.0\n4.0 5.0 6.0\n", encoding="utf-8")
    label_path.write_text("-1 01/01/2020 00:00:00\n1 02/01/2020 01:02:03\n", encoding="utf-8")

    aligned = build_secom_aligned_frame(feature_path, label_path)

    assert aligned.shape == (2, 8)
    assert aligned["source_sample_index"].tolist() == [0, 1]
    assert aligned["sample_id"].tolist() == ["secom_00001", "secom_00002"]
    assert aligned["target_pass_fail"].tolist() == [0, 1]
    assert pd.isna(aligned.loc[0, "feature_001"])
    assert str(aligned.loc[1, "observation_timestamp"]) == "2020-01-02 01:02:03"


def test_secom_alignment_rejects_mismatched_row_counts(tmp_path: Path) -> None:
    feature_path = tmp_path / "secom.data"
    label_path = tmp_path / "secom_labels.data"
    feature_path.write_text("1.0 2.0\n3.0 4.0\n", encoding="utf-8")
    label_path.write_text("-1 01/01/2020 00:00:00\n", encoding="utf-8")

    with pytest.raises(ValueError, match="row counts do not match"):
        build_secom_aligned_frame(feature_path, label_path)


def test_secom_raw_target_values_are_limited_to_minus_one_and_one(tmp_path: Path) -> None:
    label_path = tmp_path / "secom_labels.data"
    label_path.write_text("0 01/01/2020 00:00:00\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"\{-1, 1\}"):
        load_secom_labels(label_path)


def test_secom_target_mapping_is_explicit_fail_one_pass_zero(tmp_path: Path) -> None:
    label_path = tmp_path / "secom_labels.data"
    label_path.write_text("-1 01/01/2020 00:00:00\n1 02/01/2020 00:00:00\n", encoding="utf-8")

    labels = load_secom_labels(label_path)

    assert labels["target_raw"].tolist() == [-1, 1]
    assert labels["target_pass_fail"].tolist() == [0, 1]


def test_secom_ambiguous_timestamp_uses_day_first_format(tmp_path: Path) -> None:
    label_path = tmp_path / "secom_labels.data"
    label_path.write_text("-1 03/04/2020 05:06:07\n", encoding="utf-8")

    labels = load_secom_labels(label_path)

    assert str(labels.loc[0, "observation_timestamp"]) == "2020-04-03 05:06:07"


def test_secom_alignment_preserves_source_order_across_features_targets_and_timestamps(
    tmp_path: Path,
) -> None:
    feature_path = tmp_path / "secom.data"
    label_path = tmp_path / "secom_labels.data"
    feature_path.write_text("10.0 100.0\n20.0 200.0\n30.0 300.0\n", encoding="utf-8")
    label_path.write_text(
        "\n".join(
            [
                '-1 "03/04/2020 05:06:07"',
                '1 "04/04/2020 05:06:07"',
                '-1 "05/04/2020 05:06:07"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    aligned = build_secom_aligned_frame(feature_path, label_path)

    assert aligned["source_sample_index"].tolist() == [0, 1, 2]
    assert aligned["feature_000"].tolist() == [10.0, 20.0, 30.0]
    assert aligned["target_raw"].tolist() == [-1, 1, -1]
    assert aligned["target_pass_fail"].tolist() == [0, 1, 0]
    assert str(aligned.loc[0, "observation_timestamp"]) == "2020-04-03 05:06:07"
    assert str(aligned.loc[1, "observation_timestamp"]) == "2020-04-04 05:06:07"


def test_schema_inventory_identifies_roles(tmp_path: Path) -> None:
    feature_path = tmp_path / "secom.data"
    label_path = tmp_path / "secom_labels.data"
    feature_path.write_text("1.0 2.0\n", encoding="utf-8")
    label_path.write_text("1 01/01/2020 00:00:00\n", encoding="utf-8")
    aligned = build_secom_aligned_frame(feature_path, label_path)

    inventory = build_schema_inventory(aligned, dataset_name="uci_secom")
    roles = dict(zip(inventory["column_name"], inventory["role"], strict=True))

    assert roles["source_sample_index"] == "source_row_order"
    assert roles["sample_id"] == "unit_id"
    assert roles["observation_timestamp"] == "observation_timestamp"
    assert roles["target_pass_fail"] == "target"
    assert roles["feature_000"] == "process_feature"


def test_extract_zip_members_rejects_duplicate_basenames(tmp_path: Path) -> None:
    zip_path = tmp_path / "ambiguous.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("first/secom.data", "1 2 3\n")
        archive.writestr("second/secom.data", "4 5 6\n")

    with pytest.raises(ValueError, match="duplicate.*basename"):
        extract_zip_members(zip_path, tmp_path / "out", ["secom.data"])
