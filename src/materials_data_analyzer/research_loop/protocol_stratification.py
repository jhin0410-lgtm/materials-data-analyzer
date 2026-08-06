"""Battery-level exact-temperature stratification for the NASA research loop.

The analysis uses only explicit protocol metadata. It does not infer protocol
identity from battery names, filenames, row order, or rounded sensor values.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import kruskal

PRIMARY_PROTOCOL_FIELD = "ambient_temperature_median_c"
PRIMARY_RESPONSE_FIELD = "ridge_minus_persistence_mae"
MINIMUM_EVALUATED_BATTERIES_PER_GROUP = 5
SIGNIFICANCE_LEVEL = 0.05
MINIMUM_EPSILON_SQUARED = 0.10
_ALLOWED_OUTCOMES = {
    "protocol_effect_supported",
    "protocol_effect_not_supported",
    "protocol_metadata_insufficient",
    "protocol_groups_too_small",
}


def _require_columns(frame: pd.DataFrame, required: set[str], *, context: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{context} missing required columns: {', '.join(missing)}")


def _normalized_ids(frame: pd.DataFrame, *, context: str) -> pd.Series:
    _require_columns(frame, {"battery_id"}, context=context)
    if frame["battery_id"].isna().any():
        raise ValueError(f"{context} battery_id may not be missing")
    values = frame["battery_id"].astype(str).str.strip()
    if (values == "").any():
        raise ValueError(f"{context} battery_id may not be blank")
    return values


def _battery_errors(predictions: pd.DataFrame) -> pd.DataFrame:
    required = {
        "battery_id",
        "actual",
        "persistence_prediction",
        "ridge_prediction",
    }
    _require_columns(predictions, required, context="validation predictions")
    if predictions.empty:
        raise ValueError("validation predictions contain no exact-horizon rows")

    working = predictions[list(required)].copy()
    working["battery_id"] = _normalized_ids(
        working, context="validation predictions"
    )
    numeric = ("actual", "persistence_prediction", "ridge_prediction")
    for column in numeric:
        working[column] = pd.to_numeric(working[column], errors="coerce")
    if not np.isfinite(working[list(numeric)].to_numpy(dtype=float)).all():
        raise ValueError("validation predictions must contain finite numeric values")

    working["persistence_absolute_error"] = (
        working["actual"] - working["persistence_prediction"]
    ).abs()
    working["ridge_absolute_error"] = (
        working["actual"] - working["ridge_prediction"]
    ).abs()
    errors = (
        working.groupby("battery_id", sort=True)
        .agg(
            prediction_count=("actual", "size"),
            persistence_mae=("persistence_absolute_error", "mean"),
            ridge_mae=("ridge_absolute_error", "mean"),
        )
        .reset_index()
    )
    errors[PRIMARY_RESPONSE_FIELD] = errors["ridge_mae"] - errors["persistence_mae"]
    return errors


def _group_metrics(profile: pd.DataFrame) -> pd.DataFrame:
    columns = [
        PRIMARY_PROTOCOL_FIELD,
        "battery_count",
        "evaluated_battery_count",
        "prediction_count",
        "persistence_battery_macro_mae",
        "ridge_battery_macro_mae",
        "ridge_minus_persistence_mean_mae",
        "ridge_minus_persistence_median_mae",
        "minimum_required_evaluated_batteries",
        "eligible_for_primary_test",
    ]
    rows: list[dict[str, Any]] = []
    observed = profile[profile[PRIMARY_PROTOCOL_FIELD].notna()].copy()
    for value, group in observed.groupby(PRIMARY_PROTOCOL_FIELD, sort=True):
        evaluated = group[group["is_evaluated"]].copy()
        evaluated_count = int(len(evaluated))
        rows.append(
            {
                PRIMARY_PROTOCOL_FIELD: float(value),
                "battery_count": int(len(group)),
                "evaluated_battery_count": evaluated_count,
                "prediction_count": int(evaluated["prediction_count"].fillna(0).sum()),
                "persistence_battery_macro_mae": (
                    float(evaluated["persistence_mae"].mean())
                    if evaluated_count
                    else None
                ),
                "ridge_battery_macro_mae": (
                    float(evaluated["ridge_mae"].mean()) if evaluated_count else None
                ),
                "ridge_minus_persistence_mean_mae": (
                    float(evaluated[PRIMARY_RESPONSE_FIELD].mean())
                    if evaluated_count
                    else None
                ),
                "ridge_minus_persistence_median_mae": (
                    float(evaluated[PRIMARY_RESPONSE_FIELD].median())
                    if evaluated_count
                    else None
                ),
                "minimum_required_evaluated_batteries": (
                    MINIMUM_EVALUATED_BATTERIES_PER_GROUP
                ),
                "eligible_for_primary_test": (
                    evaluated_count >= MINIMUM_EVALUATED_BATTERIES_PER_GROUP
                ),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _primary_test(profile: pd.DataFrame) -> dict[str, float]:
    evaluated = profile[profile["is_evaluated"]].copy()
    samples = [
        group[PRIMARY_RESPONSE_FIELD].to_numpy(dtype=float)
        for _, group in evaluated.groupby(PRIMARY_PROTOCOL_FIELD, sort=True)
    ]
    combined = np.concatenate(samples)
    if np.ptp(combined) == 0:
        statistic = 0.0
        p_value = 1.0
    else:
        result = kruskal(*samples, nan_policy="raise")
        statistic = float(result.statistic)
        p_value = float(result.pvalue)
    group_count = len(samples)
    battery_count = len(combined)
    denominator = battery_count - group_count
    epsilon_squared = (
        max(0.0, float((statistic - group_count + 1) / denominator))
        if denominator > 0
        else 0.0
    )
    return {
        "kruskal_wallis_h": statistic,
        "kruskal_wallis_p_value": p_value,
        "epsilon_squared": epsilon_squared,
    }


def build_protocol_stratification(
    *,
    protocol_summary: pd.DataFrame,
    predictions: pd.DataFrame,
) -> dict[str, Any]:
    """Evaluate predeclared exact-temperature heterogeneity at battery level."""
    _require_columns(
        protocol_summary,
        {"battery_id", PRIMARY_PROTOCOL_FIELD},
        context="NASA protocol summary",
    )
    protocol = protocol_summary[["battery_id", PRIMARY_PROTOCOL_FIELD]].copy()
    protocol["battery_id"] = _normalized_ids(
        protocol, context="NASA protocol summary"
    )
    if protocol["battery_id"].duplicated().any():
        duplicates = sorted(
            protocol.loc[
                protocol["battery_id"].duplicated(keep=False), "battery_id"
            ].unique()
        )
        raise ValueError(
            "NASA protocol summary contains duplicate battery identifiers: "
            + ", ".join(duplicates)
        )
    protocol[PRIMARY_PROTOCOL_FIELD] = pd.to_numeric(
        protocol[PRIMARY_PROTOCOL_FIELD], errors="coerce"
    )
    protocol.loc[
        protocol[PRIMARY_PROTOCOL_FIELD].notna()
        & ~np.isfinite(protocol[PRIMARY_PROTOCOL_FIELD]),
        PRIMARY_PROTOCOL_FIELD,
    ] = np.nan

    errors = _battery_errors(predictions)
    unknown = sorted(set(errors["battery_id"]) - set(protocol["battery_id"]))
    if unknown:
        raise ValueError(
            "validation predictions contain batteries absent from NASA protocol "
            "summary: " + ", ".join(unknown)
        )

    profile = protocol.merge(
        errors,
        on="battery_id",
        how="left",
        validate="one_to_one",
    )
    profile["is_evaluated"] = profile["prediction_count"].notna()
    profile["prediction_count"] = profile["prediction_count"].fillna(0).astype(int)
    profile = profile.sort_values("battery_id", kind="mergesort").reset_index(drop=True)
    group_metrics = _group_metrics(profile)

    evaluated = profile[profile["is_evaluated"]].copy()
    missing_evaluated_metadata = int(
        evaluated[PRIMARY_PROTOCOL_FIELD].isna().sum()
    )
    distinct_groups = int(evaluated[PRIMARY_PROTOCOL_FIELD].nunique(dropna=True))
    smallest_group = (
        int(group_metrics["evaluated_battery_count"].min())
        if not group_metrics.empty
        else 0
    )

    test: dict[str, float | None] = {
        "kruskal_wallis_h": None,
        "kruskal_wallis_p_value": None,
        "epsilon_squared": None,
    }
    if missing_evaluated_metadata > 0 or distinct_groups < 2:
        outcome = "protocol_metadata_insufficient"
    elif smallest_group < MINIMUM_EVALUATED_BATTERIES_PER_GROUP:
        outcome = "protocol_groups_too_small"
    else:
        test = _primary_test(profile)
        supported = (
            float(test["kruskal_wallis_p_value"]) <= SIGNIFICANCE_LEVEL
            and float(test["epsilon_squared"]) >= MINIMUM_EPSILON_SQUARED
        )
        outcome = (
            "protocol_effect_supported"
            if supported
            else "protocol_effect_not_supported"
        )
    if outcome not in _ALLOWED_OUTCOMES:
        raise AssertionError(f"unhandled protocol outcome: {outcome}")

    summary = {
        "schema_version": "1.0",
        "outcome": outcome,
        "status": "Diagnostic",
        "protocol_field": PRIMARY_PROTOCOL_FIELD,
        "group_definition": (
            "Exact source-derived ambient_temperature_median_c values; no rounding, "
            "binning, filename inference, or battery-name inference."
        ),
        "response_field": PRIMARY_RESPONSE_FIELD,
        "protocol_battery_count": int(len(profile)),
        "evaluated_battery_count": int(len(evaluated)),
        "unevaluated_battery_count": int((~profile["is_evaluated"]).sum()),
        "missing_protocol_metadata_battery_count": int(
            profile[PRIMARY_PROTOCOL_FIELD].isna().sum()
        ),
        "missing_evaluated_protocol_metadata_battery_count": (
            missing_evaluated_metadata
        ),
        "exact_protocol_group_count": distinct_groups,
        "smallest_evaluated_protocol_group_count": smallest_group,
        "minimum_evaluated_batteries_per_group": (
            MINIMUM_EVALUATED_BATTERIES_PER_GROUP
        ),
        "primary_test": (
            "Kruskal-Wallis on battery-level Ridge-minus-persistence MAE"
        ),
        "significance_level": SIGNIFICANCE_LEVEL,
        "minimum_epsilon_squared": MINIMUM_EPSILON_SQUARED,
        **test,
        "evidence_interpretation": (
            "Supported means the single predeclared battery-level diagnostic met both "
            "the p-value and effect-size thresholds. It does not establish causality, "
            "protocol transferability, or predictive validity."
        ),
        "scientific_boundary": (
            "This is a post-hoc observational diagnostic. Every protocol battery and "
            "every exact-horizon prediction remains represented. Sparse or missing "
            "groups are reported as limitations rather than removed, pooled validation "
            "is not replaced, and the existing scientific evidence level is unchanged."
        ),
    }
    return {
        "battery_protocol_errors": profile,
        "protocol_group_metrics": group_metrics,
        "summary": summary,
    }
