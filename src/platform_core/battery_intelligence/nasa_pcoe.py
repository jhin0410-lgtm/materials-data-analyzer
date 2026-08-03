"""Offline conversion of NASA PCoE battery-aging MATLAB files.

The module performs no network access. It converts one local ``.mat`` file, a
MAT directory, or a ZIP archive (including bounded nested ZIPs) into the
canonical cycle-summary and raw-signal contracts consumed by Battery
Degradation Intelligence.
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
from platform_core.output_safety import transactional_output_directory
from platform_core.runtime_provenance import runtime_environment


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
MAX_TOTAL_EXTRACTED_BYTES = 8_000_000_000
MAX_COMPRESSION_RATIO = 500.0


@dataclass(frozen=True)
class _MatSource:
    path: Path
    source_location: str


def _warning(
    code: str,
    message: str,
    *,
    source_location: str,
    battery_id: str | None = None,
    source_operation_index: int | None = None,
    cycle_index: int | None = None,
    severity: str = "warning",
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "source_location": source_location,
        "battery_id": battery_id,
        "source_operation_index": source_operation_index,
        "cycle_index": cycle_index,
    }


def _safe_archive_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe archive member path: {name!r}")
    if path.parts and ":" in path.parts[0]:
        raise ValueError(f"unsafe archive member drive path: {name!r}")
    return path



def _copy_archive_member_limited(
    source: Any, target: Any, *, state: dict[str, int], member_name: str
) -> int:
    written = 0
    while True:
        chunk = source.read(1024 * 1024)
        if not chunk:
            break
        written += len(chunk)
        state["extracted_bytes"] += len(chunk)
        if state["extracted_bytes"] > MAX_TOTAL_EXTRACTED_BYTES:
            raise ValueError(
                "archive cumulative extracted bytes exceed "
                f"{MAX_TOTAL_EXTRACTED_BYTES}: {member_name}"
            )
        target.write(chunk)
    return written

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
            compression_ratio = info.file_size / max(info.compress_size, 1)
            if info.file_size >= 1_000_000 and compression_ratio > MAX_COMPRESSION_RATIO:
                raise ValueError(
                    "archive member compression ratio exceeds "
                    f"{MAX_COMPRESSION_RATIO}: {info.filename}"
                )
            if member.suffix.lower() not in {".mat", ".zip"}:
                continue
            state["files"] += 1
            local = destination / f"{state['files']:06d}_{member.name}"
            with archive.open(info) as source, local.open("wb") as target:
                written = _copy_archive_member_limited(
                    source, target, state=state, member_name=info.filename
                )
            if written != info.file_size:
                raise ValueError(
                    f"archive member size mismatch after extraction: {info.filename}"
                )
            location = f"{source_prefix}!{member.as_posix()}"
            if member.suffix.lower() == ".mat":
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
        extraction_state = {"members": 0, "files": 0, "extracted_bytes": 0}
        sources = _extract_zip_recursive(
            input_path,
            temporary_directory,
            source_prefix=input_path.name,
            depth=0,
            state=extraction_state,
        )
        metadata = {
            "input_kind": "zip_archive",
            "input_path": str(input_path),
            "input_sha256": file_sha256(input_path),
            "archive_member_count": extraction_state["members"],
            "archive_extracted_file_count": extraction_state["files"],
            "archive_extracted_bytes": extraction_state["extracted_bytes"],
            "archive_resource_limits": {
                "max_depth": MAX_ARCHIVE_DEPTH,
                "max_members": MAX_ARCHIVE_MEMBERS,
                "max_member_bytes": MAX_MEMBER_BYTES,
                "max_total_extracted_bytes": MAX_TOTAL_EXTRACTED_BYTES,
                "max_compression_ratio": MAX_COMPRESSION_RATIO,
            },
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
        values = [value]
    elif isinstance(value, np.ndarray):
        values = value.reshape(-1).tolist()
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        values = list(value)
    else:
        values = [value]
    return [
        _as_mapping(item, context=f"{context}[{index}]")
        for index, item in enumerate(values, start=1)
    ]


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
    data: Mapping[str, Any], field: str, *, context: str
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
    seconds = float(vector[5])
    second = int(math.floor(seconds))
    microsecond = int(round((seconds - second) * 1_000_000))
    if microsecond == 1_000_000:
        second += 1
        microsecond = 0
    try:
        return datetime(year, month, day, hour, minute, second, microsecond)
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


def _empty_inventory(source: _MatSource) -> dict[str, Any]:
    return {
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
    inventory = _empty_inventory(source)
    warnings: list[dict[str, Any]] = []
    if len(variables) != 1:
        inventory["skip_reason"] = "expected_exactly_one_top_level_variable"
        return None, [], [], inventory, warnings

    variable_name, root_value = next(iter(variables.items()))
    if not isinstance(root_value, Mapping) or "cycle" not in root_value:
        inventory["skip_reason"] = "top_level_variable_has_no_cycle_structure"
        return None, [], [], inventory, warnings

    expected_stem = PurePosixPath(source.source_location.split("!")[-1]).stem
    if variable_name.strip().casefold() != expected_stem.strip().casefold():
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
                _warning(
                    "discharge_time_does_not_start_at_zero",
                    "Source discharge Time was retained without shifting; verify the source timing convention.",
                    source_location=source.source_location,
                    battery_id=battery_id,
                    source_operation_index=operation_index,
                    cycle_index=discharge_index,
                )
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
            _warning(
                "retrieval_receipt_not_supplied",
                "The importer cannot verify when or from which URL the local source was acquired. Generated provenance remains incomplete unless --retrieved-at is supplied.",
                source_location=str(input_path),
            )
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
        str(loaded["retrieved_at"]), context="retrieval receipt retrieved_at"
    )
    actual = str(input_metadata["input_sha256"])
    if str(loaded["archive_sha256"]).lower() != actual.lower():
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
    cycle_summary: pd.DataFrame, raw_signal: pd.DataFrame
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
                "ambient_temperature_min_c": float(np.min(ambient)) if len(ambient) else math.nan,
                "ambient_temperature_median_c": float(np.median(ambient)) if len(ambient) else math.nan,
                "ambient_temperature_max_c": float(np.max(ambient)) if len(ambient) else math.nan,
                "voltage_min_v": float(raw_group["voltage_v"].min()),
                "voltage_max_v": float(raw_group["voltage_v"].max()),
                "current_abs_median_a": float(raw_group["current_a"].abs().median()),
                "current_abs_max_a": float(raw_group["current_a"].abs().max()),
                "sample_interval_median_s": float(np.median(intervals)) if intervals else math.nan,
                "discharge_duration_median_s": float(np.median(durations)) if len(durations) else math.nan,
                "initial_discharge_capacity_ah": float(capacity[0]),
                "final_discharge_capacity_ah": float(capacity[-1]),
                "minimum_discharge_capacity_ah": float(np.min(capacity)),
                "maximum_discharge_capacity_ah": float(np.max(capacity)),
            }
        )
    return pd.DataFrame(rows)


def _deduplicate_source(
    *,
    battery_id: str,
    inventory: dict[str, Any],
    seen: dict[str, tuple[str, str]],
    warnings: list[dict[str, Any]],
) -> bool:
    """Return True only for an identical duplicate source copy.

    The official outer archive contains overlapping sub-bundles. Repeated battery
    IDs are accepted only when the MAT bytes are exactly identical; same-ID files
    with different checksums remain an ambiguity and fail closed.
    """
    normalized = battery_id.casefold()
    checksum = str(inventory["mat_sha256"])
    if normalized not in seen:
        seen[normalized] = (str(inventory["source_location"]), checksum)
        return False
    first_location, first_checksum = seen[normalized]
    if checksum != first_checksum:
        raise ValueError(
            f"duplicate battery identity {battery_id!r} has different MAT checksums in "
            f"{first_location!r} and {inventory['source_location']!r}"
        )
    inventory["imported"] = False
    inventory["skip_reason"] = "duplicate_identical_source_copy"
    warnings.append(
        _warning(
            "duplicate_identical_source_copy",
            f"An identical MAT copy was already imported from {first_location}; the repeated copy was retained in inventory and excluded from canonical rows.",
            source_location=str(inventory["source_location"]),
            battery_id=battery_id,
            severity="info",
        )
    )
    return True


def _import_nasa_pcoe_battery_in_directory(
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
    output.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="mda_nasa_pcoe_") as temporary:
        sources, input_metadata = _discover_mat_sources(
            source_input, Path(temporary)
        )
        receipt, receipt_warnings = _load_retrieval_receipt(
            Path(retrieval_receipt_path) if retrieval_receipt_path else None,
            input_path=source_input,
            input_metadata=input_metadata,
        )
        if retrieved_at is not None:
            retrieved_at = _validate_aware_timestamp(
                retrieved_at, context="retrieved_at"
            )
            if receipt is None:
                receipt_warnings = [
                    _warning(
                        "retrieval_time_user_declared_without_receipt",
                        "The acquisition timestamp was explicitly supplied, but archive transport was not verified by a receipt.",
                        source_location=str(source_input),
                        severity="info",
                    )
                ]
        if not str(source_identifier).strip():
            raise ValueError("source_identifier may not be blank")

        all_cycles: list[dict[str, Any]] = []
        all_raw: list[dict[str, Any]] = []
        inventory_rows: list[dict[str, Any]] = []
        warnings = list(receipt_warnings)
        seen_batteries: dict[str, tuple[str, str]] = {}
        for source in sources:
            battery_id, cycles, raw, inventory, source_warnings = _load_source(source)
            inventory_rows.append(inventory)
            warnings.extend(source_warnings)
            if battery_id is None:
                continue
            if _deduplicate_source(
                battery_id=battery_id,
                inventory=inventory,
                seen=seen_batteries,
                warnings=warnings,
            ):
                continue
            all_cycles.extend(cycles)
            all_raw.extend(raw)

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

    if cycle_summary["_operation_started_at"].notna().all():
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
            _warning(
                "global_time_omitted_incomplete_operation_timestamps",
                "At least one MATLAB operation timestamp was missing or invalid; global_time_s was omitted for the complete canonical table.",
                source_location=str(source_input),
            )
        )

    if "temperature_c" in raw_signal.columns and raw_signal["temperature_c"].isna().any():
        raw_signal = raw_signal.drop(columns=["temperature_c"])
        warnings.append(
            _warning(
                "temperature_omitted_incomplete_coverage",
                "Temperature_measured was not available for every imported point; temperature_c was omitted rather than partially imputed.",
                source_location=str(source_input),
            )
        )

    cycle_summary["operation_started_at_source_time"] = cycle_summary[
        "_operation_started_at"
    ].map(lambda value: value.isoformat() if value is not None else None)
    cycle_summary = cycle_summary.drop(columns=["_operation_started_at"])
    raw_signal = raw_signal.drop(columns=["_operation_started_at"])

    cycle_summary = cycle_summary[
        [
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
    ].reset_index(drop=True)
    raw_columns = [
        "battery_id",
        "cycle_index",
        "step_id",
        "step_type",
        "elapsed_time_s",
        "voltage_v",
        "current_a",
    ]
    raw_columns.extend(
        column
        for column in ("temperature_c", "capacity_ah", "global_time_s")
        if column in raw_signal.columns
    )
    raw_columns.extend(
        ["source_mat_file", "source_operation_index", "source_point_index"]
    )
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

    paths = {
        "cycle_summary": output / "nasa_pcoe_cycle_summary.csv",
        "raw_signal": output / "nasa_pcoe_raw_signal.csv",
        "source_inventory": output / "nasa_pcoe_source_inventory.csv",
        "protocol_summary": output / "nasa_pcoe_protocol_summary.csv",
        "import_warnings": output / "nasa_pcoe_import_warnings.csv",
        "raw_signal_provenance": output / "nasa_pcoe_raw_signal_provenance.json",
        "manifest": output / "nasa_pcoe_import_manifest.json",
    }
    cycle_summary.to_csv(paths["cycle_summary"], index=False, lineterminator="\n")
    raw_signal.to_csv(paths["raw_signal"], index=False, lineterminator="\n")
    inventory.to_csv(paths["source_inventory"], index=False, lineterminator="\n")
    protocol.to_csv(paths["protocol_summary"], index=False, lineterminator="\n")
    warning_table.to_csv(paths["import_warnings"], index=False, lineterminator="\n")

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
        "source_sha256": file_sha256(paths["raw_signal"]),
        "license_or_terms": NASA_PCOE_TERMS,
        "battery_id_mapping_method": (
            "Exact case-insensitive agreement between each MATLAB filename stem and its sole top-level variable. Repeated battery IDs are deduplicated only when MAT SHA-256 values are identical."
        ),
        "cycle_mapping_method": (
            "One-based sequential ordinal of discharge operations in source order within each unique battery MATLAB file. Charge and impedance operations are not inferred into discharge-cycle identities."
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
                "Cumulative trapezoidal integral of absolute Current_measured over source Time, divided by 3600."
            ),
            "global_time_s_derivation": (
                "Relative difference between source operation timestamps within each battery plus source elapsed Time. Source timezone is not asserted; the column is omitted unless every operation timestamp is valid."
            ),
            "identical_duplicate_policy": (
                "Same battery ID and identical MAT SHA-256: one canonical copy; same ID and different SHA-256: fatal ambiguity."
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
    paths["raw_signal_provenance"].write_text(
        canonical_json(provenance), encoding="utf-8"
    )

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
        "identical_duplicate_copy_count": int(
            (inventory["skip_reason"] == "duplicate_identical_source_copy").sum()
        ),
        "warning_count": int(len(warning_table)),
        "outputs": {name: path.name for name, path in paths.items()},
        "output_byte_count": {
            name: path.stat().st_size
            for name, path in paths.items()
            if name != "manifest" and path.is_file()
        },
        "output_sha256": {
            name: file_sha256(path)
            for name, path in paths.items()
            if name != "manifest"
        },
        "terminal_status": "completed",
        "runtime_environment": runtime_environment(),
        "scientific_boundary": (
            "Successful import validates software conversion and provenance fields. It does not establish source comparability, degradation mechanism, predictive value, external generalization, or engineering readiness."
        ),
    }
    paths["manifest"].write_text(canonical_json(manifest), encoding="utf-8")
    return manifest


def import_nasa_pcoe_battery(
    *,
    input_path: str | Path,
    output_dir: str | Path,
    retrieval_receipt_path: str | Path | None = None,
    retrieved_at: str | None = None,
    source_identifier: str = NASA_PCOE_SOURCE_IDENTIFIER,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Import NASA PCoE data using a protected transactional output directory."""
    protected: list[Path] = [Path(input_path)]
    if retrieval_receipt_path is not None:
        protected.append(Path(retrieval_receipt_path))
    with transactional_output_directory(
        output_dir,
        overwrite=overwrite,
        protected_paths=protected,
        recognized_markers=("nasa_pcoe_import_manifest.json",),
    ) as staging_output:
        manifest = _import_nasa_pcoe_battery_in_directory(
            input_path=input_path,
            output_dir=staging_output,
            retrieval_receipt_path=retrieval_receipt_path,
            retrieved_at=retrieved_at,
            source_identifier=source_identifier,
            overwrite=False,
        )
    return manifest
