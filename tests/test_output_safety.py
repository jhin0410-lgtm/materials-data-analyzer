"""Tests for non-destructive transactional output handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from platform_core.output_safety import (
    transactional_output_directory,
    validate_output_target,
)


def test_output_target_rejects_current_directory_and_input_overlap(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsafe output directory"):
        validate_output_target(Path.cwd())

    source = tmp_path / "source.csv"
    source.write_text("x\n1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="overlaps protected"):
        validate_output_target(tmp_path, protected_paths=[source])


def test_overwrite_rejects_foreign_nonempty_directory(tmp_path: Path) -> None:
    target = tmp_path / "foreign"
    target.mkdir()
    (target / "personal.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="unrecognized"):
        with transactional_output_directory(
            target,
            overwrite=True,
            recognized_markers=["run_manifest.json"],
        ):
            pass

    assert (target / "personal.txt").read_text(encoding="utf-8") == "keep"


def test_failed_replacement_preserves_previous_valid_run(tmp_path: Path) -> None:
    target = tmp_path / "run"
    target.mkdir()
    (target / "run_manifest.json").write_text("old", encoding="utf-8")
    (target / "prior.txt").write_text("prior", encoding="utf-8")

    with pytest.raises(RuntimeError, match="synthetic failure"):
        with transactional_output_directory(
            target,
            overwrite=True,
            recognized_markers=["run_manifest.json"],
        ) as staging:
            (staging / "run_manifest.json").write_text("new", encoding="utf-8")
            raise RuntimeError("synthetic failure")

    assert (target / "run_manifest.json").read_text(encoding="utf-8") == "old"
    assert (target / "prior.txt").read_text(encoding="utf-8") == "prior"
    assert not list(tmp_path.glob(".run.mda-staging-*"))


def test_successful_replacement_promotes_complete_staged_run(tmp_path: Path) -> None:
    target = tmp_path / "run"
    target.mkdir()
    (target / "run_manifest.json").write_text("old", encoding="utf-8")

    with transactional_output_directory(
        target,
        overwrite=True,
        recognized_markers=["run_manifest.json"],
    ) as staging:
        (staging / "run_manifest.json").write_text("new", encoding="utf-8")
        (staging / "result.csv").write_text("x\n1\n", encoding="utf-8")

    assert (target / "run_manifest.json").read_text(encoding="utf-8") == "new"
    assert (target / "result.csv").is_file()
    assert not (tmp_path / ".run.mda-backup").exists()
