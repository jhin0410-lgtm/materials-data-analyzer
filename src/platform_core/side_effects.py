"""Side-effect accounting for controlled platform execution."""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path

from .artifact_resolver import calculate_sha256


IGNORED_TOP_LEVEL_DIRS = {".git", ".pytest_cache", ".pytest_tmp", "__pycache__"}


@dataclass(frozen=True)
class SideEffectSnapshot:
    tracked_status: dict[str, str]
    protected_sha256: dict[str, str]
    file_inventory: tuple[str, ...]
    allowed_output_dir: str


@dataclass(frozen=True)
class SideEffectReport:
    status: str
    tracked_changes: tuple[str, ...]
    protected_changes: tuple[str, ...]
    unexpected_files: tuple[str, ...]
    output_file_count: int
    output_bytes: int
    max_output_files: int
    max_output_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "tracked_changes": list(self.tracked_changes),
            "protected_changes": list(self.protected_changes),
            "unexpected_files": list(self.unexpected_files),
            "output_file_count": self.output_file_count,
            "output_bytes": self.output_bytes,
            "max_output_files": self.max_output_files,
            "max_output_bytes": self.max_output_bytes,
        }


def _normalize_relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _iter_repository_files(root: Path, allowed_output_dir: Path | None = None) -> tuple[str, ...]:
    root = root.resolve()
    allowed = allowed_output_dir.resolve() if allowed_output_dir is not None else None
    files: list[str] = []
    for path in root.rglob("*"):
        try:
            relative_parts = path.relative_to(root).parts
        except ValueError:
            continue
        if not relative_parts:
            continue
        if relative_parts[0] in IGNORED_TOP_LEVEL_DIRS:
            continue
        if allowed is not None:
            resolved = path.resolve()
            if allowed == resolved or allowed in resolved.parents:
                continue
        if path.is_file():
            files.append(path.relative_to(root).as_posix())
    return tuple(sorted(files))


def _parse_git_index_paths(root: Path) -> dict[str, int]:
    index_path = root / ".git" / "index"
    if not index_path.exists():
        return {}
    data = index_path.read_bytes()
    if len(data) < 12 or data[:4] != b"DIRC":
        return {}
    entry_count = struct.unpack(">I", data[8:12])[0]
    offset = 12
    paths: dict[str, int] = {}
    for _ in range(entry_count):
        entry_start = offset
        if offset + 62 > len(data):
            break
        file_size = struct.unpack(">I", data[offset + 36 : offset + 40])[0]
        flags = struct.unpack(">H", data[offset + 60 : offset + 62])[0]
        offset += 62
        if flags & 0x4000:
            offset += 2
        path_end = data.find(b"\x00", offset)
        if path_end < 0:
            break
        path = data[offset:path_end].decode("utf-8", errors="replace")
        paths[path] = file_size
        offset = path_end + 1
        entry_length = offset - entry_start
        padding = (8 - (entry_length % 8)) % 8
        offset += padding
    return paths


def tracked_status(root: str | Path) -> dict[str, str]:
    """Return a lightweight tracked-file status from the Git index."""

    repo = Path(root).resolve()
    statuses: dict[str, str] = {}
    for relative_path, indexed_size in _parse_git_index_paths(repo).items():
        path = repo / relative_path
        if not path.exists():
            statuses[relative_path] = "deleted"
        elif path.is_file() and path.stat().st_size != indexed_size:
            statuses[relative_path] = "modified_size"
    return statuses


def create_side_effect_snapshot(
    repository_root: str | Path,
    protected_paths: dict[str, Path],
    allowed_output_dir: str | Path,
) -> SideEffectSnapshot:
    root = Path(repository_root).resolve()
    allowed = Path(allowed_output_dir).resolve()
    protected_sha = {
        artifact_id: calculate_sha256(path)
        for artifact_id, path in sorted(protected_paths.items())
        if path.exists() and path.is_file()
    }
    return SideEffectSnapshot(
        tracked_status=tracked_status(root),
        protected_sha256=protected_sha,
        file_inventory=_iter_repository_files(root, allowed),
        allowed_output_dir=_normalize_relative(allowed, root),
    )


def evaluate_side_effects(
    repository_root: str | Path,
    snapshot: SideEffectSnapshot,
    protected_paths: dict[str, Path],
    allowed_output_dir: str | Path,
    *,
    max_output_files: int,
    max_output_bytes: int,
) -> SideEffectReport:
    root = Path(repository_root).resolve()
    allowed = Path(allowed_output_dir).resolve()
    before_files = set(snapshot.file_inventory)
    after_files = set(_iter_repository_files(root, allowed))
    unexpected = tuple(sorted(after_files - before_files))
    after_tracked = tracked_status(root)
    tracked_changes = tuple(sorted(path for path, status in after_tracked.items() if status != snapshot.tracked_status.get(path)))
    protected_changes: list[str] = []
    for artifact_id, path in sorted(protected_paths.items()):
        if not path.exists() or not path.is_file():
            protected_changes.append(artifact_id)
            continue
        if calculate_sha256(path) != snapshot.protected_sha256.get(artifact_id):
            protected_changes.append(artifact_id)
    output_files = [path for path in allowed.rglob("*") if path.is_file()] if allowed.exists() else []
    output_bytes = sum(path.stat().st_size for path in output_files)
    status = "allowed_outputs_only"
    if tracked_changes or protected_changes or unexpected:
        status = "prohibited_modification"
    elif len(output_files) > max_output_files or output_bytes > max_output_bytes:
        status = "output_limit_exceeded"
    return SideEffectReport(
        status=status,
        tracked_changes=tracked_changes,
        protected_changes=tuple(sorted(protected_changes)),
        unexpected_files=unexpected,
        output_file_count=len(output_files),
        output_bytes=output_bytes,
        max_output_files=max_output_files,
        max_output_bytes=max_output_bytes,
    )


def write_side_effect_report(report: SideEffectReport, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    try:
        temp.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()
    return path
