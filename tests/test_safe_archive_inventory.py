from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.safe_archive_inventory import (
    SafeArchiveInventoryError,
    inspect_zip_archive,
)


def _write_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for name, body in members.items():
            handle.writestr(name, body)


def test_safe_zip_inventory_hashes_bounded_text_without_extracting(tmp_path: Path) -> None:
    archive = tmp_path / "dataset.zip"
    _write_zip(
        archive,
        {
            "tables/data.csv": b"x,y\n1,2\n",
            "README.txt": b"description\n",
            "images/figure.png": b"not-a-real-png",
        },
    )
    result = inspect_zip_archive(archive)
    assert result["member_count"] == 3
    assert result["text_candidate_count"] == 2
    assert result["text_hashed_count"] == 2
    assert result["bulk_extraction_performed"] is False
    assert result["extension_is_not_semantic_validation"] is True
    csv_record = next(
        item for item in result["members"] if item["path"] == "tables/data.csv"
    )
    assert csv_record["text_sha256"]
    assert csv_record["utf8_decodable"] is True
    assert csv_record["line_count"] == 2


def test_archive_path_traversal_fails_closed(tmp_path: Path) -> None:
    archive = tmp_path / "bad.zip"
    _write_zip(archive, {"../escape.csv": b"x\n1\n"})
    with pytest.raises(SafeArchiveInventoryError, match="escape archive root"):
        inspect_zip_archive(archive)


def test_archive_member_budget_is_enforced_before_text_read(tmp_path: Path) -> None:
    archive = tmp_path / "large.zip"
    _write_zip(archive, {"large.csv": b"a" * 100})
    with pytest.raises(SafeArchiveInventoryError, match="member exceeds"):
        inspect_zip_archive(archive, max_member_uncompressed_bytes=50)


def test_text_hash_budget_does_not_force_bulk_read(tmp_path: Path) -> None:
    archive = tmp_path / "text-budget.zip"
    _write_zip(archive, {"large.csv": b"a" * 100})
    result = inspect_zip_archive(
        archive,
        max_text_member_bytes=50,
        max_member_uncompressed_bytes=1000,
    )
    member = result["members"][0]
    assert member["text_hash_status"] == "text_member_budget_exceeded"
    assert member["text_sha256"] is None
    assert result["text_hashed_count"] == 0


def test_archive_member_count_limit_is_enforced(tmp_path: Path) -> None:
    archive = tmp_path / "many.zip"
    _write_zip(archive, {"a.txt": b"a", "b.txt": b"b"})
    with pytest.raises(SafeArchiveInventoryError, match="member count"):
        inspect_zip_archive(archive, max_members=1)


def test_invalid_zip_fails_closed(tmp_path: Path) -> None:
    archive = tmp_path / "not.zip"
    archive.write_bytes(b"not a zip")
    with pytest.raises(SafeArchiveInventoryError, match="valid ZIP"):
        inspect_zip_archive(archive)
