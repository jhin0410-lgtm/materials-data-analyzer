"""Runtime and artifact provenance helpers shared by user-facing workflows."""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import platform
import sys
from collections.abc import Iterable
from pathlib import Path


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_directory(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        marker = candidate / ".git"
        if marker.is_dir():
            return marker
        if marker.is_file():
            text = marker.read_text(encoding="utf-8", errors="replace").strip()
            prefix = "gitdir:"
            if text.lower().startswith(prefix):
                relative = text[len(prefix) :].strip()
                return (candidate / relative).resolve(strict=False)
    return None


def _packed_ref(git_dir: Path, ref_name: str) -> str | None:
    packed = git_dir / "packed-refs"
    if not packed.is_file():
        return None
    for line in packed.read_text(encoding="utf-8", errors="replace").splitlines():
        text = line.strip()
        if not text or text.startswith(("#", "^")):
            continue
        parts = text.split(" ", 1)
        if len(parts) == 2 and parts[1] == ref_name:
            return parts[0] or None
    return None


def git_commit(root: str | Path | None = None) -> str | None:
    """Return the checked-out commit without executing an external command."""
    env_commit = os.environ.get("GITHUB_SHA") or os.environ.get("MDA_GIT_COMMIT")
    if env_commit:
        return env_commit.strip() or None

    start = Path(root).expanduser().resolve(strict=False) if root else Path.cwd()
    git_dir = _git_directory(start)
    if git_dir is None:
        return None
    head_path = git_dir / "HEAD"
    if not head_path.is_file():
        return None
    head = head_path.read_text(encoding="utf-8", errors="replace").strip()
    if not head:
        return None
    if not head.startswith("ref:"):
        return head
    ref_name = head.split(":", 1)[1].strip()
    loose = git_dir / ref_name
    if loose.is_file():
        return loose.read_text(encoding="utf-8", errors="replace").strip() or None
    return _packed_ref(git_dir, ref_name)


def dependency_versions(names: Iterable[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in sorted(set(names)):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def runtime_environment(*, project_root: str | Path | None = None) -> dict[str, object]:
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "platform": platform.platform(),
        "git_commit": git_commit(project_root),
        "dependencies": dependency_versions(
            ["numpy", "pandas", "matplotlib", "scikit-learn", "scipy", "pymatgen"]
        ),
        "executable_name": Path(sys.executable).name,
    }


def artifact_inventory(
    paths: dict[str, Path], *, root: Path | None = None
) -> dict[str, dict[str, object]]:
    inventory: dict[str, dict[str, object]] = {}
    for name, path in sorted(paths.items()):
        if not path.is_file():
            continue
        display = str(path)
        if root is not None:
            try:
                display = path.relative_to(root).as_posix()
            except ValueError:
                pass
        inventory[name] = {
            "path": display,
            "byte_count": path.stat().st_size,
            "sha256": file_sha256(path),
        }
    return inventory
