"""Filesystem-safe transactional output directory handling.

This module protects user data from accidental recursive deletion and keeps
previous valid runs intact until a replacement run has completed successfully.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _is_same_or_ancestor(candidate: Path, path: Path) -> bool:
    return candidate == path or candidate in path.parents


def validate_output_target(
    target: str | Path,
    *,
    protected_paths: Iterable[str | Path] = (),
) -> Path:
    """Return a resolved safe output target or raise ``ValueError``.

    Equality with filesystem root, current directory, user home, or an explicit
    ``MDA_PROJECT_ROOT`` is rejected. A target that equals or contains an input or
    protected path is rejected so overwrite cannot remove its source evidence. A
    dedicated output subdirectory below a source directory remains valid.
    """
    resolved = _resolved(target)
    anchor = Path(resolved.anchor).resolve(strict=False)
    dangerous = {anchor, Path.cwd().resolve(), Path.home().resolve()}
    configured_root = os.environ.get("MDA_PROJECT_ROOT")
    if configured_root:
        dangerous.add(_resolved(configured_root))

    if resolved in dangerous:
        raise ValueError(f"unsafe output directory is protected: {resolved}")

    for protected in protected_paths:
        protected_resolved = _resolved(protected)
        if _is_same_or_ancestor(resolved, protected_resolved):
            raise ValueError(
                "output directory overlaps protected input or project evidence: "
                f"output={resolved}, protected={protected_resolved}"
            )
    return resolved


def _directory_nonempty(path: Path) -> bool:
    return path.is_dir() and any(path.iterdir())


def _has_recognized_marker(path: Path, marker_names: Iterable[str]) -> bool:
    return any((path / marker).is_file() for marker in marker_names)


def _remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


@contextmanager
def transactional_output_directory(
    target: str | Path,
    *,
    overwrite: bool = False,
    protected_paths: Iterable[str | Path] = (),
    recognized_markers: Iterable[str] = (),
) -> Iterator[Path]:
    """Yield a sibling staging directory and atomically promote it on success.

    A non-empty existing target is never removed before the staged run finishes.
    Overwrite of an unrecognized foreign directory is rejected. On any exception,
    the staging directory is removed and the prior valid target is preserved.
    """
    final = validate_output_target(target, protected_paths=protected_paths)
    if final.exists() and not final.is_dir():
        raise FileExistsError(f"output path is not a directory: {final}")

    nonempty = _directory_nonempty(final) if final.exists() else False
    markers = tuple(recognized_markers)
    if nonempty and not overwrite:
        raise FileExistsError(
            f"output directory is non-empty: {final}; choose another path or pass overwrite=True"
        )
    if nonempty and overwrite and markers and not _has_recognized_marker(final, markers):
        raise ValueError(
            "refusing to overwrite an unrecognized non-empty directory; expected one "
            f"of these marker files: {', '.join(markers)}; path={final}"
        )

    final.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{final.name}.mda-staging-", dir=final.parent)
    )
    backup = final.parent / f".{final.name}.mda-backup"
    if backup.exists():
        raise FileExistsError(f"stale output backup exists and requires review: {backup}")

    try:
        yield staging
        previous_moved = False
        try:
            if final.exists():
                os.replace(final, backup)
                previous_moved = True
            os.replace(staging, final)
        except Exception:
            if final.exists() and final != staging:
                _remove_tree(final)
            if previous_moved and backup.exists():
                os.replace(backup, final)
            raise
        if backup.exists():
            _remove_tree(backup)
    except Exception:
        _remove_tree(staging)
        raise
