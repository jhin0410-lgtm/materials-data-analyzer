"""Leakage-safe warm-start cross-battery forecasting benchmark.

The benchmark predicts capacity retention at an exact future cycle from
observations available no later than the prediction origin. Battery identity
is held out from model fitting, while each held-out battery may contribute its
own observed pre-origin history. This is not a zero-shot or lifetime model.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


BENCHMARK_VERSION = "2.6.1"
BENCHMARK_ID = "battery_warm_start_cross_battery_forecast_v1"
DEFAULT_CONFIG_PATH = "configs/examples/battery_generalization_forecast.json"
DEFAULT_OUTPUT_ROOT = "outputs/v2_6_battery_generalization"
TRACKED_SUMMARY_PATH = (
    "data/processed/battery_v2_6_1_generalization_forecast_summary.json"
)

EVALUATION_SCENARIO = "warm_start_cross_battery"
ALLOWED_MODELS = ("persistence", "ridge")
CONFIG_FIELDS = {
    "schema_version",
    "benchmark_id",
    "case_study_id",
    "input_path",
    "source_lineage_path",
    "group_column",
    "time_column",
    "target_column",
    "target_unit",
    "horizon",
    "lags",
    "rolling_window",
    "minimum_history",
    "split_method",
    "n_splits",
    "random_seed",
    "models",
    "ridge_alpha",
    "plausibility_min",
    "plausibility_max",
    "large_change_threshold",
    "duplicate_cycle_policy",
    "unordered_cycle_policy",
    "credential_policy",
    "output_root",
    "output_policy",
}
SECRET_KEY_FRAGMENTS = (
    "api_key",
    "authorization",
    "access_token",
    "password",
    "credential",
    "secret",
)
SECRET_VALUE_PATTERNS = (
    re.compile(r"(?i)\b(?:sk|ghp|github_pat)-?[A-Za-z0-9_]{12,}\b"),
    re.compile(r"(?i)\bAKIA[0-9A-Z]{12,}\b"),
    re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|password)\s*[:=]"),
)
SAFE_SECURITY_EVIDENCE_FIELDS = {
    "credentials_read",
    "network_called",
    "source_mutation_performed",
}
SAFE_COLUMN_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value) if math.isfinite(float(value)) else None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n"


def canonical_checksum(payload: Any) -> str:
    encoded = json.dumps(
        _json_safe(payload),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_absolute_or_drive_qualified(path: str | Path) -> bool:
    normalized = str(path).replace("\\", "/")
    windows_path = PureWindowsPath(normalized)
    return (
        normalized.startswith("/")
        or Path(normalized).is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
    )


def resolve_repo_path(repo_root: str | Path, relative_path: str | Path) -> Path:
    root = Path(repo_root).resolve()
    candidate = Path(str(relative_path).replace("\\", "/"))
    if _is_absolute_or_drive_qualified(relative_path) or ".." in candidate.parts:
        raise ValueError("paths must be repository-relative and non-traversing")
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError("path escapes repository root") from None
    return target


def _scan_for_secrets(value: Any, *, key_path: str = "config") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered == "credential_policy":
                if item != {
                    "store_credentials": False,
                    "network_access_required": False,
                }:
                    raise ValueError(
                        f"credential policy must disable storage and network: {key_path}.{key}"
                    )
                continue
            safe_evidence = (
                lowered in SAFE_SECURITY_EVIDENCE_FIELDS
                and isinstance(item, bool)
                and item is False
            )
            if (
                not safe_evidence
                and any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS)
            ):
                raise ValueError(f"secret-like field is prohibited: {key_path}.{key}")
            _scan_for_secrets(item, key_path=f"{key_path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _scan_for_secrets(item, key_path=f"{key_path}[{index}]")
        return
    if isinstance(value, str) and any(
        pattern.search(value) for pattern in SECRET_VALUE_PATTERNS
    ):
        raise ValueError(f"secret-like value is prohibited: {key_path}")


@dataclass(frozen=True)
class BatteryForecastConfig:
    schema_version: str
    benchmark_id: str
    case_study_id: str
    input_path: str
    source_lineage_path: str
    group_column: str
    time_column: str
    target_column: str
    target_unit: str
    horizon: int
    lags: tuple[int, ...]
    rolling_window: int
    minimum_history: int
    split_method: str
    n_splits: int
    random_seed: int
    models: tuple[str, ...]
    ridge_alpha: float
    plausibility_min: float
    plausibility_max: float
    large_change_threshold: float
    duplicate_cycle_policy: str
    unordered_cycle_policy: str
    credential_policy: Mapping[str, bool]
    output_root: str
    output_policy: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "BatteryForecastConfig":
        unknown = sorted(set(payload) - CONFIG_FIELDS)
        missing = sorted(CONFIG_FIELDS - set(payload))
        if unknown:
            raise ValueError("unknown config field(s): " + ", ".join(unknown))
        if missing:
            raise ValueError("missing config field(s): " + ", ".join(missing))
        _scan_for_secrets(payload)

        for path_field in ("input_path", "source_lineage_path", "output_root"):
            value = str(payload[path_field])
            if _is_absolute_or_drive_qualified(value) or ".." in Path(
                value.replace("\\", "/")
            ).parts:
                raise ValueError(
                    f"{path_field} must be repository-relative and non-traversing"
                )
        output_root = Path(str(payload["output_root"]).replace("\\", "/")).as_posix()
        if output_root != DEFAULT_OUTPUT_ROOT:
            raise ValueError(
                f"output_root must be the local-only path {DEFAULT_OUTPUT_ROOT}"
            )

        for column_field in ("group_column", "time_column", "target_column"):
            if not SAFE_COLUMN_PATTERN.fullmatch(str(payload[column_field])):
                raise ValueError(f"{column_field} must be a simple column identifier")

        lags = tuple(int(value) for value in payload["lags"])
        if not lags or lags != tuple(sorted(set(lags))) or any(value <= 0 for value in lags):
            raise ValueError("lags must be unique positive integers in ascending order")
        models = tuple(str(value) for value in payload["models"])
        if models != ALLOWED_MODELS:
            raise ValueError(
                "models must be the fixed ordered baselines: persistence, ridge"
            )

        config = cls(
            schema_version=str(payload["schema_version"]),
            benchmark_id=str(payload["benchmark_id"]),
            case_study_id=str(payload["case_study_id"]),
            input_path=str(payload["input_path"]).replace("\\", "/"),
            source_lineage_path=str(payload["source_lineage_path"]).replace("\\", "/"),
            group_column=str(payload["group_column"]),
            time_column=str(payload["time_column"]),
            target_column=str(payload["target_column"]),
            target_unit=str(payload["target_unit"]),
            horizon=int(payload["horizon"]),
            lags=lags,
            rolling_window=int(payload["rolling_window"]),
            minimum_history=int(payload["minimum_history"]),
            split_method=str(payload["split_method"]),
            n_splits=int(payload["n_splits"]),
            random_seed=int(payload["random_seed"]),
            models=models,
            ridge_alpha=float(payload["ridge_alpha"]),
            plausibility_min=float(payload["plausibility_min"]),
            plausibility_max=float(payload["plausibility_max"]),
            large_change_threshold=float(payload["large_change_threshold"]),
            duplicate_cycle_policy=str(payload["duplicate_cycle_policy"]),
            unordered_cycle_policy=str(payload["unordered_cycle_policy"]),
            credential_policy=dict(payload["credential_policy"]),
            output_root=output_root,
            output_policy=str(payload["output_policy"]),
        )
        config._validate()
        return config

    def _validate(self) -> None:
        if self.schema_version != BENCHMARK_VERSION:
            raise ValueError(f"schema_version must be {BENCHMARK_VERSION}")
        if self.benchmark_id != BENCHMARK_ID:
            raise ValueError(f"benchmark_id must be {BENCHMARK_ID}")
        if self.case_study_id != "kaggle_battery":
            raise ValueError("case_study_id must be kaggle_battery")
        if self.horizon <= 0 or self.horizon > 100:
            raise ValueError("horizon must be in the bounded range 1..100")
        if self.rolling_window < 2 or self.rolling_window > 100:
            raise ValueError("rolling_window must be in the bounded range 2..100")
        if self.minimum_history < max(self.lags) + 1:
            raise ValueError("minimum_history must exceed the largest lag")
        if self.minimum_history < self.rolling_window:
            raise ValueError("minimum_history must cover the rolling window")
        if self.split_method != "group_kfold":
            raise ValueError("split_method must be group_kfold")
        if self.n_splits < 2 or self.n_splits > 20:
            raise ValueError("n_splits must be in the bounded range 2..20")
        if not math.isfinite(self.ridge_alpha) or self.ridge_alpha <= 0:
            raise ValueError("ridge_alpha must be finite and positive")
        if (
            not math.isfinite(self.plausibility_min)
            or not math.isfinite(self.plausibility_max)
            or self.plausibility_min >= self.plausibility_max
        ):
            raise ValueError("plausibility bounds must be finite and increasing")
        if not math.isfinite(self.large_change_threshold) or self.large_change_threshold <= 0:
            raise ValueError("large_change_threshold must be finite and positive")
        if self.duplicate_cycle_policy != "reject_trajectory":
            raise ValueError("duplicate_cycle_policy must be reject_trajectory")
        if self.unordered_cycle_policy != "stable_sort_with_audit":
            raise ValueError(
                "unordered_cycle_policy must be stable_sort_with_audit"
            )
        if self.credential_policy != {
            "store_credentials": False,
            "network_access_required": False,
        }:
            raise ValueError("credential_policy must disable storage and network access")
        if self.output_policy != "local_details_and_tracked_compact_summary":
            raise ValueError(
                "output_policy must be local_details_and_tracked_compact_summary"
            )

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(self.__dict__)


def load_config(
    path: str | Path = DEFAULT_CONFIG_PATH,
    repo_root: str | Path = ".",
) -> BatteryForecastConfig:
    config_path = resolve_repo_path(repo_root, path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("forecast config must be a JSON object")
    return BatteryForecastConfig.from_mapping(payload)


def _group_reference(group_id: Any) -> str:
    digest = hashlib.sha256(f"battery-group:{group_id}".encode("utf-8")).hexdigest()
    return f"battery_ref_{digest[:12]}"


def _finite_numeric(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.where(np.isfinite(numeric), np.nan)


def assess_data_readiness(
    frame: pd.DataFrame,
    config: BatteryForecastConfig,
    *,
    source_sha256: str | None = None,
) -> dict[str, Any]:
    required = [config.group_column, config.time_column, config.target_column]
    missing_columns = [column for column in required if column not in frame.columns]
    fatal_errors: list[str] = []
    warnings: list[str] = []
    if missing_columns:
        fatal_errors.append("missing required columns: " + ", ".join(missing_columns))
        return {
            "schema_version": BENCHMARK_VERSION,
            "status": "blocked_by_data_readiness",
            "fatal_errors": fatal_errors,
            "warnings": warnings,
            "source_sha256": source_sha256,
            "source_rows": len(frame),
        }

    groups = frame[config.group_column]
    blank_groups = groups.isna() | groups.astype(str).str.strip().eq("")
    times = _finite_numeric(frame[config.time_column])
    targets = _finite_numeric(frame[config.target_column])
    non_integer_times = times.notna() & ~np.isclose(times, np.round(times))
    duplicate_rows = int(
        frame.loc[~blank_groups & times.notna()]
        .assign(__forecast_time=times[times.notna()])
        .duplicated([config.group_column, "__forecast_time"])
        .sum()
    )
    group_count = int(groups.loc[~blank_groups].nunique())
    inversions = 0
    trajectory_lengths: list[int] = []
    for _, group_frame in frame.loc[~blank_groups & times.notna()].groupby(
        config.group_column,
        sort=True,
    ):
        values = _finite_numeric(group_frame[config.time_column]).to_numpy()
        inversions += int(np.sum(np.diff(values) <= 0))
        trajectory_lengths.append(len(group_frame))

    if int(blank_groups.sum()):
        fatal_errors.append("invalid or blank group identifiers are present")
    if int(times.isna().sum()):
        fatal_errors.append("cycle/time values must be finite numeric values")
    if int(non_integer_times.sum()):
        fatal_errors.append("cycle/time values must be integer-valued")
    if duplicate_rows:
        fatal_errors.append("duplicate battery/cycle rows are prohibited")
    if group_count < 3:
        fatal_errors.append("at least three independent battery trajectories are required")
    if int(targets.isna().sum()):
        warnings.append("missing or non-finite targets will be excluded with reasons")
    if inversions:
        warnings.append("source-order inversions will be stable-sorted and audited")
    if trajectory_lengths and min(trajectory_lengths) < config.minimum_history + config.horizon:
        warnings.append("short trajectories may not provide eligible forecast origins")
    if int((targets < config.plausibility_min).fillna(False).sum()) or int(
        (targets > config.plausibility_max).fillna(False).sum()
    ):
        warnings.append(
            "observed targets outside configured plausibility bounds require audit"
        )

    status = "blocked_by_data_readiness" if fatal_errors else (
        "ready_with_restrictions" if warnings else "ready"
    )
    return {
        "schema_version": BENCHMARK_VERSION,
        "status": status,
        "source_sha256": source_sha256,
        "source_rows": len(frame),
        "trajectory_count": group_count,
        "trajectory_length_min": min(trajectory_lengths) if trajectory_lengths else 0,
        "trajectory_length_median": (
            float(np.median(trajectory_lengths)) if trajectory_lengths else 0.0
        ),
        "trajectory_length_max": max(trajectory_lengths) if trajectory_lengths else 0,
        "missing_target_rows": int(targets.isna().sum()),
        "duplicate_group_time_rows": duplicate_rows,
        "source_order_inversion_count": inversions,
        "observed_target_min": (
            float(targets.min()) if targets.notna().any() else None
        ),
        "observed_target_max": (
            float(targets.max()) if targets.notna().any() else None
        ),
        "fatal_errors": fatal_errors,
        "warnings": warnings,
        "network_called": False,
        "credentials_read": False,
    }


def _slope(times: Sequence[float], values: Sequence[float]) -> float:
    x = np.asarray(times, dtype=float)
    y = np.asarray(values, dtype=float)
    centered = x - np.mean(x)
    denominator = float(np.dot(centered, centered))
    if len(x) < 2 or denominator <= 0:
        return 0.0
    return float(np.dot(centered, y - np.mean(y)) / denominator)


def feature_columns(config: BatteryForecastConfig) -> list[str]:
    columns = ["capacity_current"]
    columns.extend(f"capacity_lag_{lag}" for lag in config.lags)
    columns.extend(
        [
            f"capacity_rolling_mean_{config.rolling_window}",
            f"capacity_rolling_std_{config.rolling_window}",
            f"capacity_recent_slope_{config.rolling_window}",
            "current_cycle_index",
        ]
    )
    return columns


def build_lagged_forecast_frame(
    source: pd.DataFrame,
    config: BatteryForecastConfig,
) -> tuple[pd.DataFrame, dict[str, int]]:
    readiness = assess_data_readiness(source, config)
    if readiness["status"] == "blocked_by_data_readiness":
        raise ValueError("; ".join(readiness["fatal_errors"]))

    working = source.copy(deep=True)
    working["__forecast_source_row"] = np.arange(len(working), dtype=int)
    working["__forecast_time"] = _finite_numeric(working[config.time_column])
    working["__forecast_target"] = _finite_numeric(working[config.target_column])
    working = working.sort_values(
        [config.group_column, "__forecast_time", "__forecast_source_row"],
        kind="mergesort",
    )

    exclusions = {
        "missing_current_target": 0,
        "horizon_target_unavailable": 0,
        "missing_required_lag": 0,
        "insufficient_history": 0,
    }
    records: list[dict[str, Any]] = []
    for group_id, group_frame in working.groupby(config.group_column, sort=True):
        group_frame = group_frame.reset_index(drop=True)
        times = group_frame["__forecast_time"].astype(int).tolist()
        values = group_frame["__forecast_target"].tolist()
        target_by_time = dict(zip(times, values, strict=True))

        for position, row in group_frame.iterrows():
            origin = int(row["__forecast_time"])
            current = row["__forecast_target"]
            if pd.isna(current):
                exclusions["missing_current_target"] += 1
                continue
            future = target_by_time.get(origin + config.horizon)
            if future is None or pd.isna(future):
                exclusions["horizon_target_unavailable"] += 1
                continue
            lag_values = [
                target_by_time.get(origin - lag)
                for lag in config.lags
            ]
            if any(value is None or pd.isna(value) for value in lag_values):
                exclusions["missing_required_lag"] += 1
                continue
            history = group_frame.iloc[: position + 1]
            history = history.loc[history["__forecast_target"].notna()]
            if len(history) < config.minimum_history:
                exclusions["insufficient_history"] += 1
                continue
            rolling = history.tail(config.rolling_window)
            rolling_values = rolling["__forecast_target"].astype(float).to_numpy()
            rolling_times = rolling["__forecast_time"].astype(float).to_numpy()

            record = {
                config.group_column: str(group_id),
                "group_reference": _group_reference(group_id),
                "source_row_index": int(row["__forecast_source_row"]),
                "prediction_origin": origin,
                "forecast_target_cycle": origin + config.horizon,
                "feature_cutoff_cycle": origin,
                "forecast_target": float(future),
                "capacity_current": float(current),
                f"capacity_rolling_mean_{config.rolling_window}": float(
                    np.mean(rolling_values)
                ),
                f"capacity_rolling_std_{config.rolling_window}": float(
                    np.std(rolling_values, ddof=0)
                ),
                f"capacity_recent_slope_{config.rolling_window}": _slope(
                    rolling_times,
                    rolling_values,
                ),
                "current_cycle_index": float(origin),
            }
            for lag, value in zip(config.lags, lag_values, strict=True):
                record[f"capacity_lag_{lag}"] = float(value)
            records.append(record)

    result = pd.DataFrame(records)
    ordered_columns = [
        config.group_column,
        "group_reference",
        "source_row_index",
        "prediction_origin",
        "forecast_target_cycle",
        "feature_cutoff_cycle",
        "forecast_target",
        *feature_columns(config),
    ]
    if result.empty:
        return pd.DataFrame(columns=ordered_columns), exclusions
    result = result[ordered_columns].sort_values(
        [config.group_column, "prediction_origin"],
        kind="mergesort",
    )
    result = result.reset_index(drop=True)
    return result, exclusions


def _metric_values(actual: np.ndarray, predicted: np.ndarray) -> dict[str, Any]:
    residual = predicted - actual
    mae = float(np.mean(np.abs(residual)))
    rmse = float(np.sqrt(np.mean(np.square(residual))))
    if len(actual) < 2 or float(np.var(actual)) <= 0:
        r2 = None
    else:
        r2 = float(1.0 - np.sum(np.square(residual)) / np.sum(np.square(actual - np.mean(actual))))
    return {"mae": mae, "rmse": rmse, "r2": r2}


def _fit_ridge(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    config: BatteryForecastConfig,
) -> Any:
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    model = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("regressor", Ridge(alpha=config.ridge_alpha)),
        ]
    )
    model.fit(x_train, y_train)
    return model


def build_group_splits(
    forecast_frame: pd.DataFrame,
    config: BatteryForecastConfig,
) -> list[dict[str, Any]]:
    from sklearn.model_selection import GroupKFold

    group_count = int(forecast_frame[config.group_column].nunique())
    if group_count < 2:
        raise ValueError("at least two evaluable groups are required")
    n_splits = min(config.n_splits, group_count)
    splitter = GroupKFold(n_splits=n_splits)
    groups = forecast_frame[config.group_column].astype(str)
    splits: list[dict[str, Any]] = []
    for fold_index, (train_index, test_index) in enumerate(
        splitter.split(forecast_frame, groups=groups),
        start=1,
    ):
        train_groups = sorted(set(groups.iloc[train_index]))
        test_groups = sorted(set(groups.iloc[test_index]))
        overlap = sorted(set(train_groups).intersection(test_groups))
        splits.append(
            {
                "fold_id": f"group_fold_{fold_index:02d}",
                "train_index": np.asarray(train_index, dtype=int),
                "test_index": np.asarray(test_index, dtype=int),
                "train_group_count": len(train_groups),
                "test_group_count": len(test_groups),
                "train_group_references": [
                    _group_reference(value) for value in train_groups
                ],
                "test_group_references": [
                    _group_reference(value) for value in test_groups
                ],
                "group_overlap_count": len(overlap),
                "train_rows": len(train_index),
                "test_rows": len(test_index),
            }
        )
    return splits


def _aggregate_metrics(
    predictions: pd.DataFrame,
    config: BatteryForecastConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    per_group: list[dict[str, Any]] = []
    for (model, group_reference), rows in predictions.groupby(
        ["model", "group_reference"],
        sort=True,
    ):
        metrics = _metric_values(
            rows["actual"].to_numpy(dtype=float),
            rows["prediction_raw"].to_numpy(dtype=float),
        )
        per_group.append(
            {
                "model": model,
                "group_reference": group_reference,
                "prediction_count": len(rows),
                **metrics,
            }
        )

    per_group_frame = pd.DataFrame(per_group)
    aggregate: list[dict[str, Any]] = []
    for model, rows in predictions.groupby("model", sort=True):
        metrics = _metric_values(
            rows["actual"].to_numpy(dtype=float),
            rows["prediction_raw"].to_numpy(dtype=float),
        )
        group_rows = per_group_frame.loc[per_group_frame["model"] == model]
        aggregate.append(
            {
                "model": model,
                "prediction_count": len(rows),
                "evaluated_group_count": int(rows["group_reference"].nunique()),
                **metrics,
                "battery_mae_mean": float(group_rows["mae"].mean()),
                "battery_mae_median": float(group_rows["mae"].median()),
                "battery_mae_max": float(group_rows["mae"].max()),
            }
        )
    return aggregate, per_group


def _physical_plausibility(
    predictions: pd.DataFrame,
    config: BatteryForecastConfig,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model, model_rows in predictions.groupby("model", sort=True):
        predicted = model_rows["prediction_raw"].to_numpy(dtype=float)
        current = model_rows["capacity_current"].to_numpy(dtype=float)
        rows.append(
            {
                "model": model,
                "prediction_count": len(model_rows),
                "non_finite_prediction_count": int((~np.isfinite(predicted)).sum()),
                "negative_prediction_count": int((predicted < 0).sum()),
                "outside_plausibility_bounds_count": int(
                    (
                        (predicted < config.plausibility_min)
                        | (predicted > config.plausibility_max)
                    ).sum()
                ),
                "large_origin_change_count": int(
                    (np.abs(predicted - current) > config.large_change_threshold).sum()
                ),
                "outside_training_target_range_count": int(
                    model_rows["outside_training_target_range"].sum()
                ),
                "prediction_clipping_performed": False,
            }
        )
    return rows


def evaluate_forecast_frame(
    forecast_frame: pd.DataFrame,
    config: BatteryForecastConfig,
) -> dict[str, Any]:
    features = feature_columns(config)
    if forecast_frame.empty:
        raise ValueError("no eligible forecast rows")
    if any(column not in forecast_frame.columns for column in features):
        raise ValueError("forecast frame is missing registered feature columns")
    if any(
        token in column.lower()
        for column in features
        for token in ("future", "target_future", "final", "eol", "lifetime")
    ):
        raise ValueError("future-derived or lifetime feature is prohibited")
    if "forecast_target" in features:
        raise ValueError("forecast target cannot be used as a feature")

    splits = build_group_splits(forecast_frame, config)
    prediction_rows: list[dict[str, Any]] = []
    preprocessing_rows: list[dict[str, Any]] = []
    for split in splits:
        train = forecast_frame.iloc[split["train_index"]]
        test = forecast_frame.iloc[split["test_index"]]
        if split["group_overlap_count"]:
            raise ValueError("train/test battery overlap detected")
        x_train = train[features]
        x_test = test[features]
        y_train = train["forecast_target"].astype(float)
        y_test = test["forecast_target"].astype(float)
        train_min = float(y_train.min())
        train_max = float(y_train.max())

        model_predictions = {
            "persistence": test["capacity_current"].to_numpy(dtype=float),
        }
        ridge = _fit_ridge(x_train, y_train, config)
        model_predictions["ridge"] = np.asarray(
            ridge.predict(x_test),
            dtype=float,
        )
        imputer = ridge.named_steps["imputer"]
        scaler = ridge.named_steps["scaler"]
        preprocessing_rows.append(
            {
                "fold_id": split["fold_id"],
                "model": "ridge",
                "fit_scope": "training_partition_only",
                "fit_row_count": len(train),
                "test_row_count": len(test),
                "imputer_statistics_checksum": canonical_checksum(
                    np.asarray(imputer.statistics_, dtype=float).tolist()
                ),
                "scaler_mean_checksum": canonical_checksum(
                    np.asarray(scaler.mean_, dtype=float).tolist()
                ),
            }
        )

        for model in config.models:
            predicted = model_predictions[model]
            if not np.isfinite(predicted).all():
                raise ValueError(f"{model} produced non-finite predictions")
            for position, (_, row) in enumerate(test.iterrows()):
                value = float(predicted[position])
                prediction_rows.append(
                    {
                        "fold_id": split["fold_id"],
                        "model": model,
                        config.group_column: row[config.group_column],
                        "group_reference": row["group_reference"],
                        "prediction_origin": int(row["prediction_origin"]),
                        "forecast_target_cycle": int(row["forecast_target_cycle"]),
                        "feature_cutoff_cycle": int(row["feature_cutoff_cycle"]),
                        "actual": float(y_test.iloc[position]),
                        "capacity_current": float(row["capacity_current"]),
                        "prediction_raw": value,
                        "prediction_clipped": None,
                        "outside_training_target_range": bool(
                            value < train_min or value > train_max
                        ),
                    }
                )

    predictions = pd.DataFrame(prediction_rows).sort_values(
        ["fold_id", "model", "group_reference", "prediction_origin"],
        kind="mergesort",
    ).reset_index(drop=True)
    aggregate, per_group = _aggregate_metrics(predictions, config)
    aggregate_by_model = {row["model"]: row for row in aggregate}
    per_group_frame = pd.DataFrame(per_group)
    persistence_group = per_group_frame.loc[
        per_group_frame["model"] == "persistence",
        ["group_reference", "mae"],
    ].rename(columns={"mae": "persistence_mae"})
    ridge_group = per_group_frame.loc[
        per_group_frame["model"] == "ridge",
        ["group_reference", "mae"],
    ].rename(columns={"mae": "ridge_mae"})
    group_comparison = persistence_group.merge(
        ridge_group,
        on="group_reference",
        validate="one_to_one",
    )
    improved = group_comparison["ridge_mae"] < group_comparison["persistence_mae"]
    persistence_mae = float(aggregate_by_model["persistence"]["mae"])
    ridge_mae = float(aggregate_by_model["ridge"]["mae"])
    improvement_percent = (
        100.0 * (persistence_mae - ridge_mae) / persistence_mae
        if persistence_mae > 0
        else None
    )
    comparison = {
        "model": "ridge",
        "baseline": "persistence",
        "mae_absolute_difference": ridge_mae - persistence_mae,
        "mae_improvement_percent": improvement_percent,
        "improved_group_count": int(improved.sum()),
        "not_improved_group_count": int((~improved).sum()),
        "evaluated_group_count": len(group_comparison),
    }
    split_summary = [
        {
            key: value
            for key, value in split.items()
            if key not in {"train_index", "test_index"}
        }
        for split in splits
    ]
    leakage = {
        "group_overlap_count": sum(
            int(split["group_overlap_count"]) for split in splits
        ),
        "target_horizon_alignment_valid": bool(
            (
                forecast_frame["forecast_target_cycle"]
                - forecast_frame["prediction_origin"]
                == config.horizon
            ).all()
        ),
        "feature_cutoff_not_after_origin": bool(
            (
                forecast_frame["feature_cutoff_cycle"]
                <= forecast_frame["prediction_origin"]
            ).all()
        ),
        "future_feature_accessed": False,
        "centered_rolling_used": False,
        "full_trajectory_statistic_used": False,
        "target_direct_feature_used": False,
        "preprocessing_fit_scope": "training_partition_only",
        "random_row_split_used": False,
        "status": "passed",
    }
    if (
        leakage["group_overlap_count"]
        or not leakage["target_horizon_alignment_valid"]
        or not leakage["feature_cutoff_not_after_origin"]
    ):
        leakage["status"] = "failed"

    return {
        "predictions": predictions,
        "aggregate_metrics": aggregate,
        "per_group_metrics": per_group,
        "baseline_comparison": comparison,
        "split_diagnostics": split_summary,
        "preprocessing_diagnostics": preprocessing_rows,
        "leakage_audit": leakage,
        "physical_plausibility_audit": _physical_plausibility(
            predictions,
            config,
        ),
    }


def _scientific_assessment(
    evaluation: Mapping[str, Any],
) -> dict[str, Any]:
    comparison = evaluation["baseline_comparison"]
    group_count = int(comparison["evaluated_group_count"])
    improved_count = int(comparison["improved_group_count"])
    aggregate_improved = float(comparison["mae_absolute_difference"]) < 0
    majority_improved = improved_count >= math.ceil(group_count / 2)
    leakage_passed = evaluation["leakage_audit"]["status"] == "passed"

    if not leakage_passed:
        status = "inconclusive"
        reason = "leakage audit did not pass"
    elif aggregate_improved and majority_improved and group_count >= 5:
        status = "supported"
        reason = (
            "ridge improved pooled MAE and at least half of evaluated batteries"
        )
    elif aggregate_improved and improved_count >= 2:
        status = "diagnostic"
        reason = "aggregate improvement was not stable across most batteries"
    elif group_count < 3:
        status = "inconclusive"
        reason = "too few held-out batteries for a generalization assessment"
    else:
        status = "unsupported"
        reason = "ridge did not improve on persistence under the registered rules"

    return {
        "status": status,
        "reason": reason,
        "evaluation_scenario": EVALUATION_SCENARIO,
        "unseen_battery_identity_generalization": True,
        "observed_history_conditioned": True,
        "zero_shot": False,
        "mechanism_claim_allowed": False,
        "lifetime_or_rul_claim_allowed": False,
        "engineering_decision_allowed": False,
    }


def _build_result(
    source: pd.DataFrame,
    config: BatteryForecastConfig,
    *,
    source_sha256: str,
) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    readiness = assess_data_readiness(
        source,
        config,
        source_sha256=source_sha256,
    )
    if readiness["status"] == "blocked_by_data_readiness":
        raise ValueError("; ".join(readiness["fatal_errors"]))
    forecast_frame, exclusions = build_lagged_forecast_frame(source, config)
    if forecast_frame[config.group_column].nunique() < 3:
        raise ValueError("fewer than three batteries have eligible forecast rows")
    evaluation = evaluate_forecast_frame(forecast_frame, config)
    source_rows = len(source)
    excluded_rows = int(sum(exclusions.values()))
    warnings = list(readiness["warnings"])
    if forecast_frame[config.group_column].nunique() < readiness["trajectory_count"]:
        warnings.append("one or more short trajectories have no eligible forecast rows")

    result = {
        "schema_version": BENCHMARK_VERSION,
        "artifact_kind": "battery_generalization_forecast_result",
        "benchmark_id": BENCHMARK_ID,
        "evaluation_scenario": EVALUATION_SCENARIO,
        "source_dataset_reference": config.input_path,
        "source_lineage_reference": config.source_lineage_path,
        "source_sha256": source_sha256,
        "target_column": config.target_column,
        "target_unit": config.target_unit,
        "forecast_horizon_cycles": config.horizon,
        "group_column": config.group_column,
        "time_column": config.time_column,
        "feature_specification": {
            "source_columns": [
                config.group_column,
                config.time_column,
                config.target_column,
            ],
            "feature_columns": feature_columns(config),
            "lags": list(config.lags),
            "rolling_window": config.rolling_window,
            "rolling_direction": "trailing_only_including_origin",
            "minimum_history": config.minimum_history,
            "target_alignment_rule": "exact_cycle_t_plus_h",
            "missing_value_policy": "exclude_with_recorded_reason",
            "full_trajectory_statistics_used": False,
        },
        "data_readiness": {
            **readiness,
            "eligible_prediction_rows": len(forecast_frame),
            "evaluable_trajectory_count": int(
                forecast_frame[config.group_column].nunique()
            ),
        },
        "excluded_rows": excluded_rows,
        "source_rows": source_rows,
        "exclusion_reasons": exclusions,
        "split_method": config.split_method,
        "random_seed": config.random_seed,
        "split_diagnostics": evaluation["split_diagnostics"],
        "preprocessing_pipeline": {
            "ridge": [
                "SimpleImputer(strategy=median)",
                "StandardScaler",
                f"Ridge(alpha={config.ridge_alpha})",
            ],
            "fit_scope": "training_partition_only",
        },
        "preprocessing_diagnostics": evaluation["preprocessing_diagnostics"],
        "baseline_specification": {
            "model": "persistence",
            "prediction": "capacity_retention_at_origin",
        },
        "model_specification": {
            "models": list(config.models),
            "ridge_alpha": config.ridge_alpha,
            "hyperparameter_search_performed": False,
            "prediction_clipping_performed": False,
        },
        "aggregate_metrics": evaluation["aggregate_metrics"],
        "per_group_metrics": evaluation["per_group_metrics"],
        "baseline_comparison": evaluation["baseline_comparison"],
        "leakage_checks": evaluation["leakage_audit"],
        "physical_plausibility_checks": evaluation[
            "physical_plausibility_audit"
        ],
        "warnings": warnings,
        "scientific_limitations": [
            "retrieval reproducibility remains insufficient_evidence",
            "official NASA source snapshot and calibration metadata remain unresolved",
            "test-battery pre-origin history is required; this is not zero-shot",
            "cross-institution and independent external validation are unavailable",
            "battery chemistry and protocol comparability remain restricted",
            "capacity forecasting does not identify a degradation mechanism",
        ],
        "software_validation": "passed",
        "scientific_assessment": _scientific_assessment(evaluation),
        "network_called": False,
        "credentials_read": False,
        "source_mutation_performed": False,
        "model_executed": True,
    }
    frames = {
        "forecast_frame": forecast_frame,
        "predictions": evaluation["predictions"],
        "aggregate_metrics": pd.DataFrame(evaluation["aggregate_metrics"]),
        "per_group_metrics": pd.DataFrame(evaluation["per_group_metrics"]),
    }
    return result, frames


def preview_benchmark(
    config: BatteryForecastConfig,
    repo_root: str | Path = ".",
) -> dict[str, Any]:
    source_path = resolve_repo_path(repo_root, config.input_path)
    source_sha = file_sha256(source_path)
    source = pd.read_csv(source_path)
    readiness = assess_data_readiness(source, config, source_sha256=source_sha)
    eligible_count = 0
    evaluable_groups = 0
    exclusions: dict[str, int] = {}
    if readiness["status"] != "blocked_by_data_readiness":
        forecast_frame, exclusions = build_lagged_forecast_frame(source, config)
        eligible_count = len(forecast_frame)
        evaluable_groups = int(forecast_frame[config.group_column].nunique())
    status = (
        "ready"
        if readiness["status"] != "blocked_by_data_readiness"
        and evaluable_groups >= 3
        else "blocked_by_data_readiness"
    )
    return {
        "schema_version": BENCHMARK_VERSION,
        "status": status,
        "benchmark_id": BENCHMARK_ID,
        "evaluation_scenario": EVALUATION_SCENARIO,
        "input_path": config.input_path,
        "source_sha256": source_sha,
        "target_column": config.target_column,
        "target_unit": config.target_unit,
        "group_column": config.group_column,
        "time_column": config.time_column,
        "horizon": config.horizon,
        "feature_columns": feature_columns(config),
        "split_method": config.split_method,
        "planned_fold_count": min(config.n_splits, max(evaluable_groups, 0)),
        "eligible_prediction_rows": eligible_count,
        "evaluable_trajectory_count": evaluable_groups,
        "exclusion_reasons": exclusions,
        "data_readiness": readiness,
        "writes_performed": False,
        "model_executed": False,
        "network_called": False,
        "credentials_read": False,
    }


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(content)
    try:
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _atomic_write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as handle:
        temp_path = Path(handle.name)
        frame.to_csv(handle, index=False)
    try:
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def compact_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    compact = {
        "schema_version": BENCHMARK_VERSION,
        "artifact_kind": "battery_generalization_forecast_compact_summary",
        "benchmark_id": result["benchmark_id"],
        "evaluation_scenario": result["evaluation_scenario"],
        "source_dataset_reference": result["source_dataset_reference"],
        "source_lineage_reference": result["source_lineage_reference"],
        "source_sha256": result["source_sha256"],
        "target_column": result["target_column"],
        "target_unit": result["target_unit"],
        "forecast_horizon_cycles": result["forecast_horizon_cycles"],
        "source_rows": result["source_rows"],
        "eligible_prediction_rows": result["data_readiness"][
            "eligible_prediction_rows"
        ],
        "source_trajectory_count": result["data_readiness"]["trajectory_count"],
        "evaluable_trajectory_count": result["data_readiness"][
            "evaluable_trajectory_count"
        ],
        "excluded_rows": result["excluded_rows"],
        "exclusion_reasons": result["exclusion_reasons"],
        "split_method": result["split_method"],
        "fold_count": len(result["split_diagnostics"]),
        "group_overlap_count": result["leakage_checks"]["group_overlap_count"],
        "leakage_checks": result["leakage_checks"],
        "aggregate_metrics": result["aggregate_metrics"],
        "baseline_comparison": result["baseline_comparison"],
        "physical_plausibility_checks": result[
            "physical_plausibility_checks"
        ],
        "software_validation": result["software_validation"],
        "scientific_assessment": result["scientific_assessment"],
        "scientific_limitations": result["scientific_limitations"],
        "deterministic_rerun_match": result["deterministic_rerun_match"],
        "first_run_checksum": result["first_run_checksum"],
        "second_run_checksum": result["second_run_checksum"],
        "network_called": False,
        "credentials_read": False,
        "source_mutation_performed": False,
        "model_executed": True,
    }
    compact["deterministic_result_checksum"] = canonical_checksum(compact)
    return compact


def _write_outputs(
    result: Mapping[str, Any],
    frames: Mapping[str, pd.DataFrame],
    config: BatteryForecastConfig,
    repo_root: str | Path,
    *,
    write_tracked_summary: bool,
) -> list[str]:
    output_root = resolve_repo_path(repo_root, config.output_root)
    paths = {
        "forecast_summary": output_root / "forecast_summary.json",
        "aggregate_metrics": output_root / "aggregate_metrics.csv",
        "per_battery_metrics": output_root / "per_battery_metrics.csv",
        "predictions": output_root / "predictions.csv",
        "data_readiness": output_root / "data_readiness.json",
        "leakage_audit": output_root / "leakage_audit.json",
    }
    _atomic_write_text(paths["forecast_summary"], canonical_json(result))
    _atomic_write_frame(paths["aggregate_metrics"], frames["aggregate_metrics"])
    _atomic_write_frame(paths["per_battery_metrics"], frames["per_group_metrics"])
    _atomic_write_frame(paths["predictions"], frames["predictions"])
    _atomic_write_text(
        paths["data_readiness"],
        canonical_json(result["data_readiness"]),
    )
    _atomic_write_text(
        paths["leakage_audit"],
        canonical_json(result["leakage_checks"]),
    )
    written = [
        path.relative_to(Path(repo_root).resolve()).as_posix()
        for path in paths.values()
    ]
    if write_tracked_summary:
        tracked_path = resolve_repo_path(repo_root, TRACKED_SUMMARY_PATH)
        _atomic_write_text(tracked_path, canonical_json(compact_summary(result)))
        written.append(TRACKED_SUMMARY_PATH)
    return written


def run_benchmark(
    config: BatteryForecastConfig,
    repo_root: str | Path = ".",
    *,
    write_outputs: bool = True,
    write_tracked_summary: bool = True,
) -> dict[str, Any]:
    source_path = resolve_repo_path(repo_root, config.input_path)
    source_sha_before = file_sha256(source_path)
    source = pd.read_csv(source_path)

    first, frames = _build_result(
        source,
        config,
        source_sha256=source_sha_before,
    )
    second, _ = _build_result(
        source,
        config,
        source_sha256=source_sha_before,
    )
    first_checksum = canonical_checksum(first)
    second_checksum = canonical_checksum(second)
    source_sha_after = file_sha256(source_path)
    if source_sha_before != source_sha_after:
        raise ValueError("source artifact changed during benchmark execution")
    if first_checksum != second_checksum:
        raise ValueError("deterministic repeated execution checksum mismatch")

    result = {
        **first,
        "source_sha256_before": source_sha_before,
        "source_sha256_after": source_sha_after,
        "first_run_checksum": first_checksum,
        "second_run_checksum": second_checksum,
        "deterministic_rerun_match": True,
    }
    result["deterministic_result_checksum"] = canonical_checksum(result)
    written: list[str] = []
    if write_outputs:
        written = _write_outputs(
            result,
            frames,
            config,
            repo_root,
            write_tracked_summary=write_tracked_summary,
        )
    return {
        "status": "completed",
        "result": result,
        "written": written,
        "network_called": False,
        "credentials_read": False,
        "source_mutation_performed": False,
        "model_executed": True,
    }


def _contains_absolute_path(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_absolute_path(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_absolute_path(item) for item in value)
    if not isinstance(value, str):
        return False
    normalized = value.replace("\\", "/")
    if normalized.startswith(("http://", "https://")):
        return False
    return _is_absolute_or_drive_qualified(normalized)


def validate_result_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    required = {
        "schema_version",
        "artifact_kind",
        "benchmark_id",
        "evaluation_scenario",
        "source_sha256",
        "forecast_horizon_cycles",
        "aggregate_metrics",
        "baseline_comparison",
        "leakage_checks",
        "physical_plausibility_checks",
        "software_validation",
        "scientific_assessment",
        "deterministic_result_checksum",
    }
    missing = sorted(required - set(payload))
    if missing:
        errors.append("missing required result field(s): " + ", ".join(missing))
    if payload.get("schema_version") != BENCHMARK_VERSION:
        errors.append("unsupported result schema_version")
    if payload.get("benchmark_id") != BENCHMARK_ID:
        errors.append("unexpected benchmark_id")
    if payload.get("evaluation_scenario") != EVALUATION_SCENARIO:
        errors.append("unexpected evaluation scenario")
    if _contains_absolute_path(payload):
        errors.append("result contains an absolute path")
    try:
        _scan_for_secrets(payload, key_path="result")
    except ValueError as exc:
        errors.append(str(exc))
    if payload.get("artifact_kind") == "battery_generalization_forecast_result":
        checksum_payload = dict(payload)
        recorded = checksum_payload.pop("deterministic_result_checksum", None)
        if recorded != canonical_checksum(checksum_payload):
            errors.append("deterministic checksum mismatch")
        leakage = payload.get("leakage_checks", {})
        if leakage.get("group_overlap_count") != 0:
            errors.append("train/test group overlap detected")
        if leakage.get("target_horizon_alignment_valid") is not True:
            errors.append("target horizon alignment is invalid")
        if leakage.get("future_feature_accessed") is not False:
            errors.append("future feature access is not prohibited")
        if leakage.get("preprocessing_fit_scope") != "training_partition_only":
            errors.append("preprocessing fit scope is not train-only")
    elif payload.get("artifact_kind") == "battery_generalization_forecast_compact_summary":
        checksum_payload = dict(payload)
        recorded = checksum_payload.pop("deterministic_result_checksum", None)
        if recorded != canonical_checksum(checksum_payload):
            errors.append("deterministic checksum mismatch")
        if payload.get("group_overlap_count") != 0:
            errors.append("train/test group overlap detected")
    else:
        errors.append("unknown result artifact_kind")
    return {
        "schema_version": BENCHMARK_VERSION,
        "status": "valid" if not errors else "invalid",
        "valid": not errors,
        "errors": errors,
    }


def validate_result_file(
    path: str | Path,
    repo_root: str | Path = ".",
) -> dict[str, Any]:
    result_path = resolve_repo_path(repo_root, path)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("forecast result must be a JSON object")
    return validate_result_payload(payload)
