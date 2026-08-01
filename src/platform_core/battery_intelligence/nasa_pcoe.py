"""Local import of NASA PCoE battery-aging MATLAB files.

The importer performs no network access. It converts source `.mat` files (or
ZIP archives containing them) into the canonical cycle-summary and raw-signal
contracts used by Battery Degradation Intelligence.
"""
from __future__ import annotations

import json
import math
import shutil
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
import pandas as pd
from scipy.io import loadmat

from .common import canonical_json, file_sha256


NASA_PCOE_SOURCE_NAME = "NASA PCoE Li-ion Battery Aging Datasets"
NASA_PCOE_SOURCE_IDENTIFIER = (
    "https://www.nasa.gov/content/prognostics-center-of-excellence-data-set-repository"
)
NASA_PCOE_DOWNLOAD_URL = (
    "https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip"
)
NASA_PCOE_CITATION = (
    "B. Saha and K. Goebel (2007), Battery Data Set, "
    "NASA Prognostics Data Repository, NASA Ames Research Center."
)
NASA_PCOE_TERMS = (
    "NASA data catalog license field is not specified. The NASA PCoE repository "
    "requests acknowledgement of the dataset and donors and states that use is "
    "at the user's own risk."
)
IMPORT_SCHEMA_VERSION = "1.0"
MAX_ARCHIVE_DEPTH = 4
MAX_ARCHIVE_MEMBERS = 20_000
MAX_MEMBER_BYTES = 2_000_000_000


@dataclass(frozen=True)
class _MatSource:
    path: Path
    source_location: str


def _safe_archive_path(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe archive member path: {name!r}")
    if path.parts and ":" in path.parts[0]:
        raise ValueError(f"unsafe archive member drive path: {name!r}")
    return path


def _extract_zip_recursive(
    archive_path: Path,
    destination: Path,
    *,
    source_prefix: str,
    depth: int,
    state: dict[str, int],
) -> list[_MatSource]:
    if depth > MAX_ARCHIVE_DEPTH:
        raise ValueError(
            f"nested archive depth exceeds {MAX_ARCHIVE_DEPTH}: {source_prefix}"
        )
    sources: list[_MatSource] = []
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            state["members"] += 1
            if state["members"] > MAX_ARCHIVE_MEMBERS:
                raise ValueError(
                    f"archive contains more than {MAX_ARCHIVE_MEMBERS} members"
                )
            if info.is_dir():
                continue
            member = _safe_archive_path(info.filename)
            if info.file_size > MAX_MEMBER_BYTES:
                raise ValueError(
                    f"archive member exceeds {MAX_MEMBER_BYTES} bytes: {info.filename}"
                )
            suffix = member.suffix.lower()
            if suffix not in {".mat", ".zip"}:
                continue
            state["files"] += 1
            local = destination / f"{state['files']:06d}_{member.name}"
            with archive.open(info) as source, local.open("wb") as target:
                shutil.copyfileobj(source, target)
            location = f"{source_prefix}!{member.as_posix()}"
            if suffix == ".mat":
                sources.append(_MatSource(local, location))
            else:
                sources.extend(
                    _extract_zip_recursive(
                        local,
                        destination,
                        source_prefix=location,
                        depth=depth + 1,
                        state=state,
                    )
                )
    return sources


def _discover_mat_sources(
    input_path: Path,
    temporary_directory: Path,
) -> tuple[list[_MatSource], dict[str, Any]]:
    if input_path.is_dir():
        files = sorted(
            (
                path
                for path in input_path.rglob("*")
                if path.is_file() and path.suffix.lower() == ".mat"
            ),
            key=lambda path: path.as_posix().lower(),
        )
        sources = [
            _MatSource(path, path.relative_to(input_path).as_posix()) for path in files
        ]
        metadata = {
            "input_kind": "directory",
            "input_path": str(input_path),
            "input_sha256": None,
        }
    elif input_path.is_file() and input_path.suffix.lower() == ".mat":
        sources = [_MatSource(input_path, input_path.name)]
        metadata = {
            "input_kind": "mat_file",
            "input_path": str(input_path),
            "input_sha256": file_sha256(input_path),
        }
    elif input_path.is_file() and input_path.suffix.lower() == ".zip":
        sources = _extract_zip_recursive(
            input_path,
            temporary_directory,
            source_prefix=input_path.name,
            depth=0,
            state={"members": 0, "files": 0},
        )
        metadata = {
            "input_kind": "zip_archive",
            "input_path": str(input_path),
            "input_sha256": file_sha256(input_path),
        }
    else:
        raise ValueError(
            "NASA PCoE input must be an existing .mat file, .zip archive, or directory"
        )
    if not sources:
        raise ValueError("no MATLAB .mat files were found in the supplied input")
    return sources, metadata


def _as_mapping(value: Any, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be a MATLAB struct-like mapping")
    return value


def _as_records(value: Any, *, context: str) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, np.ndarray):
        values = value.reshape(-1).tolist()
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        values = list(value)
    else:
        values = [value]
    records: list[Mapping[str, Any]] = []
    for index, item in enumerate(values, start=1):
        records.append(_as_mapping(item, context=f"{context}[{index}]"))
    return records


def _text_scalar(value: Any, *, context: str) -> str:
    array = np.asarray(value)
    if array.size != 1:
        raise ValueError(f"{context} must contain exactly one text value")
    item = array.reshape(-1)[0]
    if isinstance(item, bytes):
        item = item.decode("utf-8", errors="strict")
    text = str(item).strip()
    if not text:
        raise ValueError(f"{context} may not be blank")
    return text


def _numeric_vector(value: Any, *, context: str) -> np.ndarray:
    try:
        vector = np.asarray(value, dtype=float).reshape(-1)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{context} must be numeric") from error
    if vector.size < 2:
        raise ValueError(f"{context} must contain at least two values")
    if not np.isfinite(vector).all():
        raise ValueError(f"{context} must contain only finite values")
    return vector


def _optional_numeric_vector(
    data: Mapping[str, Any],
    field: str,
    *,
    context: str,
) -> np.ndarray | None:
    if field not in data:
        return None
    return _numeric_vector(data[field], context=f"{context}.{field}")


def _positive_scalar(value: Any, *, context: str) -> float:
    try:
        array = np.asarray(value, dtype=float).reshape(-1)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{context} must be numeric") from error
    if array.size != 1 or not math.isfinite(float(array[0])):
        raise ValueError(f"{context} must contain one finite numeric value")
    result = float(array[0])
    if result <= 0:
        raise ValueError(f"{context} must be positive")
    return result


def _optional_scalar(value: Any) -> float | None:
    try:
        array = np.asarray(value, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return None
    if array.size != 1 or not math.isfinite(float(array[0])):
        return None
    return float(array[0])


def _parse_matlab_datetime(value: Any) -> datetime | None:
    try:
        vector = np.asarray(value, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return None
    if vector.size < 6 or not np.isfinite(vector[:6]).all():
        return None
    year, month, day, hour, minute = (int(item) for item in vector[:5])
    second_value = float(vector[5])
    second = int(math.floor(second_value))
    microsecond = int(round((second_value - second) * 1_000_000))
    if microsecond == 1_000_000:
        second += 1
        microsecond = 0
    try:
        return datetime(
            year,
            month,
            day,
            hour,
            minute,
            second,
            microsecond,
        )
    except ValueError:
        return None


def _cumulative_capacity_ah(current_a: np.ndarray, time_s: np.ndarray) -> np.ndarray:
    increments = np.diff(time_s)
    trapezoids = (
        0.5
        * (np.abs(current_a[:-1]) + np.abs(current_a[1:]))
        * increments
        / 3600.0
    )
    return np.concatenate(([0.0], np.cumsum(trapezoids)))


def _load_source(
    source: _MatSource,
) -> tuple[
    str | None,
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
]:
    try:
        loaded = loadmat(source.path, simplify_cells=True)
    except NotImplementedError as error:
        raise ValueError(
            f"{source.source_location}: MATLAB v7.3/HDF5 files are not supported by "
            "the bounded SciPy importer"
        ) from error
    except (OSError, ValueError, TypeError) as error:
        raise ValueError(f"{source.source_location}: unable to read MATLAB file") from error

    variables = {
        key: value for key, value in loaded.items() if not str(key).startswith("__")
    }
    inventory = {
        "source_location": source.source_location,
        "mat_sha256": file_sha256(source.path),
        "size_bytes": int(source.path.stat().st_size),
        "battery_id": None,
        "total_operation_count": 0,
        "discharge_operation_count": 0,
        "charge_operation_count": 0,
        "impedance_operation_count": 0,
        "other_operation_count": 0,
        "imported": False,
        "skip_reason": None,
    }
    warnings: list[dict[str, Any]] = []
    if len(variables) != 1:
        inventory["skip_reason"] = "expected_exactly_one_top_level_variable"
        return None, [], [], inventory, warnings

    variable_name, root_value = next(iter(variables.items()))
    if not isinstance(root_value, Mapping) or "cycle" not in root_value:
        inventory["skip_reason"] = "top_level_variable_has_no_cycle_structure"
        return None, [], [], inventory, warnings

    expected_stem = PurePosixPath(source.source_location.split("!")[-1]).stem
    if variable_name.strip().lower() != expected_stem.strip().lower():
        raise ValueError(
            f"{source.source_location}: top-level variable {variable_name!r} does "
            f"not match file stem {expected_stem!r}; battery identity is ambiguous"
        )
    battery_id = variable_name.strip()
    operations = _as_records(
        root_value["cycle"], context=f"{source.source_location}.{battery_id}.cycle"
    )
    inventory["battery_id"] = battery_id
    inventory["total_operation_count"] = len(operations)

    cycle_rows: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []
    discharge_index = 0
    for operation_index, operation in enumerate(operations, start=1):
        operation_type = _text_scalar(
            operation.get("type", ""),
            context=f"{source.source_location}.cycle[{operation_index}].type",
        ).lower()
        if operation_type == "charge":
            inventory["charge_operation_count"] += 1
            continue
        if operation_type == "impedance":
            inventory["impedance_operation_count"] += 1
            continue
        if operation_type != "discharge":
            inventory["other_operation_count"] += 1
            continue

        inventory["discharge_operation_count"] += 1
        discharge_index += 1
        context = f"{source.source_location}.cycle[{operation_index}]"
        data = _as_mapping(operation.get("data"), context=f"{context}.data")
        voltage = _numeric_vector(
            data.get("Voltage_measured"),
            context=f"{context}.data.Voltage_measured",
        )
        current = _numeric_vector(
            data.get("Current_measured"),
            context=f"{context}.data.Current_measured",
        )
        elapsed = _numeric_vector(data.get("Time"), context=f"{context}.data.Time")
        if not (len(voltage) == len(current) == len(elapsed)):
            raise ValueError(
                f"{context}: Voltage_measured, Current_measured, and Time lengths "
                "must match"
            )
        if (elapsed < 0).any() or not (np.diff(elapsed) > 0).all():
            raise ValueError(
                f"{context}: discharge Time must be non-negative and strictly increasing"
            )
        if (voltage <= 0).any():
            raise ValueError(f"{context}: Voltage_measured must be positive")

        temperature = _optional_numeric_vector(
            data, "Temperature_measured", context=f"{context}.data"
        )
        if temperature is not None and len(temperature) != len(elapsed):
            raise ValueError(f"{context}: Temperature_measured length must match Time")

        capacity = _positive_scalar(
            data.get("Capacity"), context=f"{context}.data.Capacity"
        )
        ambient = _optional_scalar(operation.get("ambient_temperature"))
        started_at = _parse_matlab_datetime(operation.get("time"))
        if elapsed[0] != 0.0:
            warnings.append(
                {
                    "severity": "warning",
                    "code": "discharge_time_does_not_start_at_zero",
                    "message": (
                        "Source discharge Time was retained without shifting; verify "
                        "the source timing convention."
                    ),
                    "source_location": source.source_location,
                    "battery_id": battery_id,
                    "source_operation_index": operation_index,
                    "cycle_index": discharge_index,
                }
            )

        cycle_rows.append(
            {
                "battery_id": battery_id,
                "cycle_index": discharge_index,
                "discharge_capacity_ah": capacity,
                "ambient_temperature_c": ambient,
                "source_mat_file": source.source_location,
                "source_operation_index": operation_index,
                "_operation_started_at": started_at,
            }
        )
        cumulative_capacity = _cumulative_capacity_ah(current, elapsed)
        for point_index in range(len(elapsed)):
            row: dict[str, Any] = {
                "battery_id": battery_id,
                "cycle_index": discharge_index,
                "step_id": "discharge_1",
                "step_type": "discharge",
                "elapsed_time_s": float(elapsed[point_index]),
                "voltage_v": float(voltage[point_index]),
                "current_a": float(current[point_index]),
                "capacity_ah": float(cumulative_capacity[point_index]),
                "source_mat_file": source.source_location,
                "source_operation_index": operation_index,
                "source_point_index": point_index,
                "_operation_started_at": started_at,
            }
            if temperature is not None:
                row["temperature_c"] = float(temperature[point_index])
            raw_rows.append(row)

    if not cycle_rows:
        inventory["skip_reason"] = "no_discharge_operations"
        return None, [], [], inventory, warnings
    inventory["imported"] = True
    return battery_id, cycle_rows, raw_rows, inventory, warnings


def _validate_aware_timestamp(value: str, *, context: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{context} may not be blank")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{context} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{context} must include a timezone offset")
    return text


def _load_retrieval_receipt(
    path: Path | None,
    *,
    input_path: Path,
    input_metadata: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if path is None:
        return None, [
            {
                "severity": "warning",
                "code": "retrieval_receipt_not_supplied",
                "message": (
                    "The importer cannot verify when or from which URL the local "
                    "source was acquired. Generated provenance will remain incomplete "
                    "for predictive admission unless --retrieved-at is explicitly supplied."
                ),
                "source_location": str(input_path),
                "battery_id": None,
                "source_operation_index": None,
                "cycle_index": None,
            }
        ]
    if not path.is_file():
        raise FileNotFoundError(f"retrieval receipt not found: {path}")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, Mapping):
        raise ValueError("retrieval receipt must be a JSON object")
    required = {"source_url", "retrieved_at", "archive_sha256"}
    missing = sorted(
        field for field in required if field not in loaded or not loaded[field]
    )
    if missing:
        raise ValueError(
            "retrieval receipt missing required fields: " + ", ".join(missing)
        )
    if input_metadata["input_kind"] != "zip_archive":
        raise ValueError(
            "retrieval receipt verification currently requires the original ZIP input"
        )
    source_url = str(loaded["source_url"]).strip()
    if not source_url.lower().startswith("https://"):
        raise ValueError("retrieval receipt source_url must use HTTPS")
    _validate_aware_timestamp(
        str(loaded["retrieved_at"]),
        context="retrieval receipt retrieved_at",
    )
    actual = str(input_metadata["input_sha256"])
    declared = str(loaded["archive_sha256"]).lower()
    if declared != actual.lower():
        raise ValueError(
            "retrieval receipt archive_sha256 does not match the supplied ZIP"
        )
    receipt = dict(loaded)
    receipt["receipt_sha256"] = file_sha256(path)
    return receipt, []


def _prepare_output(output: Path, *, overwrite: bool) -> None:
    if output.exists() and not output.is_dir():
        raise FileExistsError(f"output path is not a directory: {output}")
    if output.exists() and any(output.iterdir()):
        if not overwrite:
            raise FileExistsError(
                f"output directory is non-empty: {output}; choose another path or pass overwrite=True"
            )
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)


def _protocol_summary(
    cycle_summary: pd.DataFrame,
    raw_signal: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for battery_id, cycle_group in cycle_summary.groupby("battery_id", sort=True):
        raw_group = raw_signal[raw_signal["battery_id"] == battery_id]
        durations = (
            raw_group.groupby("cycle_index", sort=True)["elapsed_time_s"]
            .agg(lambda values: float(values.max() - values.min()))
            .to_numpy(dtype=float)
        )
        intervals: list[float] = []
        for _, signal_cycle in raw_group.groupby("cycle_index", sort=True):
            values = np.sort(signal_cycle["elapsed_time_s"].to_numpy(dtype=float))
            intervals.extend(np.diff(values).tolist())
        ambient = cycle_group["ambient_temperature_c"].dropna().to_numpy(dtype=float)
        capacity = cycle_group["discharge_capacity_ah"].to_numpy(dtype=float)
        rows.append(
            {
                "battery_id": battery_id,
                "discharge_cycle_count": int(len(cycle_group)),
                "raw_point_count": int(len(raw_group)),
                "ambient_temperature_min_c": (
                    float(np.min(ambient)) if len(ambient) else math.nan
                ),
                "ambient_temperature_median_c": (
                    float(np.median(ambient)) if len(ambient) else math.nan
                ),
                "ambient_temperature_max_c": (
                    float(np.max(ambient)) if len(ambient) else math.nan
                ),
                "voltage_min_v": float(raw_group["voltage_v"].min()),
                "voltage_max_v": float(raw_group["voltage_v"].max()),
                "current_abs_median_a": float(raw_group["current_a"].abs().median()),
                "current_abs_max_a": float(raw_group["current_a"].abs().max()),
                "sample_interval_median_s": (
                    float(np.median(intervals)) if intervals else math.nan
                ),
                "discharge_duration_median_s": (
                    float(np.median(durations)) if len(durations) else math.nan
                ),
                "initial_discharge_capacity_ah": float(capacity[0]),
                "final_discharge_capacity_ah": float(capacity[-1]),
                "minimum_discharge_capacity_ah": float(np.min(capacity)),
                "maximum_discharge_capacity_ah": float(np.max(capacity)),
            }
        )
    return pd.DataFrame(rows)


def import_nasa_pcoe_battery(
    *,
    input_path: str | Path,
    output_dir: str | Path,
    retrieval_receipt_path: str | Path | None = None,
    retrieved_at: str | None = None,
    source_identifier: str = NASA_PCOE_SOURCE_IDENTIFIER,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Convert local NASA PCoE MATLAB sources to canonical auditable CSV files."""
    source_input = Path(input_path)
    output = Path(output_dir)
    if not source_input.exists():
        raise FileNotFoundError(f"NASA PCoE input not found: {source_input}")
    _prepare_output(output, overwrite=overwrite)

    with tempfile.TemporaryDirectory(prefix="mda_nasa_pcoe_") as temporary:
        temporary_directory = Path(temporary)
        sources, input_metadata = _discover_mat_sources(
            source_input, temporary_directory
        )
        receipt, receipt_warnings = _load_retrieval_receipt(
            (
                Path(retrieval_receipt_path)
                if retrieval_receipt_path is not None
                else None
            ),
            input_path=source_input,
            input_metadata=input_metadata,
        )
        if retrieved_at is not None:
            retrieved_at = _validate_aware_timestamp(
                retrieved_at,
                context="retrieved_at",
            )
            if receipt is None:
                receipt_warnings = [
                    {
                        "severity": "info",
                        "code": "retrieval_time_user_declared_without_receipt",
                        "message": (
                            "The acquisition timestamp was explicitly supplied, "
                            "but archive transport was not verified by a receipt."
                        ),
                        "source_location": str(source_input),
                        "battery_id": None,
                        "source_operation_index": None,
                        "cycle_index": None,
                    }
                ]
        if not str(source_identifier).strip():
            raise ValueError("source_identifier may not be blank")

        all_cycles: list[dict[str, Any]] = []
        all_raw: list[dict[str, Any]] = []
        inventory_rows: list[dict[str, Any]] = []
        warnings = list(receipt_warnings)
        battery_locations: dict[str, str] = {}
        for source in sources:
            battery_id, cycle_rows, raw_rows, inventory, source_warnings = (
                _load_source(source)
            )
            inventory_rows.append(inventory)
            warnings.extend(source_warnings)
            if battery_id is None:
                continue
            normalized = battery_id.casefold()
            if normalized in battery_locations:
                raise ValueError(
                    f"duplicate battery identity {battery_id!r} in "
                    f"{battery_locations[normalized]!r} and {source.source_location!r}"
                )
            battery_locations[normalized] = source.source_location
            all_cycles.extend(cycle_rows)
            all_raw.extend(raw_rows)

    if not all_cycles or not all_raw:
        raise ValueError("no valid NASA PCoE discharge trajectories were imported")

    cycle_summary = pd.DataFrame(all_cycles).sort_values(
        ["battery_id", "cycle_index"], kind="mergesort"
    )
    raw_signal = pd.DataFrame(all_raw).sort_values(
        ["battery_id", "cycle_index", "elapsed_time_s"], kind="mergesort"
    )

    reference = cycle_summary.groupby("battery_id", sort=True)[
        "discharge_capacity_ah"
    ].transform("first")
    cycle_summary["reference_capacity_ah"] = reference
    cycle_summary["capacity_retention_percent"] = (
        100.0 * cycle_summary["discharge_capacity_ah"] / reference
    )

    starts = cycle_summary["_operation_started_at"]
    if starts.notna().all():
        base_by_battery = (
            cycle_summary.groupby("battery_id", sort=True)["_operation_started_at"]
            .min()
            .to_dict()
        )
        raw_signal["global_time_s"] = [
            (started - base_by_battery[battery_id]).total_seconds() + float(elapsed)
            for battery_id, started, elapsed in zip(
                raw_signal["battery_id"],
                raw_signal["_operation_started_at"],
                raw_signal["elapsed_time_s"],
                strict=True,
            )
        ]
    else:
        warnings.append(
            {
                "severity": "warning",
                "code": "global_time_omitted_incomplete_operation_timestamps",
                "message": (
                    "At least one MATLAB operation timestamp was missing or invalid; "
                    "global_time_s was omitted for the complete canonical table."
                ),
                "source_location": str(source_input),
                "battery_id": None,
                "source_operation_index": None,
                "cycle_index": None,
            }
        )

    if "temperature_c" in raw_signal.columns and raw_signal["temperature_c"].isna().any():
        raw_signal = raw_signal.drop(columns=["temperature_c"])
        warnings.append(
            {
                "severity": "warning",
                "code": "temperature_omitted_incomplete_coverage",
                "message": (
                    "Temperature_measured was not available for every imported point; "
                    "temperature_c was omitted rather than partially imputed."
                ),
                "source_location": str(source_input),
                "battery_id": None,
                "source_operation_index": None,
                "cycle_index": None,
            }
        )

    cycle_summary["operation_started_at_source_time"] = cycle_summary[
        "_operation_started_at"
    ].map(lambda value: value.isoformat() if value is not None else None)
    cycle_summary = cycle_summary.drop(columns=["_operation_started_at"])
    raw_signal = raw_signal.drop(columns=["_operation_started_at"])

    cycle_columns = [
        "battery_id",
        "cycle_index",
        "discharge_capacity_ah",
        "reference_capacity_ah",
        "capacity_retention_percent",
        "ambient_temperature_c",
        "operation_started_at_source_time",
        "source_mat_file",
        "source_operation_index",
    ]
    raw_columns = [
        "battery_id",
        "cycle_index",
        "step_id",
        "step_type",
        "elapsed_time_s",
        "voltage_v",
        "current_a",
    ]
    for optional in ("temperature_c", "capacity_ah", "global_time_s"):
        if optional in raw_signal.columns:
            raw_columns.append(optional)
    raw_columns.extend(
        ["source_mat_file", "source_operation_index", "source_point_index"]
    )
    cycle_summary = cycle_summary[cycle_columns].reset_index(drop=True)
    raw_signal = raw_signal[raw_columns].reset_index(drop=True)
    inventory = pd.DataFrame(inventory_rows).sort_values(
        "source_location", kind="mergesort"
    )
    protocol = _protocol_summary(cycle_summary, raw_signal)
    warning_table = pd.DataFrame(warnings)
    if warning_table.empty:
        warning_table = pd.DataFrame(
            columns=[
                "severity",
                "code",
                "message",
                "source_location",
                "battery_id",
                "source_operation_index",
                "cycle_index",
            ]
        )

    cycle_path = output / "nasa_pcoe_cycle_summary.csv"
    raw_path = output / "nasa_pcoe_raw_signal.csv"
    inventory_path = output / "nasa_pcoe_source_inventory.csv"
    protocol_path = output / "nasa_pcoe_protocol_summary.csv"
    warnings_path = output / "nasa_pcoe_import_warnings.csv"
    provenance_path = output / "nasa_pcoe_raw_signal_provenance.json"
    manifest_path = output / "nasa_pcoe_import_manifest.json"

    cycle_summary.to_csv(cycle_path, index=False, lineterminator="\n")
    raw_signal.to_csv(raw_path, index=False, lineterminator="\n")
    inventory.to_csv(inventory_path, index=False, lineterminator="\n")
    protocol.to_csv(protocol_path, index=False, lineterminator="\n")
    warning_table.to_csv(warnings_path, index=False, lineterminator="\n")

    explicit_retrieved_at = retrieved_at
    if receipt is not None:
        receipt_retrieved_at = str(receipt["retrieved_at"])
        if explicit_retrieved_at and explicit_retrieved_at != receipt_retrieved_at:
            raise ValueError("--retrieved-at conflicts with the verified retrieval receipt")
        explicit_retrieved_at = receipt_retrieved_at
        source_identifier = str(receipt["source_url"])

    provenance = {
        "schema_version": IMPORT_SCHEMA_VERSION,
        "source_name": NASA_PCOE_SOURCE_NAME,
        "source_identifier": source_identifier,
        "retrieved_at": explicit_retrieved_at or "",
        "source_sha256": file_sha256(raw_path),
        "license_or_terms": NASA_PCOE_TERMS,
        "battery_id_mapping_method": (
            "Exact case-insensitive agreement between each MATLAB filename stem "
            "and its sole top-level variable; the original variable text is retained."
        ),
        "cycle_mapping_method": (
            "One-based sequential ordinal of discharge operations in source order "
            "within each battery MATLAB file. Charge and impedance operations are "
            "not inferred into discharge-cycle identities."
        ),
        "unit_declarations": {
            "elapsed_time_s": "s",
            "voltage_v": "V",
            "current_a": "A",
            "temperature_c": "degC",
            "capacity_ah": "Ah",
            "global_time_s": "s",
        },
        "dataset_citation": NASA_PCOE_CITATION,
        "official_download_url": NASA_PCOE_DOWNLOAD_URL,
        "input": input_metadata,
        "retrieval_receipt": receipt,
        "transformation": {
            "name": "mda_nasa_pcoe_mat_to_canonical_csv",
            "version": IMPORT_SCHEMA_VERSION,
            "imported_operation_type": "discharge",
            "capacity_ah_derivation": (
                "Cumulative trapezoidal integral of absolute Current_measured over "
                "source Time, divided by 3600."
            ),
            "global_time_s_derivation": (
                "Relative difference between source operation timestamps within each battery "
                "plus source elapsed Time. Source timezone is not asserted; the "
                "column is omitted unless every operation timestamp is valid."
            ),
            "no_interpolation": True,
            "no_smoothing": True,
            "no_outlier_removal": True,
        },
        "source_file_checksums": {
            str(row["source_location"]): str(row["mat_sha256"])
            for _, row in inventory[inventory["imported"]].iterrows()
        },
    }
    provenance_path.write_text(canonical_json(provenance), encoding="utf-8")

    manifest = {
        "schema_version": IMPORT_SCHEMA_VERSION,
        "artifact_kind": "nasa_pcoe_battery_import",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": input_metadata,
        "retrieval_receipt_verified": receipt is not None,
        "battery_count": int(cycle_summary["battery_id"].nunique()),
        "discharge_cycle_count": int(len(cycle_summary)),
        "raw_point_count": int(len(raw_signal)),
        "source_mat_file_count": int(inventory["imported"].sum()),
        "skipped_mat_file_count": int((~inventory["imported"]).sum()),
        "warning_count": int(len(warning_table)),
        "outputs": {
            "cycle_summary": str(cycle_path),
            "raw_signal": str(raw_path),
            "raw_signal_provenance": str(provenance_path),
            "source_inventory": str(inventory_path),
            "protocol_summary": str(protocol_path),
            "import_warnings": str(warnings_path),
            "manifest": str(manifest_path),
        },
        "output_sha256": {
            "cycle_summary": file_sha256(cycle_path),
            "raw_signal": file_sha256(raw_path),
            "raw_signal_provenance": file_sha256(provenance_path),
            "source_inventory": file_sha256(inventory_path),
            "protocol_summary": file_sha256(protocol_path),
            "import_warnings": file_sha256(warnings_path),
        },
        "scientific_boundary": (
            "Successful import validates software conversion and provenance fields. "
            "It does not establish source comparability, degradation mechanism, "
            "predictive value, external generalization, or engineering readiness."
        ),
    }
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
    return manifest
