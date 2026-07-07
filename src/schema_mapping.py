"""Column schema mapping helpers for external tabular datasets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class ColumnMapping:
    """Describe how one source column maps into the project schema."""

    original_name: str
    standard_name: str
    unit: str | None
    role: str | None
    description: str | None = None


def apply_schema_mapping(
    df: pd.DataFrame, mappings: Iterable[ColumnMapping]
) -> pd.DataFrame:
    """Rename mapped source columns while preserving unmapped columns."""
    rename_map: dict[str, str] = {}
    standard_names: list[str] = []

    for mapping in mappings:
        if mapping.original_name in df.columns:
            rename_map[mapping.original_name] = mapping.standard_name
            standard_names.append(mapping.standard_name)

    duplicate_standard_names = sorted(
        {
            standard_name
            for standard_name in standard_names
            if standard_names.count(standard_name) > 1
        }
    )
    if duplicate_standard_names:
        raise ValueError(
            "Schema mapping would create duplicate standard column names: "
            f"{duplicate_standard_names}"
        )

    renamed_columns = [
        rename_map.get(column, column)
        for column in df.columns
    ]
    duplicate_output_columns = sorted(
        {
            column
            for column in renamed_columns
            if renamed_columns.count(column) > 1
        }
    )
    if duplicate_output_columns:
        raise ValueError(
            "Schema mapping would create duplicate DataFrame columns: "
            f"{duplicate_output_columns}"
        )

    return df.rename(columns=rename_map).copy()
