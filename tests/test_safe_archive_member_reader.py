from __future__ import annotations

import hashlib
import zipfile

import pytest

from materials_data_analyzer.research_loop.safe_archive_inventory import inspect_zip_archive
from materials_data_analyzer.research_loop.safe_archive_member_reader import (
    SafeArchiveMemberReaderError,
    read_verified_text_members,
)


def _archive(tmp_path):
    path = tmp_path / "dataset.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("Dataset/Tribology/README.txt", "state=AM-AB\nmethod=ball-on-disc\n")
        handle.writestr("Dataset/Tribology/friction.dat", "0\t0.1\n1\t0.2\n")
        handle.writestr("Dataset/binary.bin", b"\x00\x01")
    return path


def test_reads_only_explicit_inventory_bound_utf8_members(tmp_path) -> None:
    archive = _archive(tmp_path)
    inventory = inspect_zip_archive(archive)
    result = read_verified_text_members(
        archive,
        inventory,
        ["Dataset/Tribology/README.txt"],
    )
    assert result["selected_member_count"] == 1
    assert result["members"][0]["text"] == "state=AM-AB\nmethod=ball-on-disc\n"
    assert result["members"][0]["sha256"] == hashlib.sha256(
        result["members"][0]["text"].encode("utf-8")
    ).hexdigest()
    assert result["bulk_extraction_performed"] is False
    assert result["semantic_validation_performed"] is False
    assert result["scientific_status_changed"] is False


def test_rejects_archive_bytes_changed_after_inventory(tmp_path) -> None:
    archive = _archive(tmp_path)
    inventory = inspect_zip_archive(archive)
    with zipfile.ZipFile(archive, "a") as handle:
        handle.writestr("new.txt", "changed")
    with pytest.raises(SafeArchiveMemberReaderError, match="archive SHA-256"):
        read_verified_text_members(
            archive,
            inventory,
            ["Dataset/Tribology/README.txt"],
        )


def test_rejects_member_not_verified_as_text(tmp_path) -> None:
    archive = _archive(tmp_path)
    inventory = inspect_zip_archive(archive)
    with pytest.raises(SafeArchiveMemberReaderError, match="hash-verified as bounded text"):
        read_verified_text_members(archive, inventory, ["Dataset/binary.bin"])


def test_rejects_selected_total_budget_overflow(tmp_path) -> None:
    archive = _archive(tmp_path)
    inventory = inspect_zip_archive(archive)
    with pytest.raises(SafeArchiveMemberReaderError, match="byte budget"):
        read_verified_text_members(
            archive,
            inventory,
            ["Dataset/Tribology/README.txt"],
            max_total_bytes=4,
        )
