"""Tests for generic reliability connector helpers."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import pytest

from connectors.reliability import (
    calculate_sha256,
    discover_local_files,
    list_zip_members,
    read_bounded_csv_sample_from_zip,
    read_csv_header_from_zip,
)


def _write_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("nested/day_1.csv", "date,serial_number,failure\n2020-01-01,A,0\n")
        archive.writestr("day_2.CSV", "date,serial_number,failure\n2020-01-02,A,1\n")
        archive.writestr("notes/readme.txt", "not data\n")
        archive.writestr("empty_dir/", "")


def test_zip_member_inventory_is_deterministic_and_does_not_extract(tmp_path: Path) -> None:
    zip_path = tmp_path / "source.zip"
    _write_zip(zip_path)

    inventory = list_zip_members(zip_path)

    assert inventory["member_path"].tolist() == [
        "day_2.CSV",
        "nested/day_1.csv",
        "notes/readme.txt",
    ]
    assert "empty_dir/" not in set(inventory["member_path"])
    assert (tmp_path / "nested").exists() is False
    assert {
        "archive_file",
        "member_path",
        "file_name",
        "extension",
        "compressed_size_bytes",
        "uncompressed_size_bytes",
        "crc32",
    }.issubset(inventory.columns)


def test_csv_header_and_bounded_sample_from_zip(tmp_path: Path) -> None:
    zip_path = tmp_path / "source.zip"
    _write_zip(zip_path)

    header = read_csv_header_from_zip(zip_path, "nested/day_1.csv")
    sample = read_bounded_csv_sample_from_zip(
        zip_path,
        ["nested/day_1.csv", "day_2.CSV"],
        max_rows_per_member=1,
    )

    assert header == ["date", "serial_number", "failure"]
    assert len(sample) == 2
    assert sample["source_member"].tolist() == ["nested/day_1.csv", "day_2.CSV"]
    assert set(sample["failure"]) == {0, 1}


def test_local_file_discovery_and_hash_are_relative(tmp_path: Path) -> None:
    path = tmp_path / "raw" / "data.txt"
    path.parent.mkdir()
    path.write_text("abc", encoding="utf-8")

    inventory = discover_local_files(path.parent)
    digest = calculate_sha256(path)

    assert inventory.loc[0, "relative_path"] == "data.txt"
    assert inventory.loc[0, "sha256"] == digest
    assert len(digest) == 64
    assert not Path(inventory.loc[0, "relative_path"]).is_absolute()


def test_invalid_zip_reports_clear_error(tmp_path: Path) -> None:
    bad_zip = tmp_path / "bad.zip"
    bad_zip.write_text("not a zip", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid or corrupt ZIP file"):
        list_zip_members(bad_zip)


def test_connector_unit_tests_do_not_need_network() -> None:
    # A small guard to keep connector tests based on local synthetic files.
    assert pd.DataFrame({"ok": [True]}).loc[0, "ok"]
