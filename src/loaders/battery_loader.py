"""Battery aging dataset loader helpers.

This module prepares NASA/Kaggle-style battery aging raw files for the existing
tabular analyzer modes. It does not download data and does not assume raw data
is committed to the repository.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from domain_constraints import DomainConstraint, validate_domain_constraints


BATTERY_SUMMARY_COLUMNS = [
    "battery_id",
    "cycle_index",
    "ambient_temperature_c",
    "discharge_capacity_ah",
    "capacity_retention_percent",
    "internal_resistance_ohm",
    "failed",
]

BATTERY_SUMMARY_CONSTRAINTS = [
    DomainConstraint(
        column="cycle_index",
        min_value=0,
        description="Cycle index should be non-negative.",
    ),
    DomainConstraint(
        column="discharge_capacity_ah",
        min_value=0,
        description="Discharge capacity should not be negative.",
    ),
    DomainConstraint(
        column="capacity_retention_percent",
        min_value=0,
        max_value=120,
        description=(
            "Capacity retention is expected to stay in a conservative "
            "0-120 percent screening range."
        ),
    ),
    DomainConstraint(
        column="internal_resistance_ohm",
        min_value=0,
        description="Internal resistance should not be negative.",
    ),
]


def load_nasa_mat_file(path: str | Path) -> dict[str, Any]:
    """Load a NASA battery aging MATLAB file with scipy.io.loadmat.

    SciPy is optional for this project. Install it in the local environment only
    when raw MATLAB files need to be preprocessed.
    """
    mat_path = Path(path)
    if not mat_path.exists():
        raise FileNotFoundError(f"Battery raw file was not found: {mat_path}")

    try:
        from scipy.io import loadmat
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "SciPy is required to load MATLAB .mat battery files.\n"
            "Install it in your environment with: pip install scipy\n"
            "Do not commit API keys, Kaggle credentials, or large raw datasets."
        ) from exc

    return loadmat(mat_path, squeeze_me=True, struct_as_record=False)


def is_mat_struct(value: Any) -> bool:
    """Return True for scipy MATLAB struct-like objects."""
    return hasattr(value, "_fieldnames")


def unwrap_scalar(value: Any) -> Any:
    """Unwrap MATLAB/numpy scalar containers into plain Python values."""
    if isinstance(value, np.ndarray):
        squeezed = np.squeeze(value)
        if squeezed.shape == ():
            return unwrap_scalar(squeezed.item())
        return squeezed
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def get_field(value: Any, field_name: str, default: Any = None) -> Any:
    """Read a field from dicts, scipy mat_structs, or numpy structured values."""
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(field_name, default)
    if is_mat_struct(value) and field_name in getattr(value, "_fieldnames", []):
        return getattr(value, field_name)
    if hasattr(value, field_name):
        return getattr(value, field_name)
    if isinstance(value, np.void) and value.dtype.names and field_name in value.dtype.names:
        return value[field_name]
    return default


def iter_mat_items(value: Any) -> list[Any]:
    """Return a flat list from MATLAB arrays, object arrays, or Python lists."""
    if value is None:
        return []
    if isinstance(value, np.ndarray):
        return [item for item in value.ravel()]
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def field_names(value: Any) -> list[str]:
    """Return inspectable field names for dicts and MATLAB structs."""
    if isinstance(value, dict):
        return [key for key in value if not str(key).startswith("__")]
    if is_mat_struct(value):
        return list(getattr(value, "_fieldnames", []))
    if isinstance(value, np.void) and value.dtype.names:
        return list(value.dtype.names)
    return []


def scalar_field(value: Any, names: Iterable[str], default: Any = pd.NA) -> Any:
    """Return the first scalar-like field found from a list of candidate names."""
    for name in names:
        field_value = get_field(value, name, None)
        if field_value is not None:
            return unwrap_scalar(field_value)
    return default


def find_battery_object(raw_obj: Any) -> tuple[str, Any]:
    """Find the battery object inside a loaded NASA .mat dictionary."""
    if not isinstance(raw_obj, dict):
        return "unknown", raw_obj

    for key, value in raw_obj.items():
        if str(key).startswith("__"):
            continue
        if get_field(value, "cycle", None) is not None:
            return str(key), value

    available_keys = [key for key in raw_obj if not str(key).startswith("__")]
    raise ValueError(
        "Could not find a battery object with a `cycle` field in the MATLAB "
        f"file. Available top-level keys: {available_keys}"
    )


def extract_nasa_discharge_cycles(raw_obj: Any) -> list[dict[str, Any]]:
    """Extract discharge cycle records from a NASA battery MATLAB structure."""
    battery_id, battery_obj = find_battery_object(raw_obj)
    cycles = iter_mat_items(get_field(battery_obj, "cycle", None))
    if not cycles:
        raise ValueError(
            "Battery object does not contain cycle records. Run "
            "notebooks/inspect_battery_mat.py to inspect the raw structure."
        )

    records: list[dict[str, Any]] = []
    discharge_index = 0
    for raw_cycle_index, cycle in enumerate(cycles, start=1):
        cycle_type = str(unwrap_scalar(get_field(cycle, "type", ""))).lower()
        if cycle_type != "discharge":
            continue

        discharge_index += 1
        data = get_field(cycle, "data", None)
        capacity = scalar_field(
            data,
            ["Capacity", "capacity", "discharge_capacity_ah"],
        )
        internal_resistance = scalar_field(
            data,
            [
                "internal_resistance_ohm",
                "Internal_resistance",
                "Resistance",
                "resistance",
                "Re",
                "Rct",
            ],
            default=np.nan,
        )
        records.append(
            {
                "battery_id": battery_id,
                "cycle_index": discharge_index,
                "raw_cycle_index": raw_cycle_index,
                "ambient_temperature_c": scalar_field(
                    cycle,
                    ["ambient_temperature", "ambient_temperature_c", "temperature_c"],
                ),
                "discharge_capacity_ah": capacity,
                "internal_resistance_ohm": internal_resistance,
            }
        )

    if not records:
        raise ValueError(
            "No discharge cycles were found in the battery file. Available "
            "cycle types may be charge/impedance only, or the MATLAB structure "
            "may need custom normalization."
        )

    return records


def extract_cycle_records(raw_obj: Any) -> list[dict[str, Any]]:
    """Extract cycle-like records from a raw battery object.

    NASA battery aging files usually contain a top-level battery object such as
    ``B0005`` with a ``cycle`` array. This function extracts discharge cycles
    first. Simple list/DataFrame inputs are still supported for tests and manual
    intermediate preprocessing.
    """
    if isinstance(raw_obj, pd.DataFrame):
        return raw_obj.to_dict(orient="records")

    if isinstance(raw_obj, list):
        return [record for record in raw_obj if isinstance(record, dict)]

    if isinstance(raw_obj, dict):
        for key in ("cycle_records", "cycles", "cycle"):
            value = raw_obj.get(key)
            if isinstance(value, pd.DataFrame):
                return value.to_dict(orient="records")
            if isinstance(value, list):
                return [record for record in value if isinstance(record, dict)]
        return extract_nasa_discharge_cycles(raw_obj)

    if get_field(raw_obj, "cycle", None) is not None:
        return extract_nasa_discharge_cycles(raw_obj)

    raise ValueError(
        "Could not extract cycle records from the raw object. Inspect the raw "
        "NASA/Kaggle file structure with notebooks/inspect_battery_mat.py."
    )


def build_cycle_summary(cycle_records: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """Build the target cycle-level battery summary table."""
    rows: list[dict[str, Any]] = []
    first_capacity_by_battery: dict[str, float] = {}

    for record in cycle_records:
        battery_id = str(record.get("battery_id", record.get("cell_id", "unknown")))
        cycle_index = record.get("cycle_index", record.get("cycle", record.get("cycle_count")))
        discharge_capacity = record.get(
            "discharge_capacity_ah",
            record.get("capacity_ah", record.get("capacity")),
        )

        numeric_capacity = pd.to_numeric(discharge_capacity, errors="coerce")
        if pd.notna(numeric_capacity) and battery_id not in first_capacity_by_battery:
            first_capacity_by_battery[battery_id] = float(numeric_capacity)

        baseline_capacity = first_capacity_by_battery.get(battery_id)
        if baseline_capacity is not None and baseline_capacity != 0 and pd.notna(numeric_capacity):
            retention = float(numeric_capacity) / baseline_capacity * 100
        else:
            retention = record.get("capacity_retention_percent", pd.NA)

        numeric_retention = pd.to_numeric(retention, errors="coerce")
        failed = 1 if pd.notna(numeric_retention) and numeric_retention < 80 else 0

        rows.append(
            {
                "battery_id": battery_id,
                "cycle_index": cycle_index,
                "ambient_temperature_c": record.get(
                    "ambient_temperature_c",
                    record.get("ambient_temperature", record.get("temperature_c")),
                ),
                "discharge_capacity_ah": discharge_capacity,
                "capacity_retention_percent": retention,
                "internal_resistance_ohm": record.get(
                    "internal_resistance_ohm",
                    record.get("resistance_ohm", record.get("internal_resistance")),
                ),
                "failed": failed,
            }
        )

    summary_df = pd.DataFrame(rows, columns=BATTERY_SUMMARY_COLUMNS)
    validate_battery_summary_schema(summary_df)
    return summary_df


def save_cycle_summary(summary_df: pd.DataFrame, output_path: str | Path) -> Path:
    """Validate and save a cycle-level battery summary CSV."""
    validate_battery_summary_schema(summary_df)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(output, index=False)
    return output


def validate_battery_summary_schema(summary_df: pd.DataFrame) -> pd.DataFrame:
    """Validate required columns and return domain-constraint violations."""
    missing_columns = [
        column for column in BATTERY_SUMMARY_COLUMNS if column not in summary_df.columns
    ]
    if missing_columns:
        raise ValueError(
            "Battery cycle summary is missing required columns: "
            f"{missing_columns}"
        )

    return validate_domain_constraints(
        df=summary_df,
        constraints=BATTERY_SUMMARY_CONSTRAINTS,
    )
