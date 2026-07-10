"""Battery Archive cycle CSV schema audit and normalization helpers.

This module reads only cycle-data CSV headers and bounded sample rows directly
from Battery Archive zip members for schema audits, and can load full cycle CSV
members into a source-traceable normalized cycle table. It does not extract
zips or compute derived battery metrics.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any
import zipfile

import pandas as pd


REQUIRED_INVENTORY_COLUMNS = ["zip_file", "internal_csv_path", "file_name"]

SCHEMA_INVENTORY_COLUMNS = [
    "zip_file",
    "internal_csv_path",
    "file_name",
    "schema_fingerprint",
    "column_count",
    "raw_columns",
    "normalized_columns",
    "sample_row_count",
    "encoding_used",
    "delimiter_used",
    "empty_file",
    "read_status",
    "read_message",
]

COLUMN_INVENTORY_COLUMNS = [
    "zip_file",
    "internal_csv_path",
    "file_name",
    "schema_fingerprint",
    "raw_column_name",
    "normalized_column_name",
    "column_position",
    "sample_inferred_dtype",
    "sample_non_null_count",
    "sample_null_count",
    "sample_values",
    "unit_candidate",
    "mapping_candidate",
    "mapping_confidence",
    "mapping_note",
]

CYCLE_METADATA_COLUMNS = [
    "zip_file",
    "internal_csv_path",
    "file_name",
    "source",
    "cell_id",
    "chemistry",
    "form_factor",
    "temperature_C",
    "soc_min_pct",
    "soc_max_pct",
    "soc_window",
    "charge_c_rate",
    "discharge_c_rate",
    "protocol_label",
    "schema_fingerprint",
    "source_row_number",
]

CANONICAL_CYCLE_VALUE_COLUMNS = [
    "cycle_index",
    "elapsed_time",
    "elapsed_time_unit",
    "min_current",
    "min_current_unit",
    "max_current",
    "max_current_unit",
    "min_voltage",
    "min_voltage_unit",
    "max_voltage",
    "max_voltage_unit",
    "charge_capacity",
    "charge_capacity_unit",
    "discharge_capacity",
    "discharge_capacity_unit",
    "charge_energy",
    "charge_energy_unit",
    "discharge_energy",
    "discharge_energy_unit",
    "date_or_timestamp",
    "start_time",
    "end_time",
]

NORMALIZED_CYCLE_COLUMNS = CYCLE_METADATA_COLUMNS + CANONICAL_CYCLE_VALUE_COLUMNS

CYCLE_LOAD_SUMMARY_COLUMNS = [
    "zip_file",
    "internal_csv_path",
    "file_name",
    "schema_fingerprint",
    "raw_row_count",
    "normalized_row_count",
    "dropped_blank_row_count",
    "invalid_cycle_index_count",
    "invalid_charge_capacity_count",
    "invalid_discharge_capacity_count",
    "invalid_charge_energy_count",
    "invalid_discharge_energy_count",
    "metadata_join_status",
    "load_status",
    "load_message",
]

CYCLE_COLUMN_MAPPING_COLUMNS = [
    "schema_fingerprint",
    "raw_column_name",
    "normalized_column_name",
    "canonical_column_name",
    "unit",
    "required",
    "mapping_confidence",
    "mapping_note",
]

METADATA_JOIN_COLUMNS = [
    "source",
    "cell_id",
    "chemistry",
    "form_factor",
    "temperature_C",
    "soc_min_pct",
    "soc_max_pct",
    "soc_window",
    "charge_c_rate",
    "discharge_c_rate",
    "protocol_label",
]

NUMERIC_CANONICAL_COLUMNS = [
    "cycle_index",
    "elapsed_time",
    "min_current",
    "max_current",
    "min_voltage",
    "max_voltage",
    "charge_capacity",
    "discharge_capacity",
    "charge_energy",
    "discharge_energy",
]

INVALID_NUMERIC_SUMMARY_COLUMNS = {
    "cycle_index": "invalid_cycle_index_count",
    "charge_capacity": "invalid_charge_capacity_count",
    "discharge_capacity": "invalid_discharge_capacity_count",
    "charge_energy": "invalid_charge_energy_count",
    "discharge_energy": "invalid_discharge_energy_count",
}

CANONICAL_MAPPING_BY_NORMALIZED_COLUMN = {
    "cycle_index": ("cycle_index", "unknown", True, "high", "observed in both audited schemas"),
    "test_time_s": ("elapsed_time", "s", True, "high", "observed in both audited schemas"),
    "min_current_a": ("min_current", "A", True, "high", "observed in both audited schemas"),
    "max_current_a": ("max_current", "A", True, "high", "observed in both audited schemas"),
    "min_voltage_v": ("min_voltage", "V", True, "high", "observed in both audited schemas"),
    "max_voltage_v": ("max_voltage", "V", True, "high", "observed in both audited schemas"),
    "charge_capacity_ah": ("charge_capacity", "Ah", True, "high", "observed in both audited schemas"),
    "discharge_capacity_ah": (
        "discharge_capacity",
        "Ah",
        True,
        "high",
        "observed in both audited schemas",
    ),
    "charge_energy_wh": ("charge_energy", "Wh", True, "high", "observed in both audited schemas"),
    "discharge_energy_wh": (
        "discharge_energy",
        "Wh",
        True,
        "high",
        "observed in both audited schemas",
    ),
    "start_time": ("start_time", "unknown", False, "high", "optional timestamp column"),
    "end_time": ("end_time", "unknown", False, "high", "optional timestamp column"),
}

READ_STATUS_SUCCESS = "success"
READ_STATUS_HEADER_ONLY = "header_only"
READ_STATUS_EMPTY = "empty"
READ_STATUS_READ_ERROR = "read_error"


def validate_cycle_schema_inventory_input(inventory_df: pd.DataFrame) -> None:
    """Validate the minimal columns required to locate raw zip members."""
    missing_columns = [
        column for column in REQUIRED_INVENTORY_COLUMNS if column not in inventory_df.columns
    ]
    if missing_columns:
        raise ValueError(
            "Battery Archive cycle schema audit inventory is missing required "
            "column(s): " + ", ".join(missing_columns)
        )


def normalize_column_name(raw_column_name: object) -> str:
    """Create an audit-only normalized column name while preserving unit tokens."""
    name = str(raw_column_name).strip().lstrip("\ufeff").lower()
    name = name.replace("%", " percent ")
    name = re.sub(r"[(){}\[\]]", " ", name)
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "unnamed"


def build_schema_fingerprint(normalized_columns: list[str]) -> str:
    """Create a deterministic fingerprint from ordered normalized columns."""
    payload = "|".join(normalized_columns)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"schema_{digest}"


def extract_unit_candidate(raw_column_name: object, normalized_column_name: str) -> str:
    """Extract an observed unit token without converting units."""
    raw_name = str(raw_column_name)
    parenthetical_units = re.findall(r"\(([^()]*)\)", raw_name)
    if parenthetical_units:
        return parenthetical_units[-1].strip() or "unknown"

    unit_suffixes = [
        "mah",
        "mwh",
        "ah",
        "wh",
        "ohm",
        "percent",
        "pct",
        "degc",
        "c",
        "s",
        "a",
        "v",
    ]
    parts = normalized_column_name.split("_")
    if parts and parts[-1] in unit_suffixes:
        return parts[-1]
    return "unknown"


def infer_mapping_candidate(
    raw_column_name: object,
    normalized_column_name: str,
) -> tuple[str, str, str]:
    """Suggest a conservative semantic mapping candidate from observed names."""
    raw_lower = str(raw_column_name).lower()
    name = normalized_column_name

    if name in {"cycle_index", "cycle", "cycle_number", "cycle_no"}:
        return "cycle_index", "high", "explicit cycle index/name"

    if "charge" in name and "discharge" not in name and "capacity" in name:
        return "charge_capacity", "high", "explicit charge capacity column"
    if "discharge" in name and "capacity" in name:
        return "discharge_capacity", "high", "explicit discharge capacity column"
    if "capacity" in name:
        return "unknown", "none", "capacity column is not explicitly charge/discharge"

    if "charge" in name and "discharge" not in name and "energy" in name:
        return "charge_energy", "high", "explicit charge energy column"
    if "discharge" in name and "energy" in name:
        return "discharge_energy", "high", "explicit discharge energy column"
    if "energy" in name:
        return "unknown", "none", "energy column is not explicitly charge/discharge"

    if "coulombic" in name and ("efficiency" in name or "eff" in name):
        return "coulombic_efficiency", "high", "explicit coulombic efficiency column"
    if name in {"ce", "coul_efficiency"}:
        return "coulombic_efficiency", "medium", "abbreviated efficiency column"

    if "retention" in name:
        return "capacity_retention", "medium", "retention appears in observed name"
    if name in {"soh", "state_of_health"}:
        return "soh", "high", "explicit SOH column"

    if "internal" in name and "resistance" in name:
        return "internal_resistance", "high", "explicit internal resistance column"
    if name in {"ir", "dcir"} or "resistance" in name:
        return "internal_resistance", "medium", "resistance/IR context is limited"

    if "temperature" in name or name.endswith("_temp") or "_temp_" in name:
        return "temperature", "high", "explicit temperature column"

    if name in {"test_time_s", "elapsed_time", "elapsed_time_s"}:
        return "elapsed_time", "high", "explicit elapsed/test time column"
    if "time" in name and any(token in name for token in ["elapsed", "test"]):
        return "elapsed_time", "medium", "time column appears elapsed/test related"

    if name in {"date_time", "datetime", "timestamp", "start_time", "end_time"}:
        return "date_or_timestamp", "high", "explicit date/time column"
    if "date" in name or "timestamp" in name:
        return "date_or_timestamp", "medium", "date/timestamp appears in observed name"

    if "voltage" in name or "current" in name:
        return "unknown", "none", "observed electrical measurement, not a requested mapping target"

    if raw_lower.strip():
        return "unknown", "none", "no conservative mapping candidate"
    return "unknown", "none", "empty column name"


def resolve_zip_path(raw_dir: str | Path, zip_file: object) -> Path:
    """Resolve an inventory zip path safely under raw_dir."""
    zip_text = str(zip_file).replace("\\", "/")
    zip_path = PurePosixPath(zip_text)
    if zip_path.is_absolute() or ".." in zip_path.parts:
        raise ValueError(f"Unsafe zip_file path in inventory: {zip_file}")

    raw_root = Path(raw_dir).resolve()
    candidate = (raw_root / Path(*zip_path.parts)).resolve()
    if raw_root != candidate and raw_root not in candidate.parents:
        raise ValueError(f"Resolved zip path escapes raw_dir: {zip_file}")
    return candidate


def validate_internal_csv_path(internal_csv_path: object) -> str:
    """Validate and normalize a zip-internal CSV path."""
    internal_text = str(internal_csv_path).replace("\\", "/")
    internal_path = PurePosixPath(internal_text)
    if internal_path.is_absolute() or ".." in internal_path.parts:
        raise ValueError(f"Unsafe internal_csv_path in inventory: {internal_csv_path}")
    return internal_text


def _json_list(values: list[object]) -> str:
    return json.dumps(values, ensure_ascii=False)


def _empty_schema_record(
    inventory_row: pd.Series,
    read_status: str,
    read_message: str,
) -> dict[str, object]:
    return {
        "zip_file": inventory_row.get("zip_file", ""),
        "internal_csv_path": inventory_row.get("internal_csv_path", ""),
        "file_name": inventory_row.get("file_name", ""),
        "schema_fingerprint": build_schema_fingerprint([]),
        "column_count": 0,
        "raw_columns": _json_list([]),
        "normalized_columns": _json_list([]),
        "sample_row_count": 0,
        "encoding_used": "",
        "delimiter_used": "",
        "empty_file": True,
        "read_status": read_status,
        "read_message": read_message,
    }


def _sample_values(series: pd.Series, limit: int = 5) -> str:
    values: list[str] = []
    for value in series.dropna().astype(str):
        cleaned = value.strip()
        if cleaned not in values:
            values.append(cleaned[:80])
        if len(values) >= limit:
            break
    return _json_list(values)


def _read_csv_sample_from_zip(
    zip_path: Path,
    internal_csv_path: str,
    sample_rows: int,
) -> tuple[pd.DataFrame | None, str, str, str]:
    """Read a bounded CSV sample from a zip member with conservative fallbacks."""
    attempts = [
        ("utf-8-sig", ","),
        ("utf-8", ","),
        ("utf-8-sig", ";"),
        ("utf-8-sig", "\t"),
    ]
    messages: list[str] = []
    for encoding, delimiter in attempts:
        try:
            with zipfile.ZipFile(zip_path) as archive:
                with archive.open(internal_csv_path) as member:
                    sample_df = pd.read_csv(
                        member,
                        nrows=sample_rows,
                        encoding=encoding,
                        sep=delimiter,
                    )
            return sample_df, encoding, delimiter, ""
        except pd.errors.EmptyDataError:
            return None, encoding, delimiter, "empty CSV member"
        except KeyError:
            return None, encoding, delimiter, "internal CSV member was not found"
        except UnicodeDecodeError as exc:
            messages.append(f"{encoding}/{delimiter}: {exc.__class__.__name__}")
            continue
        except pd.errors.ParserError as exc:
            messages.append(f"{encoding}/{delimiter}: {exc.__class__.__name__}")
            continue
        except zipfile.BadZipFile as exc:
            return None, encoding, delimiter, f"bad zip file: {exc}"
        except Exception as exc:  # noqa: BLE001 - audit must continue per file
            messages.append(f"{encoding}/{delimiter}: {exc.__class__.__name__}: {exc}")
            continue

    return None, "", "", "; ".join(messages) or "CSV sample could not be read"


def audit_cycle_file_schema(
    raw_dir: str | Path,
    inventory_row: pd.Series,
    sample_rows: int = 50,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Audit one cycle CSV member and return file/column inventory records."""
    if sample_rows < 0:
        raise ValueError("sample_rows must be non-negative")

    try:
        zip_path = resolve_zip_path(raw_dir, inventory_row["zip_file"])
        internal_csv_path = validate_internal_csv_path(inventory_row["internal_csv_path"])
    except Exception as exc:  # noqa: BLE001 - invalid row becomes read_error
        return (
            _empty_schema_record(inventory_row, READ_STATUS_READ_ERROR, str(exc)),
            [],
        )

    if not zip_path.exists():
        return (
            _empty_schema_record(
                inventory_row,
                READ_STATUS_READ_ERROR,
                f"zip file was not found: {inventory_row['zip_file']}",
            ),
            [],
        )

    sample_df, encoding_used, delimiter_used, read_message = _read_csv_sample_from_zip(
        zip_path=zip_path,
        internal_csv_path=internal_csv_path,
        sample_rows=sample_rows,
    )
    if sample_df is None:
        return (
            _empty_schema_record(
                inventory_row,
                READ_STATUS_EMPTY if read_message == "empty CSV member" else READ_STATUS_READ_ERROR,
                read_message,
            ),
            [],
        )

    raw_columns = [str(column) for column in sample_df.columns]
    normalized_columns = [normalize_column_name(column) for column in raw_columns]
    schema_fingerprint = build_schema_fingerprint(normalized_columns)
    sample_row_count = int(len(sample_df))
    read_status = READ_STATUS_SUCCESS if sample_row_count else READ_STATUS_HEADER_ONLY

    schema_record = {
        "zip_file": inventory_row["zip_file"],
        "internal_csv_path": internal_csv_path,
        "file_name": inventory_row["file_name"],
        "schema_fingerprint": schema_fingerprint,
        "column_count": len(raw_columns),
        "raw_columns": _json_list(raw_columns),
        "normalized_columns": _json_list(normalized_columns),
        "sample_row_count": sample_row_count,
        "encoding_used": encoding_used,
        "delimiter_used": delimiter_used,
        "empty_file": False,
        "read_status": read_status,
        "read_message": read_message,
    }

    column_records: list[dict[str, object]] = []
    for position, (raw_column, normalized_column) in enumerate(
        zip(raw_columns, normalized_columns),
        start=1,
    ):
        series = sample_df[raw_column]
        mapping_candidate, mapping_confidence, mapping_note = infer_mapping_candidate(
            raw_column,
            normalized_column,
        )
        column_records.append(
            {
                "zip_file": inventory_row["zip_file"],
                "internal_csv_path": internal_csv_path,
                "file_name": inventory_row["file_name"],
                "schema_fingerprint": schema_fingerprint,
                "raw_column_name": raw_column,
                "normalized_column_name": normalized_column,
                "column_position": position,
                "sample_inferred_dtype": str(series.dtype),
                "sample_non_null_count": int(series.notna().sum()),
                "sample_null_count": int(series.isna().sum()),
                "sample_values": _sample_values(series),
                "unit_candidate": extract_unit_candidate(raw_column, normalized_column),
                "mapping_candidate": mapping_candidate,
                "mapping_confidence": mapping_confidence,
                "mapping_note": mapping_note,
            }
        )

    return schema_record, column_records


def build_cycle_schema_audit_tables(
    raw_dir: str | Path,
    inventory_df: pd.DataFrame,
    sample_rows: int = 50,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build schema and column inventories for Battery Archive cycle CSV files."""
    validate_cycle_schema_inventory_input(inventory_df)
    sorted_inventory = inventory_df.sort_values(
        ["zip_file", "internal_csv_path"],
        key=lambda series: series.astype(str).str.casefold(),
    ).reset_index(drop=True)

    schema_records: list[dict[str, object]] = []
    column_records: list[dict[str, object]] = []
    for _, inventory_row in sorted_inventory.iterrows():
        schema_record, file_column_records = audit_cycle_file_schema(
            raw_dir=raw_dir,
            inventory_row=inventory_row,
            sample_rows=sample_rows,
        )
        schema_records.append(schema_record)
        column_records.extend(file_column_records)

    schema_df = pd.DataFrame(schema_records, columns=SCHEMA_INVENTORY_COLUMNS)
    column_df = pd.DataFrame(column_records, columns=COLUMN_INVENTORY_COLUMNS)
    if not column_records:
        column_df = pd.DataFrame(columns=COLUMN_INVENTORY_COLUMNS)

    return schema_df, column_df.sort_values(
        ["zip_file", "internal_csv_path", "column_position"],
    ).reset_index(drop=True)


def summarize_mapping_coverage(column_df: pd.DataFrame) -> pd.DataFrame:
    """Summarize file coverage by conservative mapping candidate."""
    if column_df.empty:
        return pd.DataFrame(
            columns=["mapping_candidate", "file_count", "column_occurrence_count"]
        )
    valid = column_df[column_df["mapping_candidate"].ne("unknown")]
    if valid.empty:
        return pd.DataFrame(
            columns=["mapping_candidate", "file_count", "column_occurrence_count"]
        )
    summary = (
        valid.groupby("mapping_candidate", dropna=False)
        .agg(
            file_count=("internal_csv_path", "nunique"),
            column_occurrence_count=("raw_column_name", "count"),
        )
        .reset_index()
        .sort_values(["file_count", "mapping_candidate"], ascending=[False, True])
    )
    return summary


def validate_cycle_metadata_inventory(inventory_df: pd.DataFrame) -> None:
    """Validate enriched cycle-file metadata inventory before row loading."""
    required_columns = REQUIRED_INVENTORY_COLUMNS + METADATA_JOIN_COLUMNS
    missing_columns = [
        column for column in required_columns if column not in inventory_df.columns
    ]
    if missing_columns:
        raise ValueError(
            "Battery Archive enriched inventory is missing required column(s): "
            + ", ".join(missing_columns)
        )

    duplicate_count = int(
        inventory_df.duplicated(["zip_file", "internal_csv_path"]).sum()
    )
    if duplicate_count:
        raise ValueError(
            "Battery Archive enriched inventory contains duplicate "
            "(zip_file, internal_csv_path) keys."
        )


def validate_cycle_normalization_inputs(
    inventory_df: pd.DataFrame,
    schema_inventory_df: pd.DataFrame,
    column_inventory_df: pd.DataFrame,
) -> None:
    """Validate inputs for Battery Archive cycle normalization."""
    validate_cycle_metadata_inventory(inventory_df)
    missing_schema_columns = [
        column for column in SCHEMA_INVENTORY_COLUMNS if column not in schema_inventory_df.columns
    ]
    if missing_schema_columns:
        raise ValueError(
            "Battery Archive schema inventory is missing required column(s): "
            + ", ".join(missing_schema_columns)
        )

    missing_column_columns = [
        column for column in COLUMN_INVENTORY_COLUMNS if column not in column_inventory_df.columns
    ]
    if missing_column_columns:
        raise ValueError(
            "Battery Archive column inventory is missing required column(s): "
            + ", ".join(missing_column_columns)
        )

    duplicate_schema_keys = int(
        schema_inventory_df.duplicated(["zip_file", "internal_csv_path"]).sum()
    )
    if duplicate_schema_keys:
        raise ValueError(
            "Battery Archive schema inventory contains duplicate "
            "(zip_file, internal_csv_path) keys."
        )


def build_cycle_column_mapping(column_inventory_df: pd.DataFrame) -> pd.DataFrame:
    """Build a canonical mapping contract from observed audited columns only."""
    missing_columns = [
        column for column in COLUMN_INVENTORY_COLUMNS if column not in column_inventory_df.columns
    ]
    if missing_columns:
        raise ValueError(
            "Battery Archive column inventory is missing required column(s): "
            + ", ".join(missing_columns)
        )

    mapping_rows: list[dict[str, object]] = []
    unique_columns = column_inventory_df[
        [
            "schema_fingerprint",
            "raw_column_name",
            "normalized_column_name",
            "unit_candidate",
            "mapping_confidence",
            "mapping_note",
        ]
    ].drop_duplicates()

    for _, row in unique_columns.iterrows():
        normalized_name = str(row["normalized_column_name"])
        mapping = CANONICAL_MAPPING_BY_NORMALIZED_COLUMN.get(normalized_name)
        if mapping is None:
            canonical_column, unit, required, confidence, note = (
                "unknown",
                str(row.get("unit_candidate", "unknown")),
                False,
                "none",
                "not included in v1.1.3b canonical cycle table",
            )
        else:
            canonical_column, unit, required, confidence, note = mapping

        mapping_rows.append(
            {
                "schema_fingerprint": row["schema_fingerprint"],
                "raw_column_name": row["raw_column_name"],
                "normalized_column_name": normalized_name,
                "canonical_column_name": canonical_column,
                "unit": unit,
                "required": bool(required),
                "mapping_confidence": confidence,
                "mapping_note": note,
            }
        )

    return pd.DataFrame(mapping_rows, columns=CYCLE_COLUMN_MAPPING_COLUMNS).sort_values(
        ["schema_fingerprint", "raw_column_name", "canonical_column_name"]
    ).reset_index(drop=True)


def _read_full_cycle_csv_from_zip(
    zip_path: Path,
    internal_csv_path: str,
) -> tuple[pd.DataFrame | None, str]:
    """Read one full cycle CSV member without extracting raw zip contents."""
    attempts = [
        ("utf-8-sig", ","),
        ("utf-8", ","),
        ("utf-8-sig", ";"),
        ("utf-8-sig", "\t"),
    ]
    messages: list[str] = []
    for encoding, delimiter in attempts:
        try:
            with zipfile.ZipFile(zip_path) as archive:
                with archive.open(internal_csv_path) as member:
                    return (
                        pd.read_csv(
                            member,
                            encoding=encoding,
                            sep=delimiter,
                            skip_blank_lines=False,
                        ),
                        "",
                    )
        except pd.errors.EmptyDataError:
            return None, "empty CSV member"
        except KeyError:
            return None, "internal CSV member was not found"
        except UnicodeDecodeError as exc:
            messages.append(f"{encoding}/{delimiter}: {exc.__class__.__name__}")
            continue
        except pd.errors.ParserError as exc:
            messages.append(f"{encoding}/{delimiter}: {exc.__class__.__name__}")
            continue
        except zipfile.BadZipFile as exc:
            return None, f"bad zip file: {exc}"
        except Exception as exc:  # noqa: BLE001 - file-level summary records errors
            messages.append(f"{encoding}/{delimiter}: {exc.__class__.__name__}: {exc}")
            continue
    return None, "; ".join(messages) or "cycle CSV could not be read"


def load_cycle_member(
    raw_dir: str | Path,
    inventory_row: pd.Series,
) -> tuple[pd.DataFrame | None, str]:
    """Load one cycle CSV member as a DataFrame without extracting the zip."""
    try:
        zip_path = resolve_zip_path(raw_dir, inventory_row["zip_file"])
        internal_csv_path = validate_internal_csv_path(inventory_row["internal_csv_path"])
    except Exception as exc:  # noqa: BLE001 - caller records file-level error
        return None, str(exc)

    if not zip_path.exists():
        return None, f"zip file was not found: {inventory_row['zip_file']}"
    return _read_full_cycle_csv_from_zip(zip_path, internal_csv_path)


def _is_blank_row(row: pd.Series) -> bool:
    """Return whether a raw CSV row has no meaningful cell values."""
    for value in row:
        if pd.isna(value):
            continue
        if str(value).strip() != "":
            return False
    return True


def _invalid_numeric_count(series: pd.Series) -> int:
    """Count non-empty raw values that become NaN after numeric conversion."""
    non_empty = series.notna() & series.astype(str).str.strip().ne("")
    converted = pd.to_numeric(series, errors="coerce")
    return int((non_empty & converted.isna()).sum())


def _empty_load_summary(
    metadata_row: pd.Series,
    schema_fingerprint: str,
    load_status: str,
    load_message: str,
) -> dict[str, object]:
    """Build an empty file-level load summary row."""
    return {
        "zip_file": metadata_row.get("zip_file", ""),
        "internal_csv_path": metadata_row.get("internal_csv_path", ""),
        "file_name": metadata_row.get("file_name", ""),
        "schema_fingerprint": schema_fingerprint,
        "raw_row_count": 0,
        "normalized_row_count": 0,
        "dropped_blank_row_count": 0,
        "invalid_cycle_index_count": 0,
        "invalid_charge_capacity_count": 0,
        "invalid_discharge_capacity_count": 0,
        "invalid_charge_energy_count": 0,
        "invalid_discharge_energy_count": 0,
        "metadata_join_status": "matched",
        "load_status": load_status,
        "load_message": load_message,
    }


def normalize_cycle_dataframe(
    raw_df: pd.DataFrame,
    metadata_row: pd.Series,
    mapping_df: pd.DataFrame,
    schema_fingerprint: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Normalize one raw cycle DataFrame into the v1.1.3b canonical table."""
    schema_mapping = mapping_df[mapping_df["schema_fingerprint"].eq(schema_fingerprint)]
    if schema_mapping.empty:
        summary = _empty_load_summary(
            metadata_row,
            schema_fingerprint,
            "load_error",
            f"schema mapping was not found for {schema_fingerprint}",
        )
        summary["raw_row_count"] = len(raw_df)
        return pd.DataFrame(columns=NORMALIZED_CYCLE_COLUMNS), summary

    raw_columns = [str(column) for column in raw_df.columns]
    normalized_lookup = {
        normalize_column_name(raw_column): raw_column for raw_column in raw_columns
    }
    expected_normalized = set(schema_mapping["normalized_column_name"].astype(str))
    observed_normalized = set(normalized_lookup)
    if expected_normalized != observed_normalized:
        summary = _empty_load_summary(
            metadata_row,
            schema_fingerprint,
            "load_error",
            "raw columns did not match the schema mapping contract",
        )
        summary["raw_row_count"] = len(raw_df)
        return pd.DataFrame(columns=NORMALIZED_CYCLE_COLUMNS), summary

    raw_row_count = int(len(raw_df))
    blank_mask = raw_df.apply(_is_blank_row, axis=1)
    dropped_blank_row_count = int(blank_mask.sum())
    working_df = raw_df.loc[~blank_mask].copy()
    original_source_numbers = pd.Series(range(1, raw_row_count + 1), index=raw_df.index)
    source_row_numbers = original_source_numbers.loc[working_df.index].astype(int)

    normalized_df = pd.DataFrame(index=working_df.index)
    for column in NORMALIZED_CYCLE_COLUMNS:
        normalized_df[column] = pd.NA

    for column in ["zip_file", "internal_csv_path", "file_name"]:
        normalized_df[column] = metadata_row.get(column, pd.NA)
    for column in METADATA_JOIN_COLUMNS:
        normalized_df[column] = metadata_row.get(column, pd.NA)
    normalized_df["schema_fingerprint"] = schema_fingerprint
    normalized_df["source_row_number"] = source_row_numbers.values

    summary_counts = {
        "invalid_cycle_index_count": 0,
        "invalid_charge_capacity_count": 0,
        "invalid_discharge_capacity_count": 0,
        "invalid_charge_energy_count": 0,
        "invalid_discharge_energy_count": 0,
    }
    messages: list[str] = []

    for _, mapping_row in schema_mapping.iterrows():
        canonical_column = str(mapping_row["canonical_column_name"])
        if canonical_column == "unknown":
            continue
        raw_column = normalized_lookup[str(mapping_row["normalized_column_name"])]
        raw_series = working_df[raw_column]

        if canonical_column in NUMERIC_CANONICAL_COLUMNS:
            normalized_df[canonical_column] = pd.to_numeric(raw_series, errors="coerce")
            summary_column = INVALID_NUMERIC_SUMMARY_COLUMNS.get(canonical_column)
            if summary_column:
                invalid_count = _invalid_numeric_count(raw_series)
                summary_counts[summary_column] += invalid_count
                if invalid_count:
                    messages.append(f"{canonical_column}: {invalid_count} invalid numeric values")
        else:
            normalized_df[canonical_column] = raw_series.astype("string")

        unit = mapping_row.get("unit", "unknown")
        unit_column = f"{canonical_column}_unit"
        if unit_column in normalized_df.columns:
            normalized_df[unit_column] = unit

    if "start_time" in normalized_df.columns:
        normalized_df["date_or_timestamp"] = normalized_df["start_time"]

    normalized_df = normalized_df[NORMALIZED_CYCLE_COLUMNS].reset_index(drop=True)
    total_invalid = sum(summary_counts.values())
    load_status = "success_with_warnings" if total_invalid else "success"
    summary = {
        "zip_file": metadata_row.get("zip_file", ""),
        "internal_csv_path": metadata_row.get("internal_csv_path", ""),
        "file_name": metadata_row.get("file_name", ""),
        "schema_fingerprint": schema_fingerprint,
        "raw_row_count": raw_row_count,
        "normalized_row_count": int(len(normalized_df)),
        "dropped_blank_row_count": dropped_blank_row_count,
        "invalid_cycle_index_count": summary_counts["invalid_cycle_index_count"],
        "invalid_charge_capacity_count": summary_counts["invalid_charge_capacity_count"],
        "invalid_discharge_capacity_count": summary_counts[
            "invalid_discharge_capacity_count"
        ],
        "invalid_charge_energy_count": summary_counts["invalid_charge_energy_count"],
        "invalid_discharge_energy_count": summary_counts["invalid_discharge_energy_count"],
        "metadata_join_status": "matched",
        "load_status": load_status,
        "load_message": "; ".join(messages),
    }
    return normalized_df, summary


def load_battery_archive_cycle_data(
    raw_dir: str | Path,
    inventory_df: pd.DataFrame,
    schema_inventory_df: pd.DataFrame,
    column_inventory_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load and normalize Battery Archive cycle CSVs into a canonical table."""
    validate_cycle_normalization_inputs(
        inventory_df=inventory_df,
        schema_inventory_df=schema_inventory_df,
        column_inventory_df=column_inventory_df,
    )
    mapping_df = build_cycle_column_mapping(column_inventory_df)
    metadata_by_key = {
        (str(row["zip_file"]), str(row["internal_csv_path"])): row
        for _, row in inventory_df.iterrows()
    }

    normalized_frames: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []
    sorted_schema = schema_inventory_df.sort_values(
        ["zip_file", "internal_csv_path"],
        key=lambda series: series.astype(str).str.casefold(),
    ).reset_index(drop=True)

    for _, schema_row in sorted_schema.iterrows():
        key = (str(schema_row["zip_file"]), str(schema_row["internal_csv_path"]))
        metadata_row = metadata_by_key.get(key)
        if metadata_row is None:
            summary = _empty_load_summary(
                schema_row,
                str(schema_row.get("schema_fingerprint", "")),
                "load_error",
                "metadata key was not found in enriched inventory",
            )
            summary["metadata_join_status"] = "missing"
            summary_rows.append(summary)
            continue

        raw_df, read_message = load_cycle_member(raw_dir, metadata_row)
        if raw_df is None:
            summary = _empty_load_summary(
                metadata_row,
                str(schema_row.get("schema_fingerprint", "")),
                "load_error",
                read_message,
            )
            summary_rows.append(summary)
            continue

        normalized_df, summary = normalize_cycle_dataframe(
            raw_df=raw_df,
            metadata_row=metadata_row,
            mapping_df=mapping_df,
            schema_fingerprint=str(schema_row["schema_fingerprint"]),
        )
        if not normalized_df.empty:
            normalized_frames.append(normalized_df)
        summary_rows.append(summary)

    if normalized_frames:
        normalized_all = pd.concat(normalized_frames, ignore_index=True)
    else:
        normalized_all = pd.DataFrame(columns=NORMALIZED_CYCLE_COLUMNS)

    normalized_all = normalized_all.sort_values(
        ["zip_file", "internal_csv_path", "source_row_number"],
        kind="stable",
    ).reset_index(drop=True)
    duplicate_count = int(
        normalized_all.duplicated(
            ["zip_file", "internal_csv_path", "source_row_number"]
        ).sum()
    )
    if duplicate_count:
        raise ValueError(
            "Duplicate normalized cycle source keys were found: "
            "(zip_file, internal_csv_path, source_row_number)."
        )

    summary_df = pd.DataFrame(summary_rows, columns=CYCLE_LOAD_SUMMARY_COLUMNS).sort_values(
        ["zip_file", "internal_csv_path"],
        key=lambda series: series.astype(str).str.casefold(),
    ).reset_index(drop=True)
    return normalized_all[NORMALIZED_CYCLE_COLUMNS], summary_df, mapping_df
