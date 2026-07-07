"""Domain constraint checks for tabular engineering datasets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class DomainConstraint:
    """Describe a simple allowed range or value set for one column."""

    column: str
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list | None = None
    description: str | None = None


def format_example_values(series: pd.Series, limit: int = 5) -> list[Any]:
    """Return a small list of example values for a violation report."""
    return series.dropna().head(limit).tolist()


def validate_domain_constraints(
    df: pd.DataFrame, constraints: list[DomainConstraint] | None
) -> pd.DataFrame:
    """Return a table of domain-constraint violation summaries."""
    columns = [
        "column",
        "rule",
        "violation_count",
        "violation_percent",
        "example_values",
    ]
    if not constraints:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, object]] = []
    row_count = len(df)

    for constraint in constraints:
        if constraint.column not in df.columns:
            rows.append(
                {
                    "column": constraint.column,
                    "rule": "column_missing",
                    "violation_count": row_count,
                    "violation_percent": 100.0 if row_count else 0.0,
                    "example_values": [],
                }
            )
            continue

        series = df[constraint.column]
        if constraint.min_value is not None:
            mask = pd.to_numeric(series, errors="coerce") < constraint.min_value
            violation_count = int(mask.sum())
            if violation_count:
                rows.append(
                    {
                        "column": constraint.column,
                        "rule": f"min_value >= {constraint.min_value}",
                        "violation_count": violation_count,
                        "violation_percent": (
                            violation_count / row_count * 100 if row_count else 0.0
                        ),
                        "example_values": format_example_values(series[mask]),
                    }
                )

        if constraint.max_value is not None:
            mask = pd.to_numeric(series, errors="coerce") > constraint.max_value
            violation_count = int(mask.sum())
            if violation_count:
                rows.append(
                    {
                        "column": constraint.column,
                        "rule": f"max_value <= {constraint.max_value}",
                        "violation_count": violation_count,
                        "violation_percent": (
                            violation_count / row_count * 100 if row_count else 0.0
                        ),
                        "example_values": format_example_values(series[mask]),
                    }
                )

        if constraint.allowed_values is not None:
            allowed_values = set(constraint.allowed_values)
            mask = series.notna() & ~series.isin(allowed_values)
            violation_count = int(mask.sum())
            if violation_count:
                rows.append(
                    {
                        "column": constraint.column,
                        "rule": f"allowed_values in {constraint.allowed_values}",
                        "violation_count": violation_count,
                        "violation_percent": (
                            violation_count / row_count * 100 if row_count else 0.0
                        ),
                        "example_values": format_example_values(series[mask]),
                    }
                )

    return pd.DataFrame(rows, columns=columns)
