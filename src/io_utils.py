"""Input, output, and path helpers."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from config import OUTPUT_DIR, PROJECT_ROOT, OutputPaths
from data_io import load_engineering_csv


def resolve_project_path(path_value: str | Path) -> Path:
    """Resolve a user path from PROJECT_ROOT unless it is already absolute."""
    path = Path(path_value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def display_path(path: Path) -> str:
    """Return a readable project-relative path when possible."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def load_data(input_path: Path) -> pd.DataFrame:
    """Load a CSV file through the v0.2 validation layer."""
    return load_engineering_csv(input_path)

def load_csv(input_path: Path) -> pd.DataFrame:
    """Compatibility alias for the older function name."""
    return load_data(input_path)


def resolve_run_name(input_path: Path, run_name: str | None) -> str:
    """Choose the folder name for this analysis run.

    If --run-name is provided, that value is used. Otherwise, the input CSV file
    name without its extension is used.
    """
    raw_name = run_name.strip() if run_name else input_path.stem
    safe_name = re.sub(r"[^\w.-]+", "_", raw_name, flags=re.UNICODE)
    safe_name = safe_name.strip("._-")

    if not safe_name:
        raise ValueError(
            "Run name is empty after cleanup. Please provide a clearer --run-name."
        )

    return safe_name


def create_output_dirs(run_name: str) -> OutputPaths:
    """Create PROJECT_ROOT/outputs/{run_name}/processed, figures, and reports."""
    output_paths = OutputPaths(
        root=OUTPUT_DIR / run_name,
        processed=OUTPUT_DIR / run_name / "processed",
        figures=OUTPUT_DIR / run_name / "figures",
        reports=OUTPUT_DIR / run_name / "reports",
    )

    for directory in [
        output_paths.root,
        output_paths.processed,
        output_paths.figures,
        output_paths.reports,
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    return output_paths


def save_dataframe(df: pd.DataFrame, output_path: Path) -> Path:
    """Save a DataFrame as a CSV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def save_text_report(report_text: str, output_path: Path) -> Path:
    """Save a text report such as a Markdown file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text, encoding="utf-8")
    return output_path


def save_cleaned_data(df: pd.DataFrame, output_paths: OutputPaths) -> Path:
    """Save the cleaned dataset with the standard file name."""
    return save_dataframe(df, output_paths.processed / "cleaned_data.csv")


def safe_file_stem(name: str) -> str:
    """Create a safe file-name stem from a column name or label."""
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", name)
    return safe_name.strip("._-") or "column"
