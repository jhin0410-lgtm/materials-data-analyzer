"""Readiness checks for process-quality and smart-factory tabular datasets.

This module does not train models, infer root causes, or call external systems.
It provides lightweight schema and validation-readiness diagnostics for future
manufacturing process-quality case studies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import pandas as pd


@dataclass(frozen=True)
class ProcessQualityReadinessConfig:
    """Column contract used by generic process-quality readiness checks."""

    required_columns: list[str]
    observation_timestamp_column: str | None = None
    quality_timestamp_column: str | None = None
    group_columns: list[str] | None = None
    target_columns: list[str] | None = None
    process_feature_columns: list[str] | None = None
    specification_limit_columns: list[str] | None = None
    forbidden_feature_columns: list[str] | None = None
    duplicate_key_columns: list[str] | None = None
    min_groups_for_group_split: int = 3
    min_rows_for_time_split: int = 20


def build_process_quality_readiness_report(
    df: pd.DataFrame,
    config: ProcessQualityReadinessConfig,
) -> dict[str, pd.DataFrame]:
    """Build a dictionary of CSV-friendly readiness tables."""
    return {
        "required_columns": check_required_columns(df, config.required_columns),
        "timestamp_parseability": summarize_timestamp_parseability(
            df,
            [
                config.observation_timestamp_column,
                config.quality_timestamp_column,
            ],
        ),
        "identifier_coverage": summarize_identifier_coverage(
            df,
            config.group_columns or [],
        ),
        "group_cardinality": summarize_group_cardinality(
            df,
            config.group_columns or [],
        ),
        "missingness": summarize_missingness(df),
        "duplicate_summary": summarize_duplicates(
            df,
            config.duplicate_key_columns,
        ),
        "target_availability": summarize_target_availability(
            df,
            config.target_columns or [],
        ),
        "class_balance": summarize_class_balance(
            df,
            config.target_columns or [],
        ),
        "delayed_target": summarize_delayed_target(
            df,
            config.observation_timestamp_column,
            config.quality_timestamp_column,
        ),
        "forbidden_features": check_forbidden_features(
            df,
            config.forbidden_feature_columns or [],
        ),
        "specification_limits": summarize_specification_limit_readiness(
            df,
            config.specification_limit_columns or [],
        ),
        "spc_readiness": evaluate_spc_readiness(df, config),
        "validation_readiness": evaluate_validation_readiness(df, config),
    }


def check_required_columns(
    df: pd.DataFrame,
    required_columns: Iterable[str],
) -> pd.DataFrame:
    """Check whether required columns are present."""
    rows = []
    for column in required_columns:
        rows.append(
            {
                "column": column,
                "present": column in df.columns,
                "status": "present" if column in df.columns else "missing",
            }
        )
    return pd.DataFrame(rows)


def summarize_timestamp_parseability(
    df: pd.DataFrame,
    timestamp_columns: Iterable[str | None],
) -> pd.DataFrame:
    """Summarize parseability and ordering of timestamp columns."""
    rows = []
    for column in [col for col in timestamp_columns if col]:
        if column not in df.columns:
            rows.append(
                {
                    "column": column,
                    "present": False,
                    "parseable_count": 0,
                    "parseable_percent": 0.0,
                    "monotonic_increasing": False,
                    "status": "missing",
                }
            )
            continue
        parsed = pd.to_datetime(df[column], errors="coerce")
        parseable = parsed.notna()
        rows.append(
            {
                "column": column,
                "present": True,
                "parseable_count": int(parseable.sum()),
                "parseable_percent": _percent(parseable.sum(), len(df)),
                "monotonic_increasing": bool(parsed.dropna().is_monotonic_increasing),
                "status": "parseable" if parseable.any() else "unparseable",
            }
        )
    return pd.DataFrame(rows)


def summarize_identifier_coverage(
    df: pd.DataFrame,
    identifier_columns: Iterable[str],
) -> pd.DataFrame:
    """Summarize non-null coverage for identifier/group columns."""
    rows = []
    for column in identifier_columns:
        if column not in df.columns:
            rows.append(
                {
                    "column": column,
                    "present": False,
                    "non_null_count": 0,
                    "coverage_percent": 0.0,
                    "status": "missing",
                }
            )
            continue
        non_null = df[column].notna()
        rows.append(
            {
                "column": column,
                "present": True,
                "non_null_count": int(non_null.sum()),
                "coverage_percent": _percent(non_null.sum(), len(df)),
                "status": "usable" if non_null.any() else "empty",
            }
        )
    return pd.DataFrame(rows)


def summarize_group_cardinality(
    df: pd.DataFrame,
    group_columns: Iterable[str],
) -> pd.DataFrame:
    """Summarize group cardinality and approximate group split readiness."""
    rows = []
    for column in group_columns:
        if column not in df.columns:
            rows.append(
                {
                    "column": column,
                    "present": False,
                    "unique_count": 0,
                    "min_group_size": 0,
                    "median_group_size": 0,
                    "max_group_size": 0,
                    "status": "missing",
                }
            )
            continue
        counts = df[column].value_counts(dropna=True)
        rows.append(
            {
                "column": column,
                "present": True,
                "unique_count": int(counts.size),
                "min_group_size": int(counts.min()) if not counts.empty else 0,
                "median_group_size": float(counts.median()) if not counts.empty else 0.0,
                "max_group_size": int(counts.max()) if not counts.empty else 0,
                "status": "ready" if counts.size >= 3 else "limited",
            }
        )
    return pd.DataFrame(rows)


def summarize_missingness(df: pd.DataFrame) -> pd.DataFrame:
    """Summarize missing values by column."""
    rows = []
    for column in df.columns:
        missing = int(df[column].isna().sum())
        rows.append(
            {
                "column": column,
                "missing_count": missing,
                "missing_percent": _percent(missing, len(df)),
                "dtype": str(df[column].dtype),
            }
        )
    return pd.DataFrame(rows)


def summarize_duplicates(
    df: pd.DataFrame,
    key_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Summarize exact-row and optional key-based duplicates."""
    exact_count = int(df.duplicated().sum())
    rows = [
        {
            "duplicate_type": "exact_row",
            "columns": "*",
            "duplicate_count": exact_count,
            "duplicate_percent": _percent(exact_count, len(df)),
            "status": "duplicates_present" if exact_count else "none",
        }
    ]
    if key_columns:
        missing = [column for column in key_columns if column not in df.columns]
        if missing:
            rows.append(
                {
                    "duplicate_type": "key",
                    "columns": ",".join(key_columns),
                    "duplicate_count": 0,
                    "duplicate_percent": 0.0,
                    "status": "missing_key_columns:" + ",".join(missing),
                }
            )
        else:
            key_count = int(df.duplicated(subset=key_columns).sum())
            rows.append(
                {
                    "duplicate_type": "key",
                    "columns": ",".join(key_columns),
                    "duplicate_count": key_count,
                    "duplicate_percent": _percent(key_count, len(df)),
                    "status": "duplicates_present" if key_count else "none",
                }
            )
    return pd.DataFrame(rows)


def summarize_target_availability(
    df: pd.DataFrame,
    target_columns: Iterable[str],
) -> pd.DataFrame:
    """Summarize target non-null availability."""
    rows = []
    for column in target_columns:
        if column not in df.columns:
            rows.append(
                {
                    "target_column": column,
                    "present": False,
                    "non_null_count": 0,
                    "coverage_percent": 0.0,
                    "status": "missing",
                }
            )
            continue
        non_null = df[column].notna()
        rows.append(
            {
                "target_column": column,
                "present": True,
                "non_null_count": int(non_null.sum()),
                "coverage_percent": _percent(non_null.sum(), len(df)),
                "status": "available" if non_null.any() else "empty",
            }
        )
    return pd.DataFrame(rows)


def summarize_class_balance(
    df: pd.DataFrame,
    target_columns: Iterable[str],
) -> pd.DataFrame:
    """Summarize class balance for low-cardinality targets."""
    rows = []
    for column in target_columns:
        if column not in df.columns:
            continue
        values = df[column].dropna()
        unique_count = int(values.nunique())
        if unique_count > 20:
            rows.append(
                {
                    "target_column": column,
                    "class_value": "<continuous_or_high_cardinality>",
                    "count": int(values.size),
                    "percent": 100.0 if values.size else 0.0,
                    "status": "not_class_target",
                }
            )
            continue
        counts = values.value_counts(dropna=False)
        for value, count in counts.items():
            rows.append(
                {
                    "target_column": column,
                    "class_value": str(value),
                    "count": int(count),
                    "percent": _percent(count, len(values)),
                    "status": "minority_class"
                    if len(values) and count / len(values) < 0.1
                    else "observed",
                }
            )
    return pd.DataFrame(rows)


def summarize_delayed_target(
    df: pd.DataFrame,
    observation_timestamp_column: str | None,
    quality_timestamp_column: str | None,
) -> pd.DataFrame:
    """Check whether quality timestamps occur after observations."""
    if not observation_timestamp_column or not quality_timestamp_column:
        return pd.DataFrame(
            [
                {
                    "check": "delayed_target",
                    "status": "not_configured",
                    "violation_count": 0,
                    "message": "observation or quality timestamp column not configured",
                }
            ]
        )
    if observation_timestamp_column not in df.columns or quality_timestamp_column not in df.columns:
        return pd.DataFrame(
            [
                {
                    "check": "delayed_target",
                    "status": "missing_timestamp_column",
                    "violation_count": 0,
                    "message": "observation or quality timestamp column missing",
                }
            ]
        )
    observation = pd.to_datetime(df[observation_timestamp_column], errors="coerce")
    quality = pd.to_datetime(df[quality_timestamp_column], errors="coerce")
    comparable = observation.notna() & quality.notna()
    violation = comparable & (quality < observation)
    return pd.DataFrame(
        [
            {
                "check": "delayed_target",
                "status": "valid_order" if not violation.any() else "target_precedes_observation",
                "violation_count": int(violation.sum()),
                "message": "quality timestamp should be at or after observation timestamp",
            }
        ]
    )


def check_forbidden_features(
    df: pd.DataFrame,
    forbidden_feature_columns: Iterable[str],
) -> pd.DataFrame:
    """Check whether post-outcome/leakage columns are present as candidate features."""
    rows = []
    for column in forbidden_feature_columns:
        rows.append(
            {
                "column": column,
                "present": column in df.columns,
                "risk": "forbidden_present" if column in df.columns else "not_present",
            }
        )
    return pd.DataFrame(rows)


def summarize_specification_limit_readiness(
    df: pd.DataFrame,
    specification_limit_columns: Iterable[str],
) -> pd.DataFrame:
    """Summarize whether specification-limit columns exist for capability checks."""
    columns = list(specification_limit_columns)
    if not columns:
        return pd.DataFrame(
            [
                {
                    "requirement": "specification_limits",
                    "configured_columns": "",
                    "available_count": 0,
                    "status": "not_configured",
                }
            ]
        )
    available = [column for column in columns if column in df.columns]
    return pd.DataFrame(
        [
            {
                "requirement": "specification_limits",
                "configured_columns": ",".join(columns),
                "available_count": len(available),
                "status": "ready" if len(available) == len(columns) else "limited",
            }
        ]
    )


def evaluate_spc_readiness(
    df: pd.DataFrame,
    config: ProcessQualityReadinessConfig,
) -> pd.DataFrame:
    """Evaluate basic SPC readiness without calculating control limits."""
    process_features = [col for col in (config.process_feature_columns or []) if col in df.columns]
    timestamp_ready = _timestamp_ready(df, config.observation_timestamp_column)
    has_numeric = any(pd.api.types.is_numeric_dtype(df[col]) for col in process_features)
    has_subgroups = any(
        col in df.columns and df[col].nunique(dropna=True) >= 2
        for col in (config.group_columns or [])
    )
    return pd.DataFrame(
        [
            {
                "analysis": "individuals_moving_range",
                "ready": bool(timestamp_ready and has_numeric),
                "reason": "requires ordered observations and numeric process variable",
            },
            {
                "analysis": "xbar_r_or_xbar_s",
                "ready": bool(timestamp_ready and has_numeric and has_subgroups),
                "reason": "requires ordered observations, numeric process variable, and rational subgroup",
            },
            {
                "analysis": "process_capability",
                "ready": bool(has_numeric and config.specification_limit_columns),
                "reason": "requires numeric target/process measure plus externally provided specification limits",
            },
        ]
    )


def evaluate_validation_readiness(
    df: pd.DataFrame,
    config: ProcessQualityReadinessConfig,
) -> pd.DataFrame:
    """Evaluate group/time validation readiness at a high level."""
    rows = []
    for column in config.group_columns or []:
        unique_count = df[column].nunique(dropna=True) if column in df.columns else 0
        rows.append(
            {
                "validation_type": f"group_split_by_{column}",
                "ready": bool(unique_count >= config.min_groups_for_group_split),
                "basis": f"unique groups={unique_count}; minimum={config.min_groups_for_group_split}",
            }
        )
    timestamp_ready = _timestamp_ready(df, config.observation_timestamp_column)
    rows.append(
        {
            "validation_type": "forward_time_split",
            "ready": bool(timestamp_ready and len(df) >= config.min_rows_for_time_split),
            "basis": (
                f"timestamp_ready={timestamp_ready}; rows={len(df)}; "
                f"minimum_rows={config.min_rows_for_time_split}"
            ),
        }
    )
    return pd.DataFrame(rows)


def _timestamp_ready(df: pd.DataFrame, column: str | None) -> bool:
    if not column or column not in df.columns:
        return False
    parsed = pd.to_datetime(df[column], errors="coerce")
    return bool(parsed.notna().any() and parsed.dropna().is_monotonic_increasing)


def _percent(count: int | float, total: int | float) -> float:
    return float(count / total * 100.0) if total else 0.0
