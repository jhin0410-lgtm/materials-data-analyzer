"""Generic reliability source discovery and bounded acquisition helpers.

The helpers in this module are dataset-agnostic. They can inspect local raw
files, compute hashes, list ZIP members, download a bounded public artifact
when explicitly requested by a script, and preview CSV content without
extracting entire archives. Importing this module never performs network I/O.
"""

from __future__ import annotations

import csv
import hashlib
import io
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class DownloadResult:
    """Result of an explicitly requested bounded download."""

    url: str
    output_path: Path
    bytes_written: int
    sha256: str
    status: str


def calculate_sha256(path: str | Path) -> str:
    """Calculate SHA-256 for a local file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_local_files(raw_dir: str | Path) -> pd.DataFrame:
    """Return local file inventory without reading file contents."""
    root = Path(raw_dir)
    rows = []
    if not root.exists():
        return pd.DataFrame(
            columns=["relative_path", "file_name", "extension", "size_bytes", "sha256"]
        )
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rows.append(
            {
                "relative_path": path.relative_to(root).as_posix(),
                "file_name": path.name,
                "extension": path.suffix.lower(),
                "size_bytes": path.stat().st_size,
                "sha256": calculate_sha256(path),
            }
        )
    return pd.DataFrame(rows)


def list_zip_members(zip_path: str | Path) -> pd.DataFrame:
    """List ZIP members without extracting them."""
    path = Path(zip_path)
    rows = []
    try:
        with zipfile.ZipFile(path) as archive:
            for info in sorted(archive.infolist(), key=lambda item: item.filename):
                if info.is_dir():
                    continue
                rows.append(
                    {
                        "archive_file": path.name,
                        "member_path": info.filename,
                        "file_name": Path(info.filename).name,
                        "extension": Path(info.filename).suffix.lower(),
                        "compressed_size_bytes": int(info.compress_size),
                        "uncompressed_size_bytes": int(info.file_size),
                        "crc32": f"{info.CRC:08x}",
                    }
                )
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Invalid or corrupt ZIP file: {path}") from exc
    return pd.DataFrame(rows)


def read_csv_header_from_zip(zip_path: str | Path, member_path: str) -> list[str]:
    """Read only the header row from a CSV member inside a ZIP archive."""
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open(member_path) as handle:
            text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace", newline="")
            reader = csv.reader(text)
            return next(reader)


def read_bounded_csv_sample_from_zip(
    zip_path: str | Path,
    member_paths: Iterable[str],
    *,
    max_rows_per_member: int | None = 5000,
    usecols: list[str] | None = None,
) -> pd.DataFrame:
    """Read a bounded sample from selected CSV members without extraction."""
    frames = []
    with zipfile.ZipFile(zip_path) as archive:
        for member in member_paths:
            with archive.open(member) as handle:
                frame = pd.read_csv(
                    handle,
                    nrows=max_rows_per_member if max_rows_per_member and max_rows_per_member > 0 else None,
                    usecols=usecols,
                    encoding="utf-8",
                    encoding_errors="replace",
                    low_memory=False,
                )
                frame.insert(0, "source_member", member)
                frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def get_remote_file_metadata(url: str, *, timeout: int = 30) -> dict[str, object]:
    """Return basic remote file metadata using HEAD when the source supports it."""
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "materials-data-analyzer"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            headers = response.headers
            return {
                "url": url,
                "status": "reachable",
                "content_length": _int_or_none(headers.get("Content-Length")),
                "content_type": headers.get("Content-Type"),
                "etag": headers.get("ETag"),
                "last_modified": headers.get("Last-Modified"),
            }
    except Exception as exc:  # pragma: no cover - exercised with injected tests at caller level
        return {
            "url": url,
            "status": "unreachable",
            "error": str(exc),
        }


def download_file(
    url: str,
    output_path: str | Path,
    *,
    max_bytes: int,
    timeout: int = 60,
) -> DownloadResult:
    """Download a file with an explicit byte budget."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    metadata = get_remote_file_metadata(url, timeout=timeout)
    content_length = metadata.get("content_length")
    if isinstance(content_length, int) and content_length > max_bytes:
        raise ValueError(
            f"Remote file is {content_length} bytes, exceeding budget {max_bytes} bytes: {url}"
        )
    bytes_written = 0
    digest = hashlib.sha256()
    request = urllib.request.Request(url, headers={"User-Agent": "materials-data-analyzer"})
    with urllib.request.urlopen(request, timeout=timeout) as response, target.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > max_bytes:
                handle.close()
                target.unlink(missing_ok=True)
                raise ValueError(
                    f"Downloaded bytes exceeded budget {max_bytes} bytes: {url}"
                )
            digest.update(chunk)
            handle.write(chunk)
    return DownloadResult(
        url=url,
        output_path=target,
        bytes_written=bytes_written,
        sha256=digest.hexdigest(),
        status="downloaded",
    )


def _int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
