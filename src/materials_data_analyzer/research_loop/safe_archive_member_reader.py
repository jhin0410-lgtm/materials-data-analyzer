"""Read selected archive text members only after an exact safe inventory is available."""
from __future__ import annotations

import hashlib
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .kernel import ResearchLoopError

SAFE_ARCHIVE_MEMBER_READER_SCHEMA_VERSION = "1.0"
DEFAULT_MAX_SELECTED_MEMBER_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_SELECTED_TOTAL_BYTES = 16 * 1024 * 1024


class SafeArchiveMemberReaderError(ResearchLoopError):
    """Raised when selected member bytes do not match the prior safe inventory."""


def _sha(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise SafeArchiveMemberReaderError(f"{field} must be lowercase SHA-256")
    return value


def read_verified_text_members(
    archive_path: str | Path,
    inventory: Mapping[str, Any],
    member_paths: Sequence[str],
    *,
    max_member_bytes: int = DEFAULT_MAX_SELECTED_MEMBER_BYTES,
    max_total_bytes: int = DEFAULT_MAX_SELECTED_TOTAL_BYTES,
) -> dict[str, Any]:
    """Read only explicitly selected UTF-8 members and reverify all inventory bindings."""
    if isinstance(max_member_bytes, bool) or not isinstance(max_member_bytes, int) or max_member_bytes <= 0:
        raise SafeArchiveMemberReaderError("max_member_bytes must be a positive integer")
    if isinstance(max_total_bytes, bool) or not isinstance(max_total_bytes, int) or max_total_bytes <= 0:
        raise SafeArchiveMemberReaderError("max_total_bytes must be a positive integer")
    if not isinstance(member_paths, Sequence) or isinstance(member_paths, (str, bytes, bytearray)):
        raise SafeArchiveMemberReaderError("member_paths must be a sequence")
    if not isinstance(inventory, Mapping) or not isinstance(inventory.get("members"), list):
        raise SafeArchiveMemberReaderError("inventory is malformed")
    if inventory.get("bulk_extraction_performed") is not False:
        raise SafeArchiveMemberReaderError("inventory must preserve no-bulk-extraction boundary")

    target = Path(archive_path)
    try:
        observed_archive_sha = hashlib.sha256(target.read_bytes()).hexdigest()
    except OSError as exc:
        raise SafeArchiveMemberReaderError("could not read archive") from exc
    expected_archive_sha = _sha(inventory.get("archive_sha256"), "inventory.archive_sha256")
    if observed_archive_sha != expected_archive_sha:
        raise SafeArchiveMemberReaderError("archive SHA-256 differs from inventoried bytes")

    indexed: dict[str, Mapping[str, Any]] = {}
    for raw in inventory["members"]:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("path"), str):
            raise SafeArchiveMemberReaderError("inventory member is malformed")
        path = raw["path"]
        if path in indexed:
            raise SafeArchiveMemberReaderError("inventory contains duplicate member paths")
        indexed[path] = raw

    requested: list[str] = []
    for raw_path in member_paths:
        if not isinstance(raw_path, str) or not raw_path.strip() or raw_path != raw_path.strip():
            raise SafeArchiveMemberReaderError("member path must be non-empty trimmed text")
        if raw_path in requested:
            raise SafeArchiveMemberReaderError("member_paths must not contain duplicates")
        requested.append(raw_path)

    total = 0
    records: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(target, "r") as handle:
            zip_names = set(handle.namelist())
            for path in requested:
                member = indexed.get(path)
                if member is None or path not in zip_names:
                    raise SafeArchiveMemberReaderError("selected member is absent from archive inventory")
                if member.get("text_hash_status") != "hashed_within_budget":
                    raise SafeArchiveMemberReaderError("selected member was not hash-verified as bounded text")
                if member.get("utf8_decodable") is not True:
                    raise SafeArchiveMemberReaderError("selected member is not verified UTF-8 text")
                expected_size = member.get("uncompressed_size_bytes")
                if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 0:
                    raise SafeArchiveMemberReaderError("selected member size is invalid")
                if expected_size > max_member_bytes or total + expected_size > max_total_bytes:
                    raise SafeArchiveMemberReaderError("selected member read exceeds configured byte budget")
                body = handle.read(path)
                if len(body) != expected_size:
                    raise SafeArchiveMemberReaderError("selected member size differs from inventory")
                observed_sha = hashlib.sha256(body).hexdigest()
                expected_sha = _sha(member.get("text_sha256"), "inventory member text_sha256")
                if observed_sha != expected_sha:
                    raise SafeArchiveMemberReaderError("selected member SHA-256 differs from inventory")
                try:
                    text = body.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise SafeArchiveMemberReaderError("selected member is no longer UTF-8 decodable") from exc
                total += len(body)
                records.append(
                    {
                        "path": path,
                        "size_bytes": len(body),
                        "sha256": observed_sha,
                        "line_count": len(text.splitlines()),
                        "text": text,
                    }
                )
    except zipfile.BadZipFile as exc:
        raise SafeArchiveMemberReaderError("artifact is not a valid ZIP archive") from exc

    return {
        "schema_version": SAFE_ARCHIVE_MEMBER_READER_SCHEMA_VERSION,
        "archive_sha256": observed_archive_sha,
        "selected_member_count": len(records),
        "selected_total_bytes": total,
        "members": records,
        "bulk_extraction_performed": False,
        "scientific_status_changed": False,
        "semantic_validation_performed": False,
    }


__all__ = [
    "DEFAULT_MAX_SELECTED_MEMBER_BYTES",
    "DEFAULT_MAX_SELECTED_TOTAL_BYTES",
    "SAFE_ARCHIVE_MEMBER_READER_SCHEMA_VERSION",
    "SafeArchiveMemberReaderError",
    "read_verified_text_members",
]
