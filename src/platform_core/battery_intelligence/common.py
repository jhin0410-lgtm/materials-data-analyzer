"""Contracts and input validation for Battery Degradation Intelligence."""
from __future__ import annotations
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import numpy as np
import pandas as pd

SCHEMA_VERSION = "1.0"
ARTIFACT_KIND = "battery_degradation_intelligence"
DEFAULT_TARGET = "capacity_retention_percent"
DEFAULT_GROUP = "battery_id"
DEFAULT_CYCLE = "cycle_index"
DEFAULT_HORIZON = 5
DEFAULT_LAGS = (1, 2, 3)
DEFAULT_ROLLING_WINDOW = 5
DEFAULT_CONFORMAL_COVERAGE = 0.90
DEFAULT_PLAUSIBILITY_RANGE = (0.0, 150.0)
RAW_REQUIRED_COLUMNS = {"battery_id", "cycle_index", "step_type", "elapsed_time_s", "voltage_v", "current_a"}
RAW_OPTIONAL_COLUMNS = {"temperature_c", "capacity_ah", "global_time_s"}
STEP_ALIASES = {
    "charge": "charge", "charging": "charge", "charge_cc": "charge_cc",
    "cc_charge": "charge_cc", "charge_cv": "charge_cv", "cv_charge": "charge_cv",
    "discharge": "discharge", "discharging": "discharge", "rest": "rest",
    "impedance": "impedance",
}


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
        value = float(value)
        return value if math.isfinite(value) else None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n"


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dataframe_checksum(frame: pd.DataFrame) -> str:
    normalized = frame.copy()
    normalized = normalized.reindex(sorted(normalized.columns), axis=1)
    encoded = normalized.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class BatteryIntelligenceConfig:
    group_column: str = DEFAULT_GROUP
    cycle_column: str = DEFAULT_CYCLE
    target_column: str = DEFAULT_TARGET
    horizon: int = DEFAULT_HORIZON
    lags: tuple[int, ...] = DEFAULT_LAGS
    rolling_window: int = DEFAULT_ROLLING_WINDOW
    n_splits: int = 5
    ridge_alpha: float = 1.0
    conformal_coverage: float = DEFAULT_CONFORMAL_COVERAGE
    plausibility_min: float = DEFAULT_PLAUSIBILITY_RANGE[0]
    plausibility_max: float = DEFAULT_PLAUSIBILITY_RANGE[1]
    minimum_trajectory_points: int = 12
    knee_min_segment: int = 5
    knee_bootstrap_samples: int = 200
    random_seed: int = 42

    def validate(self) -> None:
        if not self.group_column or not self.cycle_column or not self.target_column:
            raise ValueError("group, cycle, and target column names must be non-empty")
        if self.horizon < 1 or self.horizon > 100:
            raise ValueError("horizon must be in the bounded range 1..100")
        if not self.lags or tuple(sorted(set(self.lags))) != self.lags:
            raise ValueError("lags must be unique positive integers in ascending order")
        if any(lag < 1 for lag in self.lags):
            raise ValueError("lags must be positive")
        if self.rolling_window < 2:
            raise ValueError("rolling_window must be at least 2")
        if self.n_splits < 2 or self.n_splits > 20:
            raise ValueError("n_splits must be in the bounded range 2..20")
        if not math.isfinite(self.ridge_alpha) or self.ridge_alpha <= 0:
            raise ValueError("ridge_alpha must be finite and positive")
        if not 0.5 < self.conformal_coverage < 1.0:
            raise ValueError("conformal_coverage must be between 0.5 and 1.0")
        if not self.plausibility_min < self.plausibility_max:
            raise ValueError("plausibility bounds must be increasing")
        if self.minimum_trajectory_points < 6:
            raise ValueError("minimum_trajectory_points must be at least 6")
        if self.knee_min_segment < 3:
            raise ValueError("knee_min_segment must be at least 3")
        if self.knee_bootstrap_samples < 0 or self.knee_bootstrap_samples > 5000:
            raise ValueError("knee_bootstrap_samples must be in the range 0..5000")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return _json_safe(self.__dict__)


def _quality_flag(
    rows: list[dict[str, Any]],
    *,
    severity: str,
    code: str,
    message: str,
    battery_id: Any = None,
    cycle_index: Any = None,
    field: str | None = None,
    value: Any = None,
) -> None:
    rows.append(
        {
            "severity": severity,
            "code": code,
            "message": message,
            "battery_id": battery_id,
            "cycle_index": cycle_index,
            "field": field,
            "value": value,
        }
    )


def validate_cycle_summary(
    frame: pd.DataFrame,
    config: BatteryIntelligenceConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    config.validate()
    required = {config.group_column, config.cycle_column, config.target_column}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("cycle summary missing required columns: " + ", ".join(missing))
    if frame.empty:
        raise ValueError("cycle summary must contain at least one row")

    cleaned = frame.copy()
    flags: list[dict[str, Any]] = []
    if cleaned[config.group_column].isna().any():
        raise ValueError("cycle summary contains missing battery identifiers")

    for column in (config.cycle_column, config.target_column):
        converted = pd.to_numeric(cleaned[column], errors="coerce")
        introduced = int((converted.isna() & cleaned[column].notna()).sum())
        if introduced:
            raise ValueError(f"cycle summary contains non-numeric values in {column}")
        cleaned[column] = converted

    if cleaned[config.cycle_column].isna().any() or cleaned[config.target_column].isna().any():
        raise ValueError("cycle and target columns may not contain missing values")
    if (~np.isfinite(cleaned[config.cycle_column])).any() or (
        ~np.isfinite(cleaned[config.target_column])
    ).any():
        raise ValueError("cycle and target values must be finite")

    duplicate_mask = cleaned.duplicated(
        subset=[config.group_column, config.cycle_column], keep=False
    )
    if duplicate_mask.any():
        examples = cleaned.loc[
            duplicate_mask, [config.group_column, config.cycle_column]
        ].head(5)
        raise ValueError(
            "duplicate battery-cycle rows are ambiguous: "
            + examples.to_dict(orient="records").__repr__()
        )

    original_order = cleaned[[config.group_column, config.cycle_column]].copy()
    cleaned = cleaned.sort_values(
        [config.group_column, config.cycle_column], kind="mergesort"
    ).reset_index(drop=True)
    reordered = not original_order.reset_index(drop=True).equals(
        cleaned[[config.group_column, config.cycle_column]]
    )
    if reordered:
        _quality_flag(
            flags,
            severity="warning",
            code="cycle_rows_reordered",
            message="Rows were stably sorted by battery and cycle; source order was retained in the audit only.",
        )

    low = cleaned[config.target_column] < config.plausibility_min
    high = cleaned[config.target_column] > config.plausibility_max
    for index in cleaned.index[low | high]:
        row = cleaned.loc[index]
        _quality_flag(
            flags,
            severity="warning",
            code="target_outside_plausibility_range",
            message="Target lies outside the configured diagnostic plausibility range; the row was retained.",
            battery_id=row[config.group_column],
            cycle_index=row[config.cycle_column],
            field=config.target_column,
            value=row[config.target_column],
        )

    optional_numeric_ranges: dict[str, tuple[float | None, float | None]] = {
        "discharge_capacity_ah": (0.0, None),
        "reference_capacity_ah": (0.0, None),
        "internal_resistance_ohm": (0.0, None),
        "ambient_temperature_c": (-100.0, 200.0),
    }
    for column, (minimum, maximum) in optional_numeric_ranges.items():
        if column not in cleaned.columns:
            continue
        converted = pd.to_numeric(cleaned[column], errors="coerce")
        invalid_text = converted.isna() & cleaned[column].notna()
        for index in cleaned.index[invalid_text]:
            row = cleaned.loc[index]
            _quality_flag(
                flags,
                severity="warning",
                code="optional_numeric_parse_failure",
                message="Optional numeric value could not be parsed and was retained as missing in the validated copy.",
                battery_id=row[config.group_column],
                cycle_index=row[config.cycle_column],
                field=column,
                value=row[column],
            )
        cleaned[column] = converted
        invalid_range = pd.Series(False, index=cleaned.index)
        if minimum is not None:
            invalid_range |= converted <= minimum
        if maximum is not None:
            invalid_range |= converted > maximum
        invalid_range &= converted.notna()
        for index in cleaned.index[invalid_range]:
            row = cleaned.loc[index]
            _quality_flag(
                flags,
                severity="warning",
                code="optional_numeric_outside_expected_range",
                message="Optional physical quantity is outside the broad diagnostic range; the value was retained.",
                battery_id=row[config.group_column],
                cycle_index=row[config.cycle_column],
                field=column,
                value=row[column],
            )

    group_counts = cleaned.groupby(config.group_column, sort=True).size()
    cycle_gaps = 0
    non_increasing = 0
    for battery_id, group in cleaned.groupby(config.group_column, sort=True):
        cycles = group[config.cycle_column].to_numpy(dtype=float)
        differences = np.diff(cycles)
        if np.any(differences <= 0):
            non_increasing += 1
            _quality_flag(
                flags,
                severity="fatal",
                code="non_increasing_cycles",
                message="Cycle indices are not strictly increasing after sorting.",
                battery_id=battery_id,
            )
        gap_count = int(np.sum(differences > 1))
        cycle_gaps += gap_count
        if gap_count:
            _quality_flag(
                flags,
                severity="warning",
                code="cycle_gaps_present",
                message="One or more cycle-index gaps are present; exact-horizon targets require observed matching cycles.",
                battery_id=battery_id,
                value=gap_count,
            )
    if non_increasing:
        raise ValueError("cycle indices must be strictly increasing within each battery")

    summary = {
        "row_count": int(len(cleaned)),
        "battery_count": int(cleaned[config.group_column].nunique()),
        "minimum_rows_per_battery": int(group_counts.min()),
        "maximum_rows_per_battery": int(group_counts.max()),
        "cycle_gap_count": int(cycle_gaps),
        "quality_flag_count": int(len(flags)),
        "fatal_flag_count": int(sum(item["severity"] == "fatal" for item in flags)),
        "warning_flag_count": int(sum(item["severity"] == "warning" for item in flags)),
        "data_checksum": dataframe_checksum(cleaned),
    }
    return cleaned, pd.DataFrame(flags), summary


def validate_raw_signal(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    missing = sorted(RAW_REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError("raw signal table missing required columns: " + ", ".join(missing))
    if frame.empty:
        raise ValueError("raw signal table must contain at least one row")

    cleaned = frame.copy()
    flags: list[dict[str, Any]] = []
    if cleaned["battery_id"].isna().any() or cleaned["step_type"].isna().any():
        raise ValueError("raw signal table contains missing battery_id or step_type")

    cleaned["step_type"] = (
        cleaned["step_type"].astype(str).str.strip().str.lower().map(STEP_ALIASES)
    )
    if cleaned["step_type"].isna().any():
        unknown = sorted(
            set(frame.loc[cleaned["step_type"].isna(), "step_type"].astype(str))
        )
        raise ValueError("unrecognized raw-signal step_type values: " + ", ".join(unknown))

    if "step_id" in cleaned.columns:
        if cleaned["step_id"].isna().any():
            raise ValueError("raw signal step_id may not contain missing values")
        cleaned["step_id"] = cleaned["step_id"].astype(str).str.strip()
        if (cleaned["step_id"] == "").any():
            raise ValueError("raw signal step_id may not be blank")
    else:
        cleaned["step_id"] = cleaned["step_type"]
        _quality_flag(
            flags,
            severity="info",
            code="step_id_not_supplied",
            message=(
                "step_id was not supplied; each step_type must occur as one "
                "continuous elapsed-time segment per battery-cycle."
            ),
        )

    numeric_columns = ["cycle_index", "elapsed_time_s", "voltage_v", "current_a"]
    numeric_columns += [column for column in RAW_OPTIONAL_COLUMNS if column in cleaned]
    for column in numeric_columns:
        converted = pd.to_numeric(cleaned[column], errors="coerce")
        if converted.isna().any() or (~np.isfinite(converted)).any():
            raise ValueError(f"raw signal column {column} must contain finite numeric values")
        cleaned[column] = converted

    if (cleaned["elapsed_time_s"] < 0).any():
        raise ValueError("elapsed_time_s may not be negative")
    if (cleaned["voltage_v"] <= 0).any():
        raise ValueError("voltage_v must be positive")

    duplicate_mask = cleaned.duplicated(
        subset=["battery_id", "cycle_index", "step_id", "step_type", "elapsed_time_s"],
        keep=False,
    )
    if duplicate_mask.any():
        raise ValueError(
            "raw signal contains duplicate battery-cycle-step-time rows; integration would be ambiguous"
        )

    original_keys = cleaned[
        ["battery_id", "cycle_index", "step_id", "step_type", "elapsed_time_s"]
    ].copy()
    cleaned = cleaned.sort_values(
        ["battery_id", "cycle_index", "step_id", "step_type", "elapsed_time_s"],
        kind="mergesort",
    ).reset_index(drop=True)
    if not original_keys.reset_index(drop=True).equals(
        cleaned[["battery_id", "cycle_index", "step_id", "step_type", "elapsed_time_s"]]
    ):
        _quality_flag(
            flags,
            severity="warning",
            code="raw_signal_rows_reordered",
            message="Raw signal rows were stably sorted for integration; original ordering was not used as evidence.",
        )

    for keys, group in cleaned.groupby(
        ["battery_id", "cycle_index", "step_id", "step_type"], sort=True
    ):
        times = group["elapsed_time_s"].to_numpy(dtype=float)
        if np.any(np.diff(times) <= 0):
            raise ValueError(
                "elapsed_time_s must be strictly increasing within each battery-cycle-step"
            )
        if len(group) < 2:
            _quality_flag(
                flags,
                severity="warning",
                code="single_point_step",
                message="A step has fewer than two points and cannot be integrated.",
                battery_id=keys[0],
                cycle_index=keys[1],
                field="step_type",
                value=f"{keys[2]}:{keys[3]}",
            )

    if "temperature_c" not in cleaned.columns:
        _quality_flag(
            flags,
            severity="info",
            code="temperature_signal_unavailable",
            message="temperature_c was not supplied; thermal features will remain unavailable.",
        )
    if "capacity_ah" not in cleaned.columns:
        _quality_flag(
            flags,
            severity="info",
            code="capacity_signal_unavailable",
            message="capacity_ah was not supplied; incremental-capacity features will remain unavailable.",
        )

    summary = {
        "row_count": int(len(cleaned)),
        "battery_count": int(cleaned["battery_id"].nunique()),
        "cycle_count": int(
            cleaned[["battery_id", "cycle_index"]].drop_duplicates().shape[0]
        ),
        "step_types": sorted(cleaned["step_type"].unique().tolist()),
        "step_id_supplied": "step_id" in frame.columns,
        "step_count": int(
            cleaned[["battery_id", "cycle_index", "step_id"]]
            .drop_duplicates()
            .shape[0]
        ),
        "quality_flag_count": int(len(flags)),
        "data_checksum": dataframe_checksum(cleaned),
    }
    return cleaned, pd.DataFrame(flags), summary
