"""Tests for run output and provenance behavior."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import pytest

import io_utils
from io_utils import create_output_dirs
from platform_core.runtime_provenance import (
    artifact_inventory,
    dependency_versions,
    file_sha256,
    git_commit,
    runtime_environment,
)
from process_data import run_selected_analysis


def _eda_args(input_path: Path, run_name: str, overwrite: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        input=str(input_path),
        target=None,
        targets=None,
        features=None,
        scenario_input=None,
        design_method="random",
        design_samples=100,
        grid_levels=5,
        group_column=None,
        goal="maximize",
        goals=None,
        lsl=None,
        usl=None,
        mode="eda",
        run_name=run_name,
        overwrite=overwrite,
        dataset_contract=None,
        decision_grade=False,
        target_weights=None,
        constraint_config=None,
    )


def test_existing_nonempty_run_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(io_utils, "OUTPUT_DIR", tmp_path)
    existing = tmp_path / "existing" / "reports"
    existing.mkdir(parents=True)
    (existing / "prior.md").write_text("prior", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists and is not empty"):
        create_output_dirs("existing")


def test_explicit_overwrite_recreates_run_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(io_utils, "OUTPUT_DIR", tmp_path)
    existing = tmp_path / "existing"
    existing.mkdir()
    prior = existing / "prior.txt"
    prior.write_text("prior", encoding="utf-8")

    output_paths = create_output_dirs("existing", overwrite=True)

    assert output_paths.root == existing
    assert not prior.exists()
    assert output_paths.processed.is_dir()
    assert output_paths.figures.is_dir()
    assert output_paths.reports.is_dir()


def test_analysis_run_writes_audit_and_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(io_utils, "OUTPUT_DIR", tmp_path / "outputs")
    input_path = tmp_path / "input.csv"
    pd.DataFrame(
        {
            "Sample ID": ["S1", "S2", "S3"],
            "Measured Value": ["1.0", "2.0", "3.0"],
        }
    ).to_csv(input_path, index=False)

    output_files = run_selected_analysis(_eda_args(input_path, "audited_run"))

    audit = json.loads(
        output_files["preprocessing_audit"].read_text(encoding="utf-8")
    )
    manifest = json.loads(output_files["run_manifest"].read_text(encoding="utf-8"))

    assert audit["column_name_policy"] == "fail_on_collision"
    assert audit["input_row_count"] == 3
    assert audit["output_row_count"] == 3
    assert manifest["run_name"] == "audited_run"
    assert manifest["mode"] == "eda"
    assert len(manifest["input"]["sha256"]) == 64
    audit_path = manifest["preprocessing"]["audit_path"].replace("\\", "/")
    assert audit_path.endswith("processed/preprocessing_audit.json")
    assert manifest["overwrite_requested"] is False
    assert manifest["terminal_status"] == "completed"
    assert manifest["runtime_environment"]["python_version"]
    assert "executable_name" in manifest["runtime_environment"]
    assert "executable" not in manifest["runtime_environment"]
    assert manifest["artifacts"]["preprocessing_audit"]["byte_count"] > 0
    assert len(manifest["artifacts"]["preprocessing_audit"]["sha256"]) == 64
    assert output_files["preprocessing_exclusions"].is_file()
    assert output_files["dataset_contract_audit"].is_file()


def test_analysis_run_rejects_ambiguous_headers_before_output_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(io_utils, "OUTPUT_DIR", tmp_path / "outputs")
    input_path = tmp_path / "collision.csv"
    pd.DataFrame(
        [[700, 710], [720, 730]],
        columns=["Process Temp C", "Process-Temp-C"],
    ).to_csv(input_path, index=False)

    with pytest.raises(ValueError, match="collide after normalization"):
        run_selected_analysis(_eda_args(input_path, "collision"))

    assert not (tmp_path / "outputs" / "collision").exists()


def test_git_commit_prefers_explicit_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    monkeypatch.setenv("MDA_GIT_COMMIT", "fallback")

    assert git_commit() == "abc123"


def test_git_commit_reads_loose_detached_and_packed_refs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.delenv("MDA_GIT_COMMIT", raising=False)

    loose_repo = tmp_path / "loose"
    loose_git = loose_repo / ".git"
    (loose_git / "refs" / "heads").mkdir(parents=True)
    (loose_git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (loose_git / "refs" / "heads" / "main").write_text(
        "1" * 40 + "\n", encoding="utf-8"
    )
    assert git_commit(loose_repo) == "1" * 40

    detached_repo = tmp_path / "detached"
    detached_git = detached_repo / ".git"
    detached_git.mkdir(parents=True)
    (detached_git / "HEAD").write_text("2" * 40 + "\n", encoding="utf-8")
    assert git_commit(detached_repo) == "2" * 40

    packed_repo = tmp_path / "packed"
    packed_git = packed_repo / ".git"
    packed_git.mkdir(parents=True)
    (packed_git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (packed_git / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled\n"
        + "3" * 40
        + " refs/heads/main\n",
        encoding="utf-8",
    )
    assert git_commit(packed_repo) == "3" * 40


def test_git_commit_resolves_worktree_gitdir_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.delenv("MDA_GIT_COMMIT", raising=False)
    repo = tmp_path / "worktree"
    repo.mkdir()
    git_dir = tmp_path / "actual-git-dir"
    git_dir.mkdir()
    (repo / ".git").write_text("gitdir: ../actual-git-dir\n", encoding="utf-8")
    (git_dir / "HEAD").write_text("4" * 40 + "\n", encoding="utf-8")

    assert git_commit(repo) == "4" * 40
    assert git_commit(tmp_path / "not-a-repository") is None


def test_dependency_and_artifact_inventory_are_deterministic(tmp_path: Path) -> None:
    artifact = tmp_path / "run" / "artifact.txt"
    artifact.parent.mkdir()
    artifact.write_text("evidence", encoding="utf-8")
    missing = tmp_path / "missing.txt"

    inventory = artifact_inventory(
        {"missing": missing, "evidence": artifact}, root=tmp_path
    )

    assert list(inventory) == ["evidence"]
    assert inventory["evidence"]["path"] == "run/artifact.txt"
    assert inventory["evidence"]["byte_count"] == len("evidence")
    assert inventory["evidence"]["sha256"] == file_sha256(artifact)
    assert dependency_versions(["definitely-not-installed-mda-package"])[
        "definitely-not-installed-mda-package"
    ] == "not-installed"


def test_runtime_environment_records_bounded_reproducibility_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MDA_GIT_COMMIT", "5" * 40)
    monkeypatch.delenv("GITHUB_SHA", raising=False)

    environment = runtime_environment(project_root=tmp_path)

    assert environment["git_commit"] == "5" * 40
    assert environment["python_version"]
    assert environment["python_implementation"]
    assert environment["os"]
    assert environment["architecture"]
    assert environment["executable_name"]
    assert "numpy" in environment["dependencies"]
