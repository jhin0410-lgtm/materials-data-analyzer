"""Battery Archive cycle CSV schema audit helpers.

This module reads only cycle-data CSV headers and bounded sample rows directly
from Battery Archive zip members. It does not extract zips, concatenate full
datasets, normalize final schemas, or compute derived battery metrics.
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
