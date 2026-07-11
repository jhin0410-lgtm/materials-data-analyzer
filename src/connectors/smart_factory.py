"""Local utilities for Smart Factory process-quality dataset acquisition.

This module handles local file discovery, bounded previews, deterministic file
hashing, and SECOM feature/label alignment. It does not train models, calculate
SPC charts, call Kaggle, or perform network acquisition.
"""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from typing import Iterable

import pandas as pd


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA256 digest for a local file."""
    file_path = Path(path)
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_local_files(raw_dir: str | Path, patterns: Iterable[str] = ("*",)) -> pd.DataFrame:
    """Discover local files under ``raw_dir`` without exposing absolute paths."""
    root = Path(raw_dir)
    rows: list[dict[str, object]] = []
    if not root.exists():
        return pd.DataFrame(
            columns=[
                "relative_path",
                "file_name",
                "size_bytes",
                "sha256",
            ]
        )
    for pattern in patterns:
        for path in sorted(root.rglob(pattern)):
            if not path.is_file():
                continue
            rows.append(
                {
                    "relative_path": path.relative_to(root).as_posix(),
                    "file_name": path.name,
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    if not rows:
        return pd.DataFrame(
            columns=[
                "relative_path",
                "file_name",
                "size_bytes",
                "sha256",
            ]
        )
    return pd.DataFrame(rows).drop_duplicates(subset=["relative_path"]).reset_index(drop=True)


def read_bounded_text_preview(path: str | Path, max_lines: int = 5) -> list[str]:
    """Read at most ``max_lines`` text lines from a local file."""
    rows: list[str] = []
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        for _ in range(max_lines):
            line = handle.readline()
            if not line:
                break
            rows.append(line.rstrip("\n"))
    return rows


def extract_zip_members(
    zip_path: str | Path,
    output_dir: str | Path,
    member_names: Iterable[str],
    *,
    overwrite: bool = False,
) -> list[Path]:
    """Extract selected zip members without overwriting existing files by default."""
    archive_path = Path(zip_path)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    member_set = set(member_names)
    extracted: list[Path] = []
    with zipfile.ZipFile(archive_path) as archive:
        names = {Path(name).name: name for name in archive.namelist() if not name.endswith("/")}
        missing = sorted(member_set - set(names))
        if missing:
            raise FileNotFoundError(f"Missing zip members: {', '.join(missing)}")
        for member_name in sorted(member_set):
            output_path = destination / member_name
            if output_path.exists() and not overwrite:
                extracted.append(output_path)
                continue
            with archive.open(names[member_name]) as source, output_path.open("wb") as target:
                target.write(source.read())
            extracted.append(output_path)
    return extracted


def load_secom_features(path: str | Path) -> pd.DataFrame:
    """Load SECOM whitespace-separated process feature matrix."""
    df = pd.read_csv(path, sep=r"\s+", header=None, na_values=["NaN"], engine="python")
    df.columns = [f"feature_{idx:03d}" for idx in range(df.shape[1])]
    return df


def load_secom_labels(path: str | Path) -> pd.DataFrame:
    """Load SECOM pass/fail labels and timestamp columns."""
    labels = pd.read_csv(path, sep=r"\s+", header=None, engine="python")
    if labels.shape[1] < 3:
        raise ValueError("SECOM labels file must contain label, date, and time columns.")
    raw_target = labels.iloc[:, 0].astype(int)
    unexpected_targets = sorted(set(raw_target.dropna()) - {-1, 1})
    if unexpected_targets:
        raise ValueError(
            "SECOM raw target values must be limited to {-1, 1}; "
            f"found {unexpected_targets}"
        )
    timestamp = (
        labels.iloc[:, 1].astype(str) + " " + labels.iloc[:, 2].astype(str)
    ).str.replace('"', "", regex=False)
    return pd.DataFrame(
        {
            "target_raw": raw_target,
            "target_pass_fail": (raw_target == 1).astype(int),
            "observation_timestamp": pd.to_datetime(
                timestamp,
                format="%d/%m/%Y %H:%M:%S",
                errors="coerce",
            ),
        }
    )


def build_secom_aligned_frame(
    feature_path: str | Path,
    label_path: str | Path,
) -> pd.DataFrame:
    """Align SECOM features with labels by original row order only.

    Neither input file is sorted before alignment. The source row position is
    preserved in ``source_sample_index`` starting at zero.
    """
    features = load_secom_features(feature_path)
    labels = load_secom_labels(label_path)
    if len(features) != len(labels):
        raise ValueError(
            "SECOM feature and label row counts do not match: "
            f"{len(features)} != {len(labels)}"
        )
    source_sample_index = pd.Series(range(len(features)), name="source_sample_index")
    sample_ids = pd.Series(
        [f"secom_{idx + 1:05d}" for idx in range(len(features))],
        name="sample_id",
    )
    return pd.concat([source_sample_index, sample_ids, labels, features], axis=1)


def build_schema_inventory(df: pd.DataFrame, dataset_name: str) -> pd.DataFrame:
    """Build a compact schema inventory for an aligned process-quality table."""
    rows: list[dict[str, object]] = []
    for column in df.columns:
        if column == "source_sample_index":
            role = "source_row_order"
        elif column == "sample_id":
            role = "unit_id"
        elif column == "observation_timestamp":
            role = "observation_timestamp"
        elif column.startswith("target_"):
            role = "target"
        elif column.startswith("feature_"):
            role = "process_feature"
        else:
            role = "metadata"
        missing_count = int(df[column].isna().sum())
        rows.append(
            {
                "dataset": dataset_name,
                "column_name": column,
                "role": role,
                "dtype": str(df[column].dtype),
                "non_null_count": int(df[column].notna().sum()),
                "missing_count": missing_count,
                "missing_percent": float(missing_count / len(df) * 100.0) if len(df) else 0.0,
                "unique_count": int(df[column].nunique(dropna=True)),
                "is_numeric": bool(pd.api.types.is_numeric_dtype(df[column])),
            }
        )
    return pd.DataFrame(rows)
