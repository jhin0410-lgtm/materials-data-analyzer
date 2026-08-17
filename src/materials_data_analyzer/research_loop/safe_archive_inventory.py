"""Bounded archive inventory for acquired public evidence.

The archive layer inventories exact members without bulk extraction.  It rejects path
traversal, encrypted members, symlinks, excessive member counts, excessive expanded size,
and unsafe compression ratios before any selected text member is read.  Text member
hashes are computed only within explicit per-file and total byte budgets.
"""
from __future__ import annotations

import hashlib
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .kernel import ResearchLoopError

SAFE_ARCHIVE_INVENTORY_SCHEMA_VERSION = "1.0"
DEFAULT_MAX_MEMBERS = 10000
DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES = 4 * 1024 * 1024 * 1024
DEFAULT_MAX_MEMBER_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
DEFAULT_MAX_COMPRESSION_RATIO = 250.0
DEFAULT_MAX_TEXT_MEMBER_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_TEXT_TOTAL_BYTES = 256 * 1024 * 1024
_TEXT_SUFFIXES = {".csv", ".txt", ".tsv", ".json", ".md", ".dat"}


class SafeArchiveInventoryError(ResearchLoopError):
    """Raised when archive inventory cannot remain bounded and path-safe."""


def _safe_member_name(name: object) -> str:
    if not isinstance(name, str) or not name or name != name.strip():
        raise SafeArchiveInventoryError("archive member name must be non-empty text")
    if "\\" in name or "\x00" in name:
        raise SafeArchiveInventoryError("archive member name contains unsafe characters")
    path = PurePosixPath(name)
    if path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise SafeArchiveInventoryError("archive member path may not escape archive root")
    if not path.parts:
        raise SafeArchiveInventoryError("archive member path is empty")
    return path.as_posix()


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _ratio(info: zipfile.ZipInfo) -> float:
    if info.file_size <= 0:
        return 0.0
    if info.compress_size <= 0:
        return float("inf")
    return info.file_size / info.compress_size


def inspect_zip_archive(
    archive_path: str | Path,
    *,
    max_members: int = DEFAULT_MAX_MEMBERS,
    max_total_uncompressed_bytes: int = DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES,
    max_member_uncompressed_bytes: int = DEFAULT_MAX_MEMBER_UNCOMPRESSED_BYTES,
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO,
    max_text_member_bytes: int = DEFAULT_MAX_TEXT_MEMBER_BYTES,
    max_text_total_bytes: int = DEFAULT_MAX_TEXT_TOTAL_BYTES,
) -> dict[str, Any]:
    target = Path(archive_path)
    for value, field in (
        (max_members, "max_members"),
        (max_total_uncompressed_bytes, "max_total_uncompressed_bytes"),
        (max_member_uncompressed_bytes, "max_member_uncompressed_bytes"),
        (max_text_member_bytes, "max_text_member_bytes"),
        (max_text_total_bytes, "max_text_total_bytes"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise SafeArchiveInventoryError(f"{field} must be a positive integer")
    if (
        isinstance(max_compression_ratio, bool)
        or not isinstance(max_compression_ratio, (int, float))
        or max_compression_ratio <= 1
    ):
        raise SafeArchiveInventoryError("max_compression_ratio must be greater than 1")
    try:
        archive_sha = hashlib.sha256(target.read_bytes()).hexdigest()
        archive_size = target.stat().st_size
    except OSError as exc:
        raise SafeArchiveInventoryError(f"could not read archive: {target}") from exc

    try:
        with zipfile.ZipFile(target, "r") as handle:
            infos = handle.infolist()
            if len(infos) > max_members:
                raise SafeArchiveInventoryError("archive member count exceeds configured ceiling")
            total_uncompressed = 0
            text_total = 0
            members: list[dict[str, Any]] = []
            seen: set[str] = set()
            for info in infos:
                name = _safe_member_name(info.filename)
                if name in seen:
                    raise SafeArchiveInventoryError("archive contains duplicate normalized member names")
                seen.add(name)
                if info.flag_bits & 0x1:
                    raise SafeArchiveInventoryError("encrypted archive members are not allowed")
                if _is_symlink(info):
                    raise SafeArchiveInventoryError("archive symlink members are not allowed")
                if info.file_size < 0 or info.compress_size < 0:
                    raise SafeArchiveInventoryError("archive member sizes are invalid")
                if info.file_size > max_member_uncompressed_bytes:
                    raise SafeArchiveInventoryError("archive member exceeds uncompressed byte ceiling")
                total_uncompressed += info.file_size
                if total_uncompressed > max_total_uncompressed_bytes:
                    raise SafeArchiveInventoryError("archive expanded size exceeds configured ceiling")
                ratio = _ratio(info)
                if ratio > max_compression_ratio:
                    raise SafeArchiveInventoryError("archive member compression ratio exceeds ceiling")
                suffix = PurePosixPath(name).suffix.lower()
                text_candidate = (not info.is_dir()) and suffix in _TEXT_SUFFIXES
                text_sha256: str | None = None
                utf8_decodable: bool | None = None
                line_count: int | None = None
                text_hash_status = "not_text_candidate"
                if text_candidate:
                    if info.file_size > max_text_member_bytes:
                        text_hash_status = "text_member_budget_exceeded"
                    elif text_total + info.file_size > max_text_total_bytes:
                        text_hash_status = "text_batch_budget_exceeded"
                    else:
                        with handle.open(info, "r") as stream:
                            chunks: list[bytes] = []
                            observed = 0
                            while True:
                                chunk = stream.read(min(1024 * 1024, info.file_size - observed + 1))
                                if not chunk:
                                    break
                                observed += len(chunk)
                                if observed > info.file_size:
                                    raise SafeArchiveInventoryError(
                                        "archive member decompressed beyond declared size"
                                    )
                                chunks.append(chunk)
                        body = b"".join(chunks)
                        if len(body) != info.file_size:
                            raise SafeArchiveInventoryError(
                                "archive member decompressed size differs from central directory"
                            )
                        text_total += len(body)
                        text_sha256 = hashlib.sha256(body).hexdigest()
                        try:
                            decoded = body.decode("utf-8")
                        except UnicodeDecodeError:
                            utf8_decodable = False
                        else:
                            utf8_decodable = True
                            line_count = len(decoded.splitlines())
                        text_hash_status = "hashed_within_budget"
                members.append(
                    {
                        "path": name,
                        "is_directory": info.is_dir(),
                        "suffix": suffix,
                        "compressed_size_bytes": info.compress_size,
                        "uncompressed_size_bytes": info.file_size,
                        "compression_ratio": round(ratio, 6),
                        "crc32": f"{info.CRC:08x}",
                        "text_candidate_by_extension": text_candidate,
                        "text_hash_status": text_hash_status,
                        "text_sha256": text_sha256,
                        "utf8_decodable": utf8_decodable,
                        "line_count": line_count,
                    }
                )
    except zipfile.BadZipFile as exc:
        raise SafeArchiveInventoryError("artifact is not a valid ZIP archive") from exc

    members.sort(key=lambda item: item["path"])
    return {
        "schema_version": SAFE_ARCHIVE_INVENTORY_SCHEMA_VERSION,
        "archive_path": str(target),
        "archive_size_bytes": archive_size,
        "archive_sha256": archive_sha,
        "member_count": len(members),
        "total_uncompressed_bytes": total_uncompressed,
        "text_bytes_hashed": text_total,
        "text_candidate_count": sum(
            1 for item in members if item["text_candidate_by_extension"]
        ),
        "text_hashed_count": sum(
            1 for item in members if item["text_hash_status"] == "hashed_within_budget"
        ),
        "members": members,
        "bulk_extraction_performed": False,
        "extension_is_not_semantic_validation": True,
        "scientific_status_changed": False,
    }


__all__ = [
    "DEFAULT_MAX_COMPRESSION_RATIO",
    "DEFAULT_MAX_MEMBER_UNCOMPRESSED_BYTES",
    "DEFAULT_MAX_MEMBERS",
    "DEFAULT_MAX_TEXT_MEMBER_BYTES",
    "DEFAULT_MAX_TEXT_TOTAL_BYTES",
    "DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES",
    "SAFE_ARCHIVE_INVENTORY_SCHEMA_VERSION",
    "SafeArchiveInventoryError",
    "inspect_zip_archive",
]
