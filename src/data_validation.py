"""Data-readiness validation summaries for tabular engineering datasets."""

from __future__ import annotations

import pandas as pd

from domain_constraints import DomainConstraint, validate_domain_constraints


def build_data_validation_report(
    df: pd.DataFrame, constraints: list[DomainConstraint] | None = None
) -> dict[str, object]:
    """Build a compact data-readiness report for one DataFrame."""
    missing_count_by_column = df.isna().sum()
    missing_percent_by_column = (
        missing_count_by_column / len(df) * 100 if len(df) else missing_count_by_column
    )

    return {
        "row_count": len(df),
        "column_count": len(df.columns),
        "duplicate_row_count": int(df.duplicated().sum()),
        "missing_count_by_column": missing_count_by_column,
        "missing_percent_by_column": missing_percent_by_column,
        "numeric_columns": df.select_dtypes(include="number").columns.tolist(),
        "categorical_columns": df.select_dtypes(
            include=["object", "string", "category"]
        ).columns.tolist(),
        "domain_constraint_violations": validate_domain_constraints(
            df=df, constraints=constraints
        ),
    }
