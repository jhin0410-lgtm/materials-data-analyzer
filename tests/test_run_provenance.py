"""Tests for run output and provenance behavior."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import pytest

import io_utils
from io_utils import create_output_dirs
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
