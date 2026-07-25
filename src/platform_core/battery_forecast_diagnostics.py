from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from .battery_forecasting import (
    BENCHMARK_ID,
    canonical_checksum,
    canonical_json,
    file_sha256,
    resolve_repo_path,
    validate_result_payload as validate_forecast_result_payload,
)


DIAGNOSTIC_VERSION = "2.6.2"
DIAGNOSTIC_ID = "battery_forecast_failure_diagnostics_v1"
DEFAULT_CONFIG_PATH = "configs/examples/battery_forecast_diagnostics.json"
DEFAULT_OUTPUT_ROOT = "outputs/v2_6_battery_diagnostics"
DEFAULT_TRACKED_SUMMARY = (
    "data/processed/battery_v2_6_2_forecast_failure_diagnostic_summary.json"
)
ALLOWED_MODELS = ("persistence", "ridge")
SAFE_COLUMN_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
HEX_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SECRET_TOKENS = (
    "api_key",
    "apikey",
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "authorization",
    "private_key",
)

CONFIG_FIELDS = {
    "schema_version",
    "diagnostic_id",
    "case_study_id",
    "source_benchmark_config_path",
    "source_benchmark_summary_path",
    "source_benchmark_result_path",
    "source_predictions_path",
    "source_analysis_ready_path",
    "source_lineage_path",
    "metadata_recovery_summary_path",
    "expected_benchmark_summary_checksum",
    "expected_benchmark_result_checksum",
    "group_column",
    "time_column",
    "target_column",
    "models",
    "horizon",
    "local_window",
    "regime_early_max_cycle",
    "regime_middle_max_cycle",
    "sparse_prediction_max",
    "abrupt_change_threshold",
    "high_target_std_threshold",
    "low_target_std_threshold",
    "high_local_volatility_threshold",
    "flat_range_threshold",
    "flat_window",
    "physical_min",
    "physical_max",
    "source_benchmark_execution_status",
    "credential_policy",
    "output_root",
    "tracked_summary_path",
    "output_policy",
}

RESULT_FIELDS = {
    "schema_version",
    "artifact_kind",
    "diagnostic_id",
    "case_study_id",
    "source_benchmark_reference",
    "source_benchmark_checksum",
    "source_benchmark_result_reference",
    "source_benchmark_result_checksum",
    "source_predictions_reference",
    "source_predictions_sha256",
    "source_analysis_ready_reference",
    "source_analysis_ready_sha256",
    "source_lineage_reference",
    "evaluation_scenario",
    "forecast_horizon_cycles",
    "battery_count",
    "prediction_count",
    "aggregate_metrics",
    "influence_summary",
    "per_battery_diagnostics",
    "influence_analysis",
    "trajectory_quality_flags",
    "degradation_regime_metrics",
    "local_trend_relationships",
    "physical_violation_analysis",
    "comparability_readiness",
    "dominant_failure_modes",
    "unresolved_information",
    "recommendations",
    "prohibited_claims",
    "scientific_closeout",
    "diagnostic_thresholds",
    "regime_policy",
    "network_called",
    "credentials_read",
    "source_mutation_performed",
    "model_retrained",
    "source_benchmark_model_reexecuted",
    "first_run_checksum",
    "second_run_checksum",
    "deterministic_rerun_match",
    "source_hashes_before",
    "source_hashes_after",
    "deterministic_result_checksum",
}

COMPACT_FIELDS = {
    "schema_version",
    "artifact_kind",
    "diagnostic_id",
    "case_study_id",
    "source_benchmark_reference",
    "source_benchmark_checksum",
    "source_benchmark_result_checksum",
    "source_predictions_sha256",
    "source_analysis_ready_reference",
    "source_analysis_ready_sha256",
    "evaluation_scenario",
    "forecast_horizon_cycles",
    "battery_count",
    "prediction_count",
    "aggregate_metrics",
    "influence_summary",
    "degradation_regime_metrics",
    "physical_violation_analysis",
    "comparability_readiness",
    "dominant_failure_modes",
    "unresolved_information",
    "recommendations",
    "prohibited_claims",
    "scientific_closeout",
    "diagnostic_thresholds",
    "regime_policy",
    "network_called",
    "credentials_read",
    "source_mutation_performed",
    "model_retrained",
    "source_benchmark_model_reexecuted",
    "first_run_checksum",
    "second_run_checksum",
    "deterministic_rerun_match",
    "deterministic_result_checksum",
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, Path):
        return value.as_posix()
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


def _is_absolute_or_drive_qualified(path: str | Path) -> bool:
    text = str(path).replace("\\", "/")
    return (
        Path(text).is_absolute()
        or bool(re.match(r"^[A-Za-z]:", text))
        or text.startswith("/")
        or text.startswith("//")
    )


def _scan_for_secrets(value: Any, *, key_path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text == "credential_policy":
                if item != {
                    "store_credentials": False,
                    "network_access_required": False,
                }:
                    raise ValueError(
                        "credential policy must disable storage and network"
                    )
                continue
            safe_evidence = key_text == "credentials_read" and item is False
            if not safe_evidence and any(
                token in key_text for token in SECRET_TOKENS
            ):
                raise ValueError(f"secret-like field is prohibited: {key_path}.{key}")
            _scan_for_secrets(item, key_path=f"{key_path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _scan_for_secrets(item, key_path=f"{key_path}[{index}]")
        return
    if isinstance(value, str):
        lowered = value.lower()
        if any(f"{token}=" in lowered for token in SECRET_TOKENS):
            raise ValueError(f"secret-like value is prohibited at {key_path}")


def _contains_absolute_path(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_absolute_path(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_absolute_path(item) for item in value)
    if isinstance(value, str):
        return _is_absolute_or_drive_qualified(value)
    return False


@dataclass(frozen=True)
class BatteryForecastDiagnosticConfig:
    schema_version: str
    diagnostic_id: str
    case_study_id: str
    source_benchmark_config_path: str
    source_benchmark_summary_path: str
    source_benchmark_result_path: str
    source_predictions_path: str
    source_analysis_ready_path: str
    source_lineage_path: str
    metadata_recovery_summary_path: str
    expected_benchmark_summary_checksum: str
    expected_benchmark_result_checksum: str
    group_column: str
    time_column: str
    target_column: str
    models: tuple[str, ...]
    horizon: int
    local_window: int
    regime_early_max_cycle: int
    regime_middle_max_cycle: int
    sparse_prediction_max: int
    abrupt_change_threshold: float
    high_target_std_threshold: float
    low_target_std_threshold: float
    high_local_volatility_threshold: float
    flat_range_threshold: float
    flat_window: int
    physical_min: float
    physical_max: float
    source_benchmark_execution_status: str
    credential_policy: Mapping[str, bool]
    output_root: str
    tracked_summary_path: str
    output_policy: str

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> "BatteryForecastDiagnosticConfig":
        unknown = sorted(set(payload) - CONFIG_FIELDS)
        missing = sorted(CONFIG_FIELDS - set(payload))
        if unknown:
            raise ValueError("unknown config field(s): " + ", ".join(unknown))
        if missing:
            raise ValueError("missing config field(s): " + ", ".join(missing))
        _scan_for_secrets(payload, key_path="config")

        path_fields = (
            "source_benchmark_config_path",
            "source_benchmark_summary_path",
            "source_benchmark_result_path",
            "source_predictions_path",
            "source_analysis_ready_path",
            "source_lineage_path",
            "metadata_recovery_summary_path",
            "output_root",
            "tracked_summary_path",
        )
        normalized_paths: dict[str, str] = {}
        for field in path_fields:
            value = str(payload[field]).replace("\\", "/")
            if _is_absolute_or_drive_qualified(value) or ".." in Path(value).parts:
                raise ValueError(
                    f"{field} must be repository-relative and non-traversing"
                )
            normalized_paths[field] = Path(value).as_posix()

        for field in ("group_column", "time_column", "target_column"):
            if not SAFE_COLUMN_PATTERN.fullmatch(str(payload[field])):
                raise ValueError(f"{field} must be a simple column identifier")

        config = cls(
            schema_version=str(payload["schema_version"]),
            diagnostic_id=str(payload["diagnostic_id"]),
            case_study_id=str(payload["case_study_id"]),
            source_benchmark_config_path=normalized_paths[
                "source_benchmark_config_path"
            ],
            source_benchmark_summary_path=normalized_paths[
                "source_benchmark_summary_path"
            ],
            source_benchmark_result_path=normalized_paths[
                "source_benchmark_result_path"
            ],
            source_predictions_path=normalized_paths["source_predictions_path"],
            source_analysis_ready_path=normalized_paths[
                "source_analysis_ready_path"
            ],
            source_lineage_path=normalized_paths["source_lineage_path"],
            metadata_recovery_summary_path=normalized_paths[
                "metadata_recovery_summary_path"
            ],
            expected_benchmark_summary_checksum=str(
                payload["expected_benchmark_summary_checksum"]
            ),
            expected_benchmark_result_checksum=str(
                payload["expected_benchmark_result_checksum"]
            ),
            group_column=str(payload["group_column"]),
            time_column=str(payload["time_column"]),
            target_column=str(payload["target_column"]),
            models=tuple(str(item) for item in payload["models"]),
            horizon=int(payload["horizon"]),
            local_window=int(payload["local_window"]),
            regime_early_max_cycle=int(payload["regime_early_max_cycle"]),
            regime_middle_max_cycle=int(payload["regime_middle_max_cycle"]),
            sparse_prediction_max=int(payload["sparse_prediction_max"]),
            abrupt_change_threshold=float(payload["abrupt_change_threshold"]),
            high_target_std_threshold=float(
                payload["high_target_std_threshold"]
            ),
            low_target_std_threshold=float(payload["low_target_std_threshold"]),
            high_local_volatility_threshold=float(
                payload["high_local_volatility_threshold"]
            ),
            flat_range_threshold=float(payload["flat_range_threshold"]),
            flat_window=int(payload["flat_window"]),
            physical_min=float(payload["physical_min"]),
            physical_max=float(payload["physical_max"]),
            source_benchmark_execution_status=str(
                payload["source_benchmark_execution_status"]
            ),
            credential_policy=dict(payload["credential_policy"]),
            output_root=normalized_paths["output_root"],
            tracked_summary_path=normalized_paths["tracked_summary_path"],
            output_policy=str(payload["output_policy"]),
        )
        config._validate()
        return config

    def _validate(self) -> None:
        if self.schema_version != DIAGNOSTIC_VERSION:
            raise ValueError(f"schema_version must be {DIAGNOSTIC_VERSION}")
        if self.diagnostic_id != DIAGNOSTIC_ID:
            raise ValueError(f"diagnostic_id must be {DIAGNOSTIC_ID}")
        if self.case_study_id != "kaggle_battery":
            raise ValueError("case_study_id must be kaggle_battery")
        if self.models != ALLOWED_MODELS:
            raise ValueError("models must remain persistence, ridge")
        if self.horizon != 5:
            raise ValueError("horizon must remain the registered exact t+5")
        if self.local_window < 2 or self.local_window > 20:
            raise ValueError("local_window must be in the bounded range 2..20")
        if not (
            0 < self.regime_early_max_cycle < self.regime_middle_max_cycle
        ):
            raise ValueError("regime cycle boundaries must be positive and ordered")
        if self.sparse_prediction_max < 1:
            raise ValueError("sparse_prediction_max must be positive")
        positive_thresholds = (
            self.abrupt_change_threshold,
            self.high_target_std_threshold,
            self.low_target_std_threshold,
            self.high_local_volatility_threshold,
            self.flat_range_threshold,
        )
        if any(not math.isfinite(item) or item <= 0 for item in positive_thresholds):
            raise ValueError("diagnostic thresholds must be finite and positive")
        if self.low_target_std_threshold >= self.high_target_std_threshold:
            raise ValueError("target standard-deviation thresholds must be ordered")
        if self.flat_window < 2 or self.flat_window > 20:
            raise ValueError("flat_window must be in the bounded range 2..20")
        if (
            not math.isfinite(self.physical_min)
            or not math.isfinite(self.physical_max)
            or self.physical_min >= self.physical_max
        ):
            raise ValueError("physical bounds must be finite and increasing")
        for checksum in (
            self.expected_benchmark_summary_checksum,
            self.expected_benchmark_result_checksum,
        ):
            if not HEX_SHA256_PATTERN.fullmatch(checksum):
                raise ValueError("expected benchmark checksums must be SHA-256")
        if self.output_root != DEFAULT_OUTPUT_ROOT:
            raise ValueError(f"output_root must be {DEFAULT_OUTPUT_ROOT}")
        if self.tracked_summary_path != DEFAULT_TRACKED_SUMMARY:
            raise ValueError(
                f"tracked_summary_path must be {DEFAULT_TRACKED_SUMMARY}"
            )
        if self.source_benchmark_execution_status not in {
            "existing_local_output_reused",
            "reexecuted_same_config_for_diagnostics",
        }:
            raise ValueError("unsupported source_benchmark_execution_status")
        if self.credential_policy != {
            "store_credentials": False,
            "network_access_required": False,
        }:
            raise ValueError("credential_policy must disable storage and network")
        if self.output_policy != "local_details_and_tracked_compact_summary":
            raise ValueError(
                "output_policy must be local_details_and_tracked_compact_summary"
            )

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(self.__dict__)


def load_config(
    path: str | Path = DEFAULT_CONFIG_PATH,
    repo_root: str | Path = ".",
) -> BatteryForecastDiagnosticConfig:
    config_path = resolve_repo_path(repo_root, path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("diagnostic config must be a JSON object")
    return BatteryForecastDiagnosticConfig.from_mapping(payload)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def _group_reference(group_id: Any) -> str:
    digest = hashlib.sha256(f"battery-group:{group_id}".encode("utf-8")).hexdigest()
    return f"battery_ref_{digest[:12]}"


def _metric_values(actual: pd.Series, predicted: pd.Series) -> dict[str, float | None]:
    actual_values = actual.to_numpy(dtype=float)
    predicted_values = predicted.to_numpy(dtype=float)
    error = predicted_values - actual_values
    absolute = np.abs(error)
    mae = float(np.mean(absolute))
    rmse = float(np.sqrt(np.mean(error**2)))
    denominator = float(np.sum((actual_values - np.mean(actual_values)) ** 2))
    r2 = (
        float(1.0 - np.sum(error**2) / denominator)
        if len(actual_values) >= 2 and denominator > 0
        else None
    )
    return {
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
        "maximum_absolute_error": float(np.max(absolute)),
        "median_absolute_error": float(np.median(absolute)),
        "absolute_error_sum": float(np.sum(absolute)),
    }


def _regime(origin: int, config: BatteryForecastDiagnosticConfig) -> str:
    if origin <= config.regime_early_max_cycle:
        return "early"
    if origin <= config.regime_middle_max_cycle:
        return "middle"
    return "late"


def _slope(times: Sequence[float], values: Sequence[float]) -> float:
    x = np.asarray(times, dtype=float)
    y = np.asarray(values, dtype=float)
    centered = x - np.mean(x)
    denominator = float(np.dot(centered, centered))
    if len(x) < 2 or denominator <= 0:
        return 0.0
    return float(np.dot(centered, y - np.mean(y)) / denominator)


def _input_paths(
    config: BatteryForecastDiagnosticConfig,
    repo_root: str | Path,
) -> dict[str, Path]:
    return {
        "benchmark_config": resolve_repo_path(
            repo_root,
            config.source_benchmark_config_path,
        ),
        "benchmark_summary": resolve_repo_path(
            repo_root,
            config.source_benchmark_summary_path,
        ),
        "benchmark_result": resolve_repo_path(
            repo_root,
            config.source_benchmark_result_path,
        ),
        "predictions": resolve_repo_path(
            repo_root,
            config.source_predictions_path,
        ),
        "analysis_ready": resolve_repo_path(
            repo_root,
            config.source_analysis_ready_path,
        ),
        "lineage": resolve_repo_path(repo_root, config.source_lineage_path),
        "metadata_recovery": resolve_repo_path(
            repo_root,
            config.metadata_recovery_summary_path,
        ),
    }


def _validate_benchmark_artifacts(
    config: BatteryForecastDiagnosticConfig,
    paths: Mapping[str, Path],
) -> tuple[dict[str, Any], dict[str, Any]]:
    summary = _load_json(paths["benchmark_summary"])
    summary_validation = validate_forecast_result_payload(summary)
    if not summary_validation["valid"]:
        raise ValueError(
            "source benchmark summary is invalid: "
            + "; ".join(summary_validation["errors"])
        )
    if (
        summary.get("deterministic_result_checksum")
        != config.expected_benchmark_summary_checksum
    ):
        raise ValueError("source benchmark checksum mismatch")

    result = _load_json(paths["benchmark_result"])
    result_validation = validate_forecast_result_payload(result)
    if not result_validation["valid"]:
        raise ValueError(
            "source benchmark result is invalid: "
            + "; ".join(result_validation["errors"])
        )
    if (
        result.get("deterministic_result_checksum")
        != config.expected_benchmark_result_checksum
    ):
        raise ValueError("source benchmark detailed-result checksum mismatch")

    consistency_fields = (
        "benchmark_id",
        "evaluation_scenario",
        "source_sha256",
        "forecast_horizon_cycles",
    )
    for field in consistency_fields:
        summary_value = (
            summary.get("forecast_horizon_cycles")
            if field == "forecast_horizon_cycles"
            else summary.get(field)
        )
        if summary_value != result.get(field):
            raise ValueError(f"source benchmark field mismatch: {field}")
    if summary.get("benchmark_id") != BENCHMARK_ID:
        raise ValueError("unexpected source benchmark ID")
    if result.get("model_specification", {}).get(
        "hyperparameter_search_performed"
    ) is not False:
        raise ValueError("source benchmark used hyperparameter search")
    if result.get("model_specification", {}).get(
        "prediction_clipping_performed"
    ) is not False:
        raise ValueError("source benchmark predictions were clipped")
    if result.get("leakage_checks", {}).get("status") != "passed":
        raise ValueError("source benchmark leakage audit did not pass")
    if result.get("scientific_assessment", {}).get("status") != "unsupported":
        raise ValueError("source benchmark scientific assessment changed")
    return summary, result


def _validate_predictions(
    predictions: pd.DataFrame,
    config: BatteryForecastDiagnosticConfig,
    benchmark_result: Mapping[str, Any],
) -> pd.DataFrame:
    required = {
        "fold_id",
        "model",
        config.group_column,
        "group_reference",
        "prediction_origin",
        "forecast_target_cycle",
        "feature_cutoff_cycle",
        "actual",
        "capacity_current",
        "prediction_raw",
        "prediction_clipped",
        "outside_training_target_range",
    }
    missing = sorted(required - set(predictions.columns))
    if missing:
        raise ValueError(
            "source predictions missing required column(s): " + ", ".join(missing)
        )
    models = tuple(sorted(str(item) for item in predictions["model"].unique()))
    if models != tuple(sorted(config.models)):
        raise ValueError("source predictions contain unexpected models")
    if predictions["prediction_raw"].isna().any():
        raise ValueError("source predictions contain missing predictions")
    numeric = predictions[
        [
            "prediction_origin",
            "forecast_target_cycle",
            "feature_cutoff_cycle",
            "actual",
            "capacity_current",
            "prediction_raw",
        ]
    ].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any() or not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("source predictions contain invalid numeric values")
    if not (
        numeric["forecast_target_cycle"] - numeric["prediction_origin"]
        == config.horizon
    ).all():
        raise ValueError("source prediction horizon mismatch")
    if not (
        numeric["feature_cutoff_cycle"] <= numeric["prediction_origin"]
    ).all():
        raise ValueError("source prediction cutoff occurs after origin")

    key = [
        "fold_id",
        "model",
        "group_reference",
        "prediction_origin",
    ]
    if predictions.duplicated(key).any():
        raise ValueError("source predictions contain duplicate model-origin rows")
    per_model = predictions.groupby("model", sort=True).size()
    if per_model.nunique() != 1:
        raise ValueError("source prediction counts differ by model")

    expected_by_model = {
        row["model"]: int(row["prediction_count"])
        for row in benchmark_result["aggregate_metrics"]
    }
    if per_model.to_dict() != expected_by_model:
        raise ValueError("source prediction counts do not match benchmark")

    actual_by_origin = predictions.groupby(
        ["group_reference", "prediction_origin"],
        sort=True,
    )["actual"].nunique()
    if (actual_by_origin != 1).any():
        raise ValueError("source prediction targets disagree between models")
    references = predictions[
        [config.group_column, "group_reference"]
    ].drop_duplicates()
    if references[config.group_column].nunique() != len(references):
        raise ValueError("battery identity maps to multiple references")
    if any(
        row.group_reference != _group_reference(row[config.group_column])
        for _, row in references.iterrows()
    ):
        raise ValueError("battery reference checksum mismatch")
    return predictions.copy(deep=True)


def _load_inputs(
    config: BatteryForecastDiagnosticConfig,
    repo_root: str | Path,
) -> dict[str, Any]:
    paths = _input_paths(config, repo_root)
    missing = [
        path.relative_to(Path(repo_root).resolve()).as_posix()
        for path in paths.values()
        if not path.is_file()
    ]
    if missing:
        raise ValueError("missing required input artifact(s): " + ", ".join(missing))
    summary, result = _validate_benchmark_artifacts(config, paths)
    source = pd.read_csv(paths["analysis_ready"])
    predictions = _validate_predictions(
        pd.read_csv(paths["predictions"]),
        config,
        result,
    )
    lineage = _load_json(paths["lineage"])
    metadata_recovery = pd.read_csv(paths["metadata_recovery"])

    required_source = {
        config.group_column,
        config.time_column,
        config.target_column,
    }
    missing_source = sorted(required_source - set(source.columns))
    if missing_source:
        raise ValueError(
            "analysis-ready source missing column(s): " + ", ".join(missing_source)
        )
    source_sha = file_sha256(paths["analysis_ready"])
    if source_sha != summary.get("source_sha256"):
        raise ValueError("analysis-ready source checksum mismatch")
    if int(source[config.group_column].nunique()) != int(
        summary["source_trajectory_count"]
    ):
        raise ValueError("analysis-ready battery count mismatch")
    if int(len(source)) != int(summary["source_rows"]):
        raise ValueError("analysis-ready row count mismatch")
    return {
        "paths": paths,
        "benchmark_summary": summary,
        "benchmark_result": result,
        "source": source,
        "predictions": predictions,
        "lineage": lineage,
        "metadata_recovery": metadata_recovery,
    }


def _prepare_prediction_origins(
    predictions: pd.DataFrame,
    source: pd.DataFrame,
    config: BatteryForecastDiagnosticConfig,
) -> pd.DataFrame:
    key = [
        "fold_id",
        config.group_column,
        "group_reference",
        "prediction_origin",
        "forecast_target_cycle",
        "feature_cutoff_cycle",
        "actual",
        "capacity_current",
    ]
    wide = (
        predictions.pivot(index=key, columns="model", values="prediction_raw")
        .reset_index()
        .sort_values(["group_reference", "prediction_origin"], kind="mergesort")
        .reset_index(drop=True)
    )
    if any(model not in wide.columns for model in config.models):
        raise ValueError("source predictions cannot be paired by model")
    wide["regime"] = wide["prediction_origin"].map(
        lambda value: _regime(int(value), config)
    )

    local_rows: list[dict[str, Any]] = []
    working = source.copy(deep=True)
    working["__source_order"] = np.arange(len(working), dtype=int)
    for battery_id, battery in working.groupby(config.group_column, sort=True):
        ordered = battery.sort_values(
            [config.time_column, "__source_order"],
            kind="mergesort",
        )
        origins = wide.loc[
            wide[config.group_column].astype(str) == str(battery_id),
            "prediction_origin",
        ].astype(int)
        for origin in origins:
            history = ordered.loc[
                pd.to_numeric(ordered[config.time_column], errors="coerce") <= origin
            ].tail(config.local_window)
            times = pd.to_numeric(
                history[config.time_column],
                errors="coerce",
            ).to_numpy(dtype=float)
            values = pd.to_numeric(
                history[config.target_column],
                errors="coerce",
            ).to_numpy(dtype=float)
            differences = np.diff(values)
            local_rows.append(
                {
                    config.group_column: str(battery_id),
                    "prediction_origin": int(origin),
                    "local_slope": _slope(times, values),
                    "local_volatility": float(np.std(values, ddof=0)),
                    "recent_monotonicity": (
                        float(np.mean(differences <= 0))
                        if len(differences)
                        else None
                    ),
                    "abrupt_change_proximity": bool(
                        np.any(np.abs(differences) >= config.abrupt_change_threshold)
                    ),
                    "local_history_count": len(values),
                    "local_history_max_cycle": int(np.max(times)),
                }
            )
    local = pd.DataFrame(local_rows)
    if (local["local_history_max_cycle"] > local["prediction_origin"]).any():
        raise ValueError("local trend diagnostics accessed a future observation")
    wide = wide.merge(
        local,
        on=[config.group_column, "prediction_origin"],
        how="left",
        validate="one_to_one",
    )
    if wide["local_slope"].isna().any():
        raise ValueError("local trend diagnostics are incomplete")
    return wide


def _trajectory_quality(
    source: pd.DataFrame,
    config: BatteryForecastDiagnosticConfig,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    working = source.copy(deep=True)
    working["__source_order"] = np.arange(len(working), dtype=int)
    expected_metadata = (
        "ambient_temperature_c",
        "source_filename",
        "test_id",
    )
    for battery_id, battery in working.groupby(config.group_column, sort=True):
        source_times = pd.to_numeric(
            battery[config.time_column],
            errors="coerce",
        )
        duplicate_cycle_count = int(source_times.duplicated().sum())
        unordered_cycle_count = int((source_times.diff().dropna() < 0).sum())
        ordered = battery.assign(__time=source_times).sort_values(
            ["__time", "__source_order"],
            kind="mergesort",
        )
        times = ordered["__time"].to_numpy(dtype=float)
        target = pd.to_numeric(
            ordered[config.target_column],
            errors="coerce",
        ).to_numpy(dtype=float)
        unique_times = np.unique(times)
        time_differences = np.diff(unique_times)
        missing_cycle_gap_count = int((time_differences > 1).sum())
        missing_cycle_count = int(
            np.maximum(time_differences - 1, 0).sum()
        )
        differences = np.diff(target)
        abrupt_drop_count = int(
            (differences <= -config.abrupt_change_threshold).sum()
        )
        abrupt_upward_recovery_count = int(
            (differences >= config.abrupt_change_threshold).sum()
        )
        suspicious_single_point_jump_count = 0
        if len(differences) >= 2:
            first = differences[:-1]
            second = differences[1:]
            suspicious_single_point_jump_count = int(
                (
                    (first * second < 0)
                    & (np.abs(first) >= config.abrupt_change_threshold)
                    & (np.abs(second) >= config.abrupt_change_threshold)
                ).sum()
            )

        target_series = pd.Series(target)
        rolling_std = target_series.rolling(
            config.local_window,
            min_periods=config.local_window,
        ).std(ddof=0)
        high_local_volatility_window_count = int(
            (rolling_std >= config.high_local_volatility_threshold).sum()
        )
        rolling_range = (
            target_series.rolling(
                config.flat_window,
                min_periods=config.flat_window,
            ).max()
            - target_series.rolling(
                config.flat_window,
                min_periods=config.flat_window,
            ).min()
        )
        flat_window_count = int(
            (rolling_range <= config.flat_range_threshold).sum()
        )
        target_std = float(np.std(target, ddof=0))
        missing_metadata_fields = [
            field
            for field in expected_metadata
            if field not in ordered.columns or ordered[field].isna().any()
        ]
        if (
            "internal_resistance_ohm" not in ordered.columns
            or ordered["internal_resistance_ohm"].isna().all()
        ):
            missing_metadata_fields.append("internal_resistance_ohm")
        rows.append(
            {
                config.group_column: str(battery_id),
                "group_reference": _group_reference(battery_id),
                "trajectory_row_count": len(ordered),
                "cycle_min": int(np.min(times)),
                "cycle_max": int(np.max(times)),
                "duplicate_cycle_count": duplicate_cycle_count,
                "missing_cycle_gap_count": missing_cycle_gap_count,
                "missing_cycle_count": missing_cycle_count,
                "unordered_cycle_count": unordered_cycle_count,
                "abrupt_drop_count": abrupt_drop_count,
                "abrupt_upward_recovery_count": abrupt_upward_recovery_count,
                "suspicious_single_point_jump_count": (
                    suspicious_single_point_jump_count
                ),
                "high_local_volatility_window_count": (
                    high_local_volatility_window_count
                ),
                "flat_window_count": flat_window_count,
                "target_min": float(np.min(target)),
                "target_max": float(np.max(target)),
                "target_range": float(np.max(target) - np.min(target)),
                "target_std": target_std,
                "low_target_variation_flag": bool(
                    target_std <= config.low_target_std_threshold
                ),
                "high_target_volatility_flag": bool(
                    target_std >= config.high_target_std_threshold
                ),
                "missing_metadata_fields": ";".join(
                    sorted(set(missing_metadata_fields))
                ),
                "possible_data_quality_issue": bool(
                    duplicate_cycle_count
                    or unordered_cycle_count
                    or suspicious_single_point_jump_count
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(
        "group_reference",
        kind="mergesort",
    ).reset_index(drop=True)


def _regime_metrics(
    wide: pd.DataFrame,
    config: BatteryForecastDiagnosticConfig,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for regime in ("early", "middle", "late"):
        frame = wide.loc[wide["regime"] == regime]
        persistence = _metric_values(frame["actual"], frame["persistence"])
        ridge = _metric_values(frame["actual"], frame["ridge"])
        persistence_mae = float(persistence["mae"])
        ridge_mae = float(ridge["mae"])
        rows.append(
            {
                "regime": regime,
                "assignment_basis": "prediction_origin_fixed_cycle_boundary",
                "prediction_count": len(frame),
                "persistence_mae": persistence_mae,
                "persistence_rmse": persistence["rmse"],
                "ridge_mae": ridge_mae,
                "ridge_rmse": ridge["rmse"],
                "ridge_minus_persistence_mae": ridge_mae - persistence_mae,
                "ridge_relative_improvement_percent": (
                    100.0 * (persistence_mae - ridge_mae) / persistence_mae
                    if persistence_mae > 0
                    else None
                ),
                "persistence_physical_violation_count": int(
                    (
                        (frame["persistence"] < config.physical_min)
                        | (frame["persistence"] > config.physical_max)
                    ).sum()
                ),
                "ridge_physical_violation_count": int(
                    (
                        (frame["ridge"] < config.physical_min)
                        | (frame["ridge"] > config.physical_max)
                    ).sum()
                ),
                "future_target_used_for_assignment": False,
            }
        )
    return pd.DataFrame(rows)


def _per_battery_diagnostics(
    wide: pd.DataFrame,
    quality: pd.DataFrame,
    config: BatteryForecastDiagnosticConfig,
) -> pd.DataFrame:
    quality_by_reference = quality.set_index("group_reference")
    rows: list[dict[str, Any]] = []
    for group_reference, frame in wide.groupby("group_reference", sort=True):
        persistence = _metric_values(frame["actual"], frame["persistence"])
        ridge = _metric_values(frame["actual"], frame["ridge"])
        quality_row = quality_by_reference.loc[group_reference]
        classifications: list[str] = []
        persistence_mae = float(persistence["mae"])
        ridge_mae = float(ridge["mae"])
        ridge_physical_violations = int(
            (
                (frame["ridge"] < config.physical_min)
                | (frame["ridge"] > config.physical_max)
            ).sum()
        )
        if ridge_mae >= persistence_mae:
            classifications.append("baseline_dominant")
        if len(frame) <= config.sparse_prediction_max:
            classifications.append("sparse_evaluation")
        if bool(quality_row["high_target_volatility_flag"]):
            classifications.append("high_target_volatility")
        if (
            int(quality_row["abrupt_drop_count"])
            or int(quality_row["abrupt_upward_recovery_count"])
        ):
            classifications.append("abrupt_transition")
        if ridge_physical_violations:
            classifications.append("physical_extrapolation")
        if bool(quality_row["possible_data_quality_issue"]):
            classifications.append("possible_data_quality_issue")
        classifications.append("metadata_comparability_unresolved")

        battery_regime_worse_count = 0
        regime_values: dict[str, Any] = {}
        for regime_name in ("early", "middle", "late"):
            regime_frame = frame.loc[frame["regime"] == regime_name]
            if regime_frame.empty:
                regime_values[f"{regime_name}_prediction_count"] = 0
                regime_values[f"{regime_name}_persistence_mae"] = None
                regime_values[f"{regime_name}_ridge_mae"] = None
                continue
            regime_persistence_mae = float(
                np.mean(
                    np.abs(
                        regime_frame["actual"].to_numpy(dtype=float)
                        - regime_frame["persistence"].to_numpy(dtype=float)
                    )
                )
            )
            regime_ridge_mae = float(
                np.mean(
                    np.abs(
                        regime_frame["actual"].to_numpy(dtype=float)
                        - regime_frame["ridge"].to_numpy(dtype=float)
                    )
                )
            )
            battery_regime_worse_count += int(
                regime_ridge_mae >= regime_persistence_mae
            )
            regime_values[f"{regime_name}_prediction_count"] = len(regime_frame)
            regime_values[f"{regime_name}_persistence_mae"] = (
                regime_persistence_mae
            )
            regime_values[f"{regime_name}_ridge_mae"] = regime_ridge_mae
        if (
            ridge_mae >= persistence_mae
            and len(frame) > config.sparse_prediction_max
            and battery_regime_worse_count >= 2
        ):
            classifications.append("model_form_mismatch")
        if classifications == ["metadata_comparability_unresolved"]:
            classifications.append("no_clear_failure_mode")

        battery_id = str(frame[config.group_column].iloc[0])
        rows.append(
            {
                config.group_column: battery_id,
                "group_reference": group_reference,
                "prediction_count": len(frame),
                "prediction_cycle_min": int(frame["prediction_origin"].min()),
                "prediction_cycle_max": int(frame["prediction_origin"].max()),
                "target_min": float(frame["actual"].min()),
                "target_max": float(frame["actual"].max()),
                "target_range": float(frame["actual"].max() - frame["actual"].min()),
                "target_std": float(frame["actual"].std(ddof=0)),
                "persistence_mae": persistence_mae,
                "persistence_rmse": persistence["rmse"],
                "ridge_mae": ridge_mae,
                "ridge_rmse": ridge["rmse"],
                "ridge_minus_persistence_mae": ridge_mae - persistence_mae,
                "ridge_relative_improvement_percent": (
                    100.0 * (persistence_mae - ridge_mae) / persistence_mae
                    if persistence_mae > 0
                    else None
                ),
                "persistence_maximum_absolute_error": persistence[
                    "maximum_absolute_error"
                ],
                "ridge_maximum_absolute_error": ridge["maximum_absolute_error"],
                "persistence_median_absolute_error": persistence[
                    "median_absolute_error"
                ],
                "ridge_median_absolute_error": ridge["median_absolute_error"],
                "persistence_negative_prediction_count": int(
                    (frame["persistence"] < 0).sum()
                ),
                "ridge_negative_prediction_count": int((frame["ridge"] < 0).sum()),
                "persistence_out_of_bound_prediction_count": int(
                    (
                        (frame["persistence"] < config.physical_min)
                        | (frame["persistence"] > config.physical_max)
                    ).sum()
                ),
                "ridge_out_of_bound_prediction_count": ridge_physical_violations,
                "mean_local_slope": float(frame["local_slope"].mean()),
                "mean_local_volatility": float(frame["local_volatility"].mean()),
                "abrupt_change_proximity_prediction_count": int(
                    frame["abrupt_change_proximity"].sum()
                ),
                "diagnostic_classifications": ";".join(
                    sorted(set(classifications))
                ),
                **regime_values,
            }
        )
    return pd.DataFrame(rows).sort_values(
        "group_reference",
        kind="mergesort",
    ).reset_index(drop=True)


def _influence_analysis(
    wide: pd.DataFrame,
    per_battery: pd.DataFrame,
) -> pd.DataFrame:
    total_count = len(wide)
    total_persistence_error = float(
        np.abs(wide["actual"] - wide["persistence"]).sum()
    )
    total_ridge_error = float(np.abs(wide["actual"] - wide["ridge"]).sum())
    total_excess = total_ridge_error - total_persistence_error
    rows: list[dict[str, Any]] = []
    for _, battery in per_battery.iterrows():
        group_reference = battery["group_reference"]
        frame = wide.loc[wide["group_reference"] == group_reference]
        count = len(frame)
        persistence_error = float(
            np.abs(frame["actual"] - frame["persistence"]).sum()
        )
        ridge_error = float(np.abs(frame["actual"] - frame["ridge"]).sum())
        remaining_count = total_count - count
        if remaining_count <= 0:
            raise ValueError("leave-one-battery-out requires multiple batteries")
        loo_persistence = (
            total_persistence_error - persistence_error
        ) / remaining_count
        loo_ridge = (total_ridge_error - ridge_error) / remaining_count
        rows.append(
            {
                "group_reference": group_reference,
                "prediction_count": count,
                "prediction_count_contribution": count / total_count,
                "persistence_absolute_error_sum": persistence_error,
                "persistence_absolute_error_contribution": (
                    persistence_error / total_persistence_error
                    if total_persistence_error > 0
                    else None
                ),
                "ridge_absolute_error_sum": ridge_error,
                "ridge_absolute_error_contribution": (
                    ridge_error / total_ridge_error
                    if total_ridge_error > 0
                    else None
                ),
                "ridge_minus_persistence_absolute_error": (
                    ridge_error - persistence_error
                ),
                "ridge_excess_error_share": (
                    (ridge_error - persistence_error) / total_excess
                    if total_excess > 0
                    else None
                ),
                "leave_one_out_persistence_mae": loo_persistence,
                "leave_one_out_ridge_mae": loo_ridge,
                "leave_one_out_ridge_minus_persistence_mae": (
                    loo_ridge - loo_persistence
                ),
                "scientific_conclusion_changes_without_battery": bool(
                    loo_ridge <= loo_persistence
                ),
            }
        )
    result = pd.DataFrame(rows)
    result["ridge_error_rank"] = (
        result["ridge_absolute_error_sum"]
        .rank(method="first", ascending=False)
        .astype(int)
    )
    result["ridge_excess_error_rank"] = (
        result["ridge_minus_persistence_absolute_error"]
        .rank(method="first", ascending=False)
        .astype(int)
    )
    return result.sort_values(
        ["ridge_error_rank", "group_reference"],
        kind="mergesort",
    ).reset_index(drop=True)


def _safe_correlation(left: pd.Series, right: pd.Series) -> float | None:
    frame = pd.DataFrame(
        {
            "left": pd.to_numeric(left, errors="coerce"),
            "right": pd.to_numeric(right, errors="coerce"),
        }
    ).dropna()
    if len(frame) < 3:
        return None
    if frame["left"].nunique() < 2 or frame["right"].nunique() < 2:
        return None
    value = frame["left"].corr(frame["right"])
    return float(value) if pd.notna(value) else None


def _local_trend_relationships(wide: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    variables = (
        "local_slope",
        "local_volatility",
        "capacity_current",
        "recent_monotonicity",
        "abrupt_change_proximity",
    )
    for model in ALLOWED_MODELS:
        absolute_error = np.abs(wide["actual"] - wide[model])
        for variable in variables:
            values = wide[variable].astype(float)
            rows.append(
                {
                    "model": model,
                    "diagnostic_variable": variable,
                    "prediction_count": len(wide),
                    "pearson_correlation_with_absolute_error": _safe_correlation(
                        values,
                        absolute_error,
                    ),
                    "rank_correlation_with_absolute_error": _safe_correlation(
                        values.rank(method="average"),
                        pd.Series(absolute_error).rank(method="average"),
                    ),
                    "causal_interpretation_allowed": False,
                }
            )
        abrupt = wide["abrupt_change_proximity"].astype(bool)
        rows.append(
            {
                "model": model,
                "diagnostic_variable": "abrupt_change_proximity_error_contrast",
                "prediction_count": len(wide),
                "pearson_correlation_with_absolute_error": None,
                "rank_correlation_with_absolute_error": None,
                "abrupt_proximity_prediction_count": int(abrupt.sum()),
                "abrupt_proximity_mae": (
                    float(np.mean(absolute_error[abrupt]))
                    if abrupt.any()
                    else None
                ),
                "no_abrupt_proximity_mae": (
                    float(np.mean(absolute_error[~abrupt]))
                    if (~abrupt).any()
                    else None
                ),
                "causal_interpretation_allowed": False,
            }
        )
    return pd.DataFrame(rows)


def _comparability_audit(
    source: pd.DataFrame,
    lineage: Mapping[str, Any],
    metadata_recovery: pd.DataFrame,
    config: BatteryForecastDiagnosticConfig,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    recovery = (
        metadata_recovery.set_index("metadata_field").to_dict(orient="index")
        if "metadata_field" in metadata_recovery.columns
        else {}
    )
    battery_count = int(source[config.group_column].nunique())
    temperature_supported = (
        "ambient_temperature_c" in source.columns
        and source["ambient_temperature_c"].notna().all()
    )
    variable_temperature_batteries = (
        int(
            (
                source.groupby(config.group_column)["ambient_temperature_c"]
                .nunique()
                .gt(1)
            ).sum()
        )
        if temperature_supported
        else 0
    )
    rows = [
        {
            "metadata_field": "source_package",
            "availability_status": "supported_immediate_upstream",
            "supported_battery_count": int(
                lineage.get("exact_lineage_cell_count", 0)
            ),
            "comparability_status": "restricted",
            "evidence": "verified local Kaggle package",
            "limitation": "official original NASA snapshot/version unresolved",
        },
        {
            "metadata_field": "battery_identifier",
            "availability_status": "supported",
            "supported_battery_count": battery_count,
            "comparability_status": "identity_only",
            "evidence": config.group_column,
            "limitation": "identity does not establish protocol comparability",
        },
        {
            "metadata_field": "nominal_capacity",
            "availability_status": "unresolved",
            "supported_battery_count": 0,
            "comparability_status": "not_established",
            "evidence": "reference capacity is derived by first_n_median",
            "limitation": "derived reference capacity is not nominal capacity",
        },
        {
            "metadata_field": "chemistry",
            "availability_status": "unresolved",
            "supported_battery_count": 0,
            "comparability_status": "not_established",
            "evidence": "not present in tracked analysis-ready artifact",
            "limitation": "chemistry equivalence cannot be verified",
        },
        {
            "metadata_field": "ambient_temperature",
            "availability_status": (
                "supported_with_variation"
                if temperature_supported
                else "unresolved"
            ),
            "supported_battery_count": battery_count if temperature_supported else 0,
            "comparability_status": "heterogeneous_observed_conditions",
            "evidence": "ambient_temperature_c",
            "limitation": (
                f"{variable_temperature_batteries} batteries span multiple "
                "recorded temperatures"
            ),
        },
        {
            "metadata_field": "charge_protocol",
            "availability_status": "group_level_partial",
            "supported_battery_count": int(
                lineage.get("protocol_document_cell_coverage", 0)
            ),
            "comparability_status": "not_established",
            "evidence": "local protocol documents",
            "limitation": "cycle-specific commanded protocol logs unavailable",
        },
        {
            "metadata_field": "discharge_protocol",
            "availability_status": "group_level_partial",
            "supported_battery_count": int(
                lineage.get("protocol_document_cell_coverage", 0)
            ),
            "comparability_status": "not_established",
            "evidence": "local protocol documents and measured signals",
            "limitation": "observed current is not a commanded protocol log",
        },
        {
            "metadata_field": "cutoff_voltage",
            "availability_status": "unresolved",
            "supported_battery_count": 0,
            "comparability_status": "not_established",
            "evidence": "not present in tracked analysis-ready artifact",
            "limitation": "cutoff policy cannot be verified per cycle",
        },
        {
            "metadata_field": "measurement_method",
            "availability_status": "partial",
            "supported_battery_count": battery_count,
            "comparability_status": "restricted",
            "evidence": "measured voltage/current/temperature summaries",
            "limitation": "calibration and uncertainty metadata unavailable",
        },
        {
            "metadata_field": "preprocessing_version",
            "availability_status": "supported_global_artifact",
            "supported_battery_count": battery_count,
            "comparability_status": "software_only",
            "evidence": f"lineage schema {lineage.get('schema_version', 'unknown')}",
            "limitation": "software version does not establish test comparability",
        },
    ]
    frame = pd.DataFrame(rows)
    unresolved = frame.loc[
        frame["comparability_status"].isin(
            ["not_established", "restricted", "heterogeneous_observed_conditions"]
        ),
        "metadata_field",
    ].tolist()
    summary = {
        "status": "comparability_not_established",
        "battery_count": battery_count,
        "recorded_temperature_count": (
            int(source["ambient_temperature_c"].nunique())
            if temperature_supported
            else 0
        ),
        "variable_temperature_battery_count": variable_temperature_batteries,
        "official_original_snapshot_status": lineage.get(
            "original_nasa_snapshot_status",
            "unresolved",
        ),
        "cycle_specific_protocol_status": recovery.get(
            "documented_protocol_group",
            {},
        ).get("limitation", "unresolved"),
        "unresolved_fields": sorted(unresolved),
        "same_condition_assumption_made": False,
    }
    return frame, summary


def _aggregate_metrics(
    wide: pd.DataFrame,
    source_result: Mapping[str, Any],
) -> list[dict[str, Any]]:
    aggregate: list[dict[str, Any]] = []
    source_by_model = {
        str(row["model"]): row for row in source_result["aggregate_metrics"]
    }
    for model in ALLOWED_MODELS:
        metrics = _metric_values(wide["actual"], wide[model])
        source = source_by_model[model]
        if (
            not math.isclose(
                float(metrics["mae"]),
                float(source["mae"]),
                rel_tol=0,
                abs_tol=1e-12,
            )
            or not math.isclose(
                float(metrics["rmse"]),
                float(source["rmse"]),
                rel_tol=0,
                abs_tol=1e-12,
            )
            or len(wide) != int(source["prediction_count"])
        ):
            raise ValueError(f"{model} metrics do not match source benchmark")
        aggregate.append(
            {
                "model": model,
                "prediction_count": len(wide),
                "mae": metrics["mae"],
                "rmse": metrics["rmse"],
                "r2": metrics["r2"],
                "source_benchmark_metric_preserved": True,
            }
        )
    return aggregate


def _physical_violation_analysis(
    wide: pd.DataFrame,
    config: BatteryForecastDiagnosticConfig,
) -> dict[str, Any]:
    persistence_error = np.abs(wide["actual"] - wide["persistence"])
    ridge_error = np.abs(wide["actual"] - wide["ridge"])
    excess = ridge_error - persistence_error
    ridge_violation = (
        (wide["ridge"] < config.physical_min)
        | (wide["ridge"] > config.physical_max)
    )
    persistence_violation = (
        (wide["persistence"] < config.physical_min)
        | (wide["persistence"] > config.physical_max)
    )
    ridge_error_sum = float(ridge_error.sum())
    excess_sum = float(excess.sum())
    return {
        "persistence_violation_count": int(persistence_violation.sum()),
        "ridge_violation_count": int(ridge_violation.sum()),
        "ridge_negative_prediction_count": int((wide["ridge"] < 0).sum()),
        "prediction_clipping_performed": False,
        "ridge_violation_absolute_error_share": (
            float(ridge_error[ridge_violation].sum()) / ridge_error_sum
            if ridge_error_sum > 0
            else None
        ),
        "ridge_violation_excess_error_share": (
            float(excess[ridge_violation].sum()) / excess_sum
            if excess_sum > 0
            else None
        ),
        "major_aggregate_failure_driver": bool(
            excess_sum > 0
            and float(excess[ridge_violation].sum()) / excess_sum >= 0.2
        ),
    }


def _influence_summary(
    influence: pd.DataFrame,
    per_battery: pd.DataFrame,
    wide: pd.DataFrame,
    config: BatteryForecastDiagnosticConfig,
) -> dict[str, Any]:
    top_ridge = influence.nsmallest(5, "ridge_error_rank")
    top_excess = influence.nsmallest(5, "ridge_excess_error_rank")
    sparse_references = set(
        per_battery.loc[
            per_battery["prediction_count"] <= config.sparse_prediction_max,
            "group_reference",
        ]
    )
    sparse = influence.loc[influence["group_reference"].isin(sparse_references)]
    total_excess = float(
        influence["ridge_minus_persistence_absolute_error"].sum()
    )
    sparse_excess = float(
        sparse["ridge_minus_persistence_absolute_error"].sum()
    )
    worst = per_battery.sort_values(
        ["ridge_mae", "group_reference"],
        ascending=[False, True],
        kind="mergesort",
    ).iloc[0]
    worst_influence = influence.loc[
        influence["group_reference"] == worst["group_reference"]
    ].iloc[0]
    return {
        "top_five_ridge_error_contributors": [
            {
                "group_reference": row["group_reference"],
                "ridge_absolute_error_contribution": row[
                    "ridge_absolute_error_contribution"
                ],
                "ridge_minus_persistence_absolute_error": row[
                    "ridge_minus_persistence_absolute_error"
                ],
            }
            for _, row in top_ridge.iterrows()
        ],
        "top_five_excess_error_contributors": [
            {
                "group_reference": row["group_reference"],
                "ridge_excess_error_share": row["ridge_excess_error_share"],
                "ridge_minus_persistence_absolute_error": row[
                    "ridge_minus_persistence_absolute_error"
                ],
            }
            for _, row in top_excess.iterrows()
        ],
        "top_one_ridge_error_concentration": float(
            top_ridge.head(1)["ridge_absolute_error_contribution"].sum()
        ),
        "top_three_ridge_error_concentration": float(
            top_ridge.head(3)["ridge_absolute_error_contribution"].sum()
        ),
        "top_five_ridge_error_concentration": float(
            top_ridge["ridge_absolute_error_contribution"].sum()
        ),
        "top_three_excess_error_concentration": float(
            top_excess.head(3)["ridge_minus_persistence_absolute_error"].sum()
            / total_excess
        ),
        "top_five_excess_error_concentration": float(
            top_excess["ridge_minus_persistence_absolute_error"].sum()
            / total_excess
        ),
        "leave_one_out_conclusion_change_count": int(
            influence["scientific_conclusion_changes_without_battery"].sum()
        ),
        "leave_one_out_ridge_minus_persistence_mae_min": float(
            influence["leave_one_out_ridge_minus_persistence_mae"].min()
        ),
        "leave_one_out_ridge_minus_persistence_mae_max": float(
            influence["leave_one_out_ridge_minus_persistence_mae"].max()
        ),
        "worst_ridge_mae_group_reference": worst["group_reference"],
        "worst_ridge_mae": float(worst["ridge_mae"]),
        "worst_persistence_mae": float(worst["persistence_mae"]),
        "worst_group_prediction_count": int(worst["prediction_count"]),
        "worst_group_exclusion_changes_conclusion": bool(
            worst_influence["scientific_conclusion_changes_without_battery"]
        ),
        "sparse_battery_count": len(sparse_references),
        "sparse_prediction_count": int(sparse["prediction_count"].sum()),
        "sparse_prediction_share": float(
            sparse["prediction_count"].sum() / len(wide)
        ),
        "sparse_excess_error_share": (
            sparse_excess / total_excess if total_excess > 0 else None
        ),
        "outlier_removal_performed": False,
        "analysis_role": "diagnostic_sensitivity_only",
    }


def _dominant_failure_modes(
    per_battery: pd.DataFrame,
) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for value in per_battery["diagnostic_classifications"]:
        for item in str(value).split(";"):
            if item:
                counts[item] = counts.get(item, 0) + 1
    return [
        {
            "failure_mode": key,
            "battery_count": counts[key],
            "classification_basis": "predeclared_deterministic_rules",
            "mechanism_diagnosis": False,
        }
        for key in sorted(counts, key=lambda item: (-counts[item], item))
    ]


def _scientific_closeout(
    aggregate: list[dict[str, Any]],
    influence_summary: Mapping[str, Any],
    regimes: pd.DataFrame,
    physical: Mapping[str, Any],
    comparability: Mapping[str, Any],
    wide: pd.DataFrame,
) -> dict[str, Any]:
    by_model = {row["model"]: row for row in aggregate}
    persistence_mae = float(by_model["persistence"]["mae"])
    ridge_mae = float(by_model["ridge"]["mae"])
    abrupt = wide["abrupt_change_proximity"].astype(bool)
    ridge_error = np.abs(wide["actual"] - wide["ridge"])
    persistence_error = np.abs(wide["actual"] - wide["persistence"])
    total_excess = float((ridge_error - persistence_error).sum())
    abrupt_excess = float(
        (ridge_error[abrupt] - persistence_error[abrupt]).sum()
    )
    ridge_worse_regimes = int(
        (regimes["ridge_minus_persistence_mae"] > 0).sum()
    )
    return {
        "status": "diagnostic",
        "evidence_level": "diagnostic_pattern_without_causal_explanation",
        "ridge_failure_concentrated_in_few_batteries": bool(
            influence_summary["top_five_excess_error_concentration"] >= 0.8
        ),
        "concentration_interpretation": (
            "excess error is concentrated, but no single-battery exclusion "
            "changes persistence superiority"
        ),
        "worst_battery_exclusion_preserves_persistence_advantage": bool(
            not influence_summary["worst_group_exclusion_changes_conclusion"]
        ),
        "sparse_groups_are_primary_driver": bool(
            influence_summary["sparse_excess_error_share"] is not None
            and influence_summary["sparse_excess_error_share"] >= 0.2
        ),
        "ridge_worse_regime_count": ridge_worse_regimes,
        "regime_count": len(regimes),
        "abrupt_proximity_prediction_count": int(abrupt.sum()),
        "abrupt_proximity_excess_error_share": (
            abrupt_excess / total_excess if total_excess > 0 else None
        ),
        "abrupt_transitions_are_primary_driver": bool(
            total_excess > 0 and abrupt_excess / total_excess >= 0.5
        ),
        "physical_violations_are_primary_driver": bool(
            physical["major_aggregate_failure_driver"]
        ),
        "comparability_status": comparability["status"],
        "persistence_mae": persistence_mae,
        "ridge_mae": ridge_mae,
        "ridge_relative_mae_worsening_percent": (
            100.0 * (ridge_mae - persistence_mae) / persistence_mae
        ),
        "most_supported_explanation": (
            "short-horizon persistence strength plus battery-dependent linear "
            "model mismatch; heterogeneous source conditions remain unresolved"
        ),
        "next_model_experiment_status": (
            "not_justified_without_comparability_metadata_and_predeclared_validation"
        ),
        "predictive_generalization_claim_allowed": False,
        "mechanism_claim_allowed": False,
        "engineering_claim_allowed": False,
    }


def _analyze(
    inputs: Mapping[str, Any],
    config: BatteryForecastDiagnosticConfig,
) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    source = inputs["source"].copy(deep=True)
    predictions = inputs["predictions"].copy(deep=True)
    wide = _prepare_prediction_origins(predictions, source, config)
    quality = _trajectory_quality(source, config)
    regimes = _regime_metrics(wide, config)
    per_battery = _per_battery_diagnostics(
        wide,
        quality,
        config,
    )
    influence = _influence_analysis(wide, per_battery)
    relationships = _local_trend_relationships(wide)
    comparability_frame, comparability = _comparability_audit(
        source,
        inputs["lineage"],
        inputs["metadata_recovery"],
        config,
    )
    aggregate = _aggregate_metrics(wide, inputs["benchmark_result"])
    physical = _physical_violation_analysis(wide, config)
    influence_summary = _influence_summary(
        influence,
        per_battery,
        wide,
        config,
    )
    dominant = _dominant_failure_modes(per_battery)
    closeout = _scientific_closeout(
        aggregate,
        influence_summary,
        regimes,
        physical,
        comparability,
        wide,
    )
    result = {
        "schema_version": DIAGNOSTIC_VERSION,
        "artifact_kind": "battery_forecast_failure_diagnostic_result",
        "diagnostic_id": DIAGNOSTIC_ID,
        "case_study_id": config.case_study_id,
        "source_benchmark_reference": config.source_benchmark_summary_path,
        "source_benchmark_checksum": config.expected_benchmark_summary_checksum,
        "source_benchmark_result_reference": config.source_benchmark_result_path,
        "source_benchmark_result_checksum": (
            config.expected_benchmark_result_checksum
        ),
        "source_predictions_reference": config.source_predictions_path,
        "source_predictions_sha256": file_sha256(
            inputs["paths"]["predictions"]
        ),
        "source_analysis_ready_reference": config.source_analysis_ready_path,
        "source_analysis_ready_sha256": file_sha256(
            inputs["paths"]["analysis_ready"]
        ),
        "source_lineage_reference": config.source_lineage_path,
        "evaluation_scenario": "warm_start_cross_battery",
        "forecast_horizon_cycles": config.horizon,
        "battery_count": len(per_battery),
        "prediction_count": len(wide),
        "aggregate_metrics": aggregate,
        "influence_summary": influence_summary,
        "per_battery_diagnostics": per_battery.to_dict(orient="records"),
        "influence_analysis": influence.to_dict(orient="records"),
        "trajectory_quality_flags": quality.to_dict(orient="records"),
        "degradation_regime_metrics": regimes.to_dict(orient="records"),
        "local_trend_relationships": relationships.to_dict(orient="records"),
        "physical_violation_analysis": physical,
        "comparability_readiness": comparability,
        "dominant_failure_modes": dominant,
        "unresolved_information": [
            "official original NASA snapshot/version",
            "battery chemistry",
            "nominal capacity",
            "cycle-specific charge and discharge command logs",
            "cutoff voltage policy",
            "measurement calibration and uncertainty",
            "independent external battery validation",
        ],
        "recommendations": [
            "retain persistence as the benchmark reference",
            "do not exclude high-error batteries from the official benchmark",
            "resolve protocol, chemistry, cutoff, and calibration comparability",
            "audit abrupt transitions against source measurements",
            "predeclare any future model family and external validation",
        ],
        "prohibited_claims": [
            "degradation mechanism identified",
            "battery-level predictive generalization validated",
            "SOH, RUL, or lifetime predicted",
            "bad batteries justify exclusion",
            "source conditions are comparable",
            "engineering or production decision supported",
        ],
        "scientific_closeout": closeout,
        "diagnostic_thresholds": {
            "sparse_prediction_max": config.sparse_prediction_max,
            "abrupt_change_threshold_percent_points": (
                config.abrupt_change_threshold
            ),
            "high_target_std_threshold_percent_points": (
                config.high_target_std_threshold
            ),
            "low_target_std_threshold_percent_points": (
                config.low_target_std_threshold
            ),
            "high_local_volatility_threshold_percent_points": (
                config.high_local_volatility_threshold
            ),
            "flat_range_threshold_percent_points": config.flat_range_threshold,
            "flat_window": config.flat_window,
            "physical_bounds_percent": [
                config.physical_min,
                config.physical_max,
            ],
        },
        "regime_policy": {
            "early": f"prediction_origin <= {config.regime_early_max_cycle}",
            "middle": (
                f"{config.regime_early_max_cycle} < prediction_origin <= "
                f"{config.regime_middle_max_cycle}"
            ),
            "late": f"prediction_origin > {config.regime_middle_max_cycle}",
            "future_target_used": False,
        },
        "network_called": False,
        "credentials_read": False,
        "source_mutation_performed": False,
        "model_retrained": False,
        "source_benchmark_model_reexecuted": (
            config.source_benchmark_execution_status
            == "reexecuted_same_config_for_diagnostics"
        ),
    }
    frames = {
        "per_battery_diagnostics": per_battery,
        "influence_analysis": influence,
        "regime_metrics": regimes,
        "trajectory_quality_flags": quality,
        "local_trend_relationships": relationships,
        "comparability_audit": comparability_frame,
    }
    return _json_safe(result), frames


def preview_diagnostics(
    config: BatteryForecastDiagnosticConfig,
    repo_root: str | Path = ".",
) -> dict[str, Any]:
    paths = _input_paths(config, repo_root)
    missing = [
        path.relative_to(Path(repo_root).resolve()).as_posix()
        for path in paths.values()
        if not path.is_file()
    ]
    if missing:
        return {
            "schema_version": DIAGNOSTIC_VERSION,
            "diagnostic_id": DIAGNOSTIC_ID,
            "status": "blocked_missing_input",
            "required_inputs": {
                key: path.relative_to(Path(repo_root).resolve()).as_posix()
                for key, path in sorted(paths.items())
            },
            "missing_inputs": missing,
            "writes_performed": False,
            "model_retrained": False,
            "network_called": False,
            "credentials_read": False,
        }
    inputs = _load_inputs(config, repo_root)
    return {
        "schema_version": DIAGNOSTIC_VERSION,
        "diagnostic_id": DIAGNOSTIC_ID,
        "status": "ready",
        "source_benchmark_reference": config.source_benchmark_summary_path,
        "source_benchmark_checksum": config.expected_benchmark_summary_checksum,
        "source_benchmark_result_checksum": (
            config.expected_benchmark_result_checksum
        ),
        "source_predictions_reference": config.source_predictions_path,
        "source_predictions_sha256": file_sha256(paths["predictions"]),
        "source_analysis_ready_reference": config.source_analysis_ready_path,
        "source_analysis_ready_sha256": file_sha256(paths["analysis_ready"]),
        "battery_count": int(
            inputs["predictions"]["group_reference"].nunique()
        ),
        "prediction_count": int(len(inputs["predictions"]) / len(ALLOWED_MODELS)),
        "evaluation_scenario": "warm_start_cross_battery",
        "forecast_horizon_cycles": config.horizon,
        "planned_outputs": [
            f"{config.output_root}/diagnostic_summary.json",
            f"{config.output_root}/per_battery_diagnostics.csv",
            f"{config.output_root}/influence_analysis.csv",
            f"{config.output_root}/regime_metrics.csv",
            f"{config.output_root}/trajectory_quality_flags.csv",
            f"{config.output_root}/local_trend_relationships.csv",
            f"{config.output_root}/comparability_audit.csv",
            config.tracked_summary_path,
        ],
        "writes_performed": False,
        "model_retrained": False,
        "source_benchmark_model_reexecuted": (
            config.source_benchmark_execution_status
            == "reexecuted_same_config_for_diagnostics"
        ),
        "network_called": False,
        "credentials_read": False,
    }


def compact_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    compact = {
        key: result[key]
        for key in (
            "schema_version",
            "diagnostic_id",
            "case_study_id",
            "source_benchmark_reference",
            "source_benchmark_checksum",
            "source_benchmark_result_checksum",
            "source_predictions_sha256",
            "source_analysis_ready_reference",
            "source_analysis_ready_sha256",
            "evaluation_scenario",
            "forecast_horizon_cycles",
            "battery_count",
            "prediction_count",
            "aggregate_metrics",
            "influence_summary",
            "degradation_regime_metrics",
            "physical_violation_analysis",
            "comparability_readiness",
            "dominant_failure_modes",
            "unresolved_information",
            "recommendations",
            "prohibited_claims",
            "scientific_closeout",
            "diagnostic_thresholds",
            "regime_policy",
            "network_called",
            "credentials_read",
            "source_mutation_performed",
            "model_retrained",
            "source_benchmark_model_reexecuted",
            "first_run_checksum",
            "second_run_checksum",
            "deterministic_rerun_match",
        )
    }
    compact["artifact_kind"] = (
        "battery_forecast_failure_diagnostic_compact_summary"
    )
    compact["deterministic_result_checksum"] = canonical_checksum(compact)
    return _json_safe(compact)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _atomic_write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    try:
        frame.to_csv(temporary, index=False, lineterminator="\n")
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _write_outputs(
    result: Mapping[str, Any],
    frames: Mapping[str, pd.DataFrame],
    config: BatteryForecastDiagnosticConfig,
    repo_root: str | Path,
    *,
    write_tracked_summary: bool,
) -> list[str]:
    output_root = resolve_repo_path(repo_root, config.output_root)
    paths = {
        "diagnostic_summary": output_root / "diagnostic_summary.json",
        "per_battery_diagnostics": output_root / "per_battery_diagnostics.csv",
        "influence_analysis": output_root / "influence_analysis.csv",
        "regime_metrics": output_root / "regime_metrics.csv",
        "trajectory_quality_flags": output_root / "trajectory_quality_flags.csv",
        "local_trend_relationships": output_root / "local_trend_relationships.csv",
        "comparability_audit": output_root / "comparability_audit.csv",
    }
    _atomic_write_text(paths["diagnostic_summary"], canonical_json(result))
    for key in (
        "per_battery_diagnostics",
        "influence_analysis",
        "regime_metrics",
        "trajectory_quality_flags",
        "local_trend_relationships",
        "comparability_audit",
    ):
        _atomic_write_frame(paths[key], frames[key])
    written = [
        path.relative_to(Path(repo_root).resolve()).as_posix()
        for path in paths.values()
    ]
    if write_tracked_summary:
        tracked_path = resolve_repo_path(repo_root, config.tracked_summary_path)
        _atomic_write_text(
            tracked_path,
            canonical_json(compact_summary(result)),
        )
        written.append(config.tracked_summary_path)
    return written


def run_diagnostics(
    config: BatteryForecastDiagnosticConfig,
    repo_root: str | Path = ".",
    *,
    write_outputs: bool = True,
    write_tracked_summary: bool = True,
) -> dict[str, Any]:
    inputs = _load_inputs(config, repo_root)
    input_paths = inputs["paths"]
    hashes_before = {
        key: file_sha256(path)
        for key, path in sorted(input_paths.items())
    }
    first, frames = _analyze(inputs, config)
    second, _ = _analyze(inputs, config)
    first_checksum = canonical_checksum(first)
    second_checksum = canonical_checksum(second)
    if first_checksum != second_checksum:
        raise ValueError("deterministic repeated diagnostic checksum mismatch")
    hashes_after = {
        key: file_sha256(path)
        for key, path in sorted(input_paths.items())
    }
    if hashes_before != hashes_after:
        raise ValueError("diagnostic source artifact changed during execution")
    result = {
        **first,
        "first_run_checksum": first_checksum,
        "second_run_checksum": second_checksum,
        "deterministic_rerun_match": True,
        "source_hashes_before": hashes_before,
        "source_hashes_after": hashes_after,
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
        "result": _json_safe(result),
        "frames": frames,
        "written": written,
        "network_called": False,
        "credentials_read": False,
        "source_mutation_performed": False,
        "model_retrained": False,
    }


def _validate_contribution_consistency(
    payload: Mapping[str, Any],
    errors: list[str],
) -> None:
    influence = payload.get("influence_analysis")
    per_battery = payload.get("per_battery_diagnostics")
    aggregate = payload.get("aggregate_metrics")
    if not isinstance(influence, list) or not isinstance(per_battery, list):
        errors.append("detailed diagnostic rows are missing")
        return
    if len(influence) != int(payload.get("battery_count", -1)):
        errors.append("influence battery count mismatch")
    if len(per_battery) != int(payload.get("battery_count", -1)):
        errors.append("per-battery diagnostic count mismatch")
    if not influence:
        errors.append("influence analysis is empty")
        return
    prediction_share = sum(
        float(row["prediction_count_contribution"]) for row in influence
    )
    if not math.isclose(prediction_share, 1.0, rel_tol=0, abs_tol=1e-10):
        errors.append("prediction-count contributions do not sum to one")
    total_predictions = sum(int(row["prediction_count"]) for row in influence)
    if total_predictions != int(payload.get("prediction_count", -1)):
        errors.append("influence prediction count mismatch")
    by_model = {
        str(row["model"]): row
        for row in aggregate
    } if isinstance(aggregate, list) else {}
    for model in ALLOWED_MODELS:
        if model not in by_model:
            errors.append(f"aggregate metric missing model: {model}")
            continue
        absolute_error_sum = sum(
            float(row[f"{model}_absolute_error_sum"]) for row in influence
        )
        expected = (
            float(by_model[model]["mae"])
            * int(by_model[model]["prediction_count"])
        )
        if not math.isclose(
            absolute_error_sum,
            expected,
            rel_tol=0,
            abs_tol=1e-8,
        ):
            errors.append(f"{model} absolute-error contribution mismatch")


def validate_result_payload(
    payload: Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    artifact_kind = payload.get("artifact_kind")
    expected_fields = (
        RESULT_FIELDS
        if artifact_kind == "battery_forecast_failure_diagnostic_result"
        else COMPACT_FIELDS
        if artifact_kind
        == "battery_forecast_failure_diagnostic_compact_summary"
        else set()
    )
    if not expected_fields:
        errors.append("unknown diagnostic artifact_kind")
    else:
        unknown = sorted(set(payload) - expected_fields)
        missing = sorted(expected_fields - set(payload))
        if unknown:
            errors.append("unknown result field(s): " + ", ".join(unknown))
        if missing:
            errors.append("missing result field(s): " + ", ".join(missing))
    if payload.get("schema_version") != DIAGNOSTIC_VERSION:
        errors.append("unsupported diagnostic schema_version")
    if payload.get("diagnostic_id") != DIAGNOSTIC_ID:
        errors.append("unexpected diagnostic_id")
    if payload.get("evaluation_scenario") != "warm_start_cross_battery":
        errors.append("unexpected evaluation scenario")
    if payload.get("forecast_horizon_cycles") != 5:
        errors.append("forecast horizon changed")
    if payload.get("model_retrained") is not False:
        errors.append("diagnostic model retraining is prohibited")
    if payload.get("network_called") is not False:
        errors.append("network execution is prohibited")
    if payload.get("credentials_read") is not False:
        errors.append("credential access is prohibited")
    if payload.get("source_mutation_performed") is not False:
        errors.append("source mutation is prohibited")
    if _contains_absolute_path(payload):
        errors.append("result contains an absolute path")
    try:
        _scan_for_secrets(payload, key_path="result")
    except ValueError as exc:
        errors.append(str(exc))
    checksum_payload = dict(payload)
    recorded = checksum_payload.pop("deterministic_result_checksum", None)
    if recorded != canonical_checksum(checksum_payload):
        errors.append("deterministic checksum mismatch")
    if artifact_kind == "battery_forecast_failure_diagnostic_result":
        _validate_contribution_consistency(payload, errors)
        if payload.get("source_hashes_before") != payload.get(
            "source_hashes_after"
        ):
            errors.append("source non-mutation hashes do not match")
    if repo_root is not None and payload.get("source_benchmark_reference"):
        try:
            source_path = resolve_repo_path(
                repo_root,
                str(payload["source_benchmark_reference"]),
            )
            source_payload = _load_json(source_path)
            source_validation = validate_forecast_result_payload(source_payload)
            if not source_validation["valid"]:
                errors.append("referenced source benchmark is invalid")
            elif (
                source_payload.get("deterministic_result_checksum")
                != payload.get("source_benchmark_checksum")
            ):
                errors.append("source benchmark checksum mismatch")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"source benchmark validation failed: {exc}")
    return {
        "schema_version": DIAGNOSTIC_VERSION,
        "status": "valid" if not errors else "invalid",
        "valid": not errors,
        "errors": errors,
    }


def validate_result_file(
    path: str | Path,
    repo_root: str | Path = ".",
) -> dict[str, Any]:
    result_path = resolve_repo_path(repo_root, path)
    payload = _load_json(result_path)
    return validate_result_payload(payload, repo_root=repo_root)
