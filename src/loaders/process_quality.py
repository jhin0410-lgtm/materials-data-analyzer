"""Generic loaders for process-quality tabular datasets.

The helpers in this module preserve source row order and align a numeric
feature matrix with ordered label/timestamp rows by row position. Dataset
specific target mappings and timestamp formats are injected by configuration;
the loader does not hard-code SECOM-specific labels.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class ProcessQualityLoadConfig:
    """Configuration for row-position process-quality table construction."""

    feature_prefix: str
    target_mapping: Mapping[int, int]
    timestamp_format: str
    timestamp_dayfirst: bool = True
    raw_target_column: str = "target_raw"
    mapped_target_column: str = "target_failure"
    timestamp_column: str = "observation_timestamp"
    raw_timestamp_column: str = "source_timestamp_raw"
    sample_index_column: str = "sample_index"
    source_order_column: str = "source_order_index"
    chronological_rank_column: str = "chronological_rank"


def load_whitespace_numeric_matrix(
    path: str | Path,
    feature_prefix: str,
) -> pd.DataFrame:
    """Load a whitespace-separated numeric matrix with deterministic names."""
    df = pd.read_csv(path, sep=r"\s+", header=None, na_values=["NaN"], engine="python")
    df.columns = [f"{feature_prefix}{idx:03d}" for idx in range(df.shape[1])]
    return df


def load_ordered_label_timestamp_rows(
    path: str | Path,
    config: ProcessQualityLoadConfig,
) -> pd.DataFrame:
    """Load target and timestamp rows without sorting or reindexing."""
    labels = pd.read_csv(path, sep=r"\s+", header=None, engine="python")
    if labels.shape[1] < 3:
        raise ValueError("Label file must contain target, date, and time columns.")

    raw_target = labels.iloc[:, 0].astype(int)
    allowed_targets = set(config.target_mapping)
    unexpected_targets = sorted(set(raw_target.dropna()) - allowed_targets)
    if unexpected_targets:
        raise ValueError(
            "Unexpected raw target values; expected "
            f"{sorted(allowed_targets)}, found {unexpected_targets}"
        )

    raw_timestamp = (
        labels.iloc[:, 1].astype(str) + " " + labels.iloc[:, 2].astype(str)
    ).str.replace('"', "", regex=False)
    parsed_timestamp = pd.to_datetime(
        raw_timestamp,
        format=config.timestamp_format,
        dayfirst=config.timestamp_dayfirst,
        errors="coerce",
    )

    return pd.DataFrame(
        {
            config.raw_target_column: raw_target,
            config.mapped_target_column: raw_target.map(config.target_mapping).astype(int),
            config.raw_timestamp_column: raw_timestamp,
            config.timestamp_column: parsed_timestamp,
        }
    )


def build_row_position_aligned_table(
    feature_path: str | Path,
    label_path: str | Path,
    config: ProcessQualityLoadConfig,
) -> pd.DataFrame:
    """Build an analysis-ready table using source row position as the key."""
    features = load_whitespace_numeric_matrix(feature_path, config.feature_prefix)
    labels = load_ordered_label_timestamp_rows(label_path, config)
    if len(features) != len(labels):
        raise ValueError(
            "Feature and label row counts do not match: "
            f"{len(features)} != {len(labels)}"
        )

    sample_index = pd.Series(range(len(features)), name=config.sample_index_column)
    source_order = pd.Series(range(len(features)), name=config.source_order_column)
    base = pd.concat([sample_index, labels, source_order, features], axis=1).copy()
    chronological_rank = build_chronological_rank(
        base,
        timestamp_column=config.timestamp_column,
        source_order_column=config.source_order_column,
    )
    extra_columns = {config.chronological_rank_column: chronological_rank}
    if "target_pass_fail" not in base.columns:
        extra_columns["target_pass_fail"] = base[config.mapped_target_column]
    aligned = pd.concat([base, pd.DataFrame(extra_columns)], axis=1).copy()

    ordered_columns = [
        config.sample_index_column,
        config.raw_timestamp_column,
        config.timestamp_column,
        config.source_order_column,
        config.chronological_rank_column,
        config.raw_target_column,
        "target_pass_fail",
        config.mapped_target_column,
    ]
    feature_columns = [column for column in aligned.columns if column.startswith(config.feature_prefix)]
    return aligned[ordered_columns + feature_columns]


def build_chronological_rank(
    df: pd.DataFrame,
    *,
    timestamp_column: str,
    source_order_column: str,
) -> pd.Series:
    """Create a deterministic chronological rank with source order tie-breaks."""
    ordered_index = (
        df[[timestamp_column, source_order_column]]
        .sort_values(
            [timestamp_column, source_order_column],
            ascending=[True, True],
            na_position="last",
            kind="mergesort",
        )
        .index
    )
    ranks = pd.Series(range(len(df)), index=ordered_index, dtype="int64")
    return ranks.sort_index()
