"""NASA PCoE importer with auditable invalid-capacity quarantine.

Some official NASA PCoE discharge operations contain a ``Capacity`` field that
cannot be used as a physical degradation target: it may be missing, nonnumeric,
non-scalar, complex-valued, non-finite, zero, or negative. Those operations are excluded from
canonical cycle-summary and raw-signal tables, while their original source
identity, discharge ordinal, observed representation, and exclusion reason
remain auditable.

No capacity value is imputed, clipped, smoothed, interpolated, or renumbered.
Structural signal corruption remains fatal.
"""
from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Any

import numpy as np
import pandas as pd

from . import nasa_pcoe as _base
from .common import canonical_json, file_sha256


_IMPORT_LOCK = RLock()
_DUPLICATE_SKIP_REASON = "duplicate_identical_source_copy"
_EXCLUDED_OPERATIONS_FILENAME = "nasa_pcoe_excluded_operations.csv"
_INVALID_CAPACITY_REASONS = (
    "missing",
    "nonnumeric",
    "nonscalar",
    "complex",
    "nonfinite",
    "nonpositive",
)


def _capacity_observation(value: Any, *, present: bool) -> tuple[float | None, str | None, str]:
    """Return ``(valid_value, issue, observed_repr)`` for one Capacity field."""
    if not present:
        return None, "missing", "missing:<missing>"
    try:
        raw = np.asarray(value)
    except (TypeError, ValueError):
        text = repr(value)
        return None, "nonnumeric", ("nonnumeric:" + text)[:500]
    flat = raw.reshape(-1)
    if np.iscomplexobj(raw) or any(isinstance(item, complex) for item in flat.tolist()):
        return None, "complex", ("complex:" + np.array2string(raw, threshold=20))[:500]
    try:
        array = np.asarray(value, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        text = repr(value)
        return None, "nonnumeric", ("nonnumeric:" + text)[:500]
    if array.size != 1:
        return None, "nonscalar", ("nonscalar:" + np.array2string(array, threshold=20))[:500]
    scalar = float(array[0])
    if not math.isfinite(scalar):
        return None, "nonfinite", f"nonfinite:{scalar!r}"
    if scalar <= 0:
        return None, "nonpositive", f"nonpositive:{scalar!r}"
    return scalar, None, repr(scalar)


def _inventory_with_capacity_counts(source: Any) -> dict[str, Any]:
    inventory = _base._empty_inventory(source)
    inventory["imported_discharge_operation_count"] = 0
    inventory["excluded_discharge_operation_count"] = 0
    inventory["invalid_capacity_operation_count"] = 0
    for reason in _INVALID_CAPACITY_REASONS:
        inventory[f"{reason}_capacity_operation_count"] = 0
    return inventory


def _invalid_capacity_warning(
    *,
    issue: str,
    observed: str,
    source_location: str,
    battery_id: str,
    operation_index: int,
    discharge_index: int,
) -> dict[str, Any]:
    warning = _base._warning(
        "invalid_discharge_capacity_excluded",
        (
            f"Source discharge Capacity is {issue} ({observed}) and cannot serve "
            "as a physical degradation target. The operation was excluded from "
            "canonical cycle-summary and raw-signal tables without changing later "
            "source discharge ordinals. No value was imputed, clipped, smoothed, "
            "or interpolated."
        ),
        source_location=source_location,
        battery_id=battery_id,
        source_operation_index=operation_index,
        cycle_index=discharge_index,
    )
    warning["capacity_issue"] = issue
    warning["observed_value"] = observed
    return warning


def _load_source_with_invalid_capacity_quarantine(
    source: Any,
) -> tuple[
    str | None,
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
]:
    """Load one MAT source while quarantining unusable Capacity targets."""
    try:
        loaded = _base.loadmat(source.path, simplify_cells=True)
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
    inventory = _inventory_with_capacity_counts(source)
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
    operations = _base._as_records(
        root_value["cycle"], context=f"{source.source_location}.{battery_id}.cycle"
    )
    inventory["battery_id"] = battery_id
    inventory["total_operation_count"] = len(operations)

    cycle_rows: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []
    discharge_index = 0
    for operation_index, operation in enumerate(operations, start=1):
        operation_type = _base._text_scalar(
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
        data = _base._as_mapping(operation.get("data"), context=f"{context}.data")

        # Validate the measured trajectory before deciding whether its target can
        # enter canonical tables. Corrupt vectors remain fatal rather than hidden
        # behind a target quarantine.
        voltage = _base._numeric_vector(
            data.get("Voltage_measured"),
            context=f"{context}.data.Voltage_measured",
        )
        current = _base._numeric_vector(
            data.get("Current_measured"),
            context=f"{context}.data.Current_measured",
        )
        elapsed = _base._numeric_vector(
            data.get("Time"), context=f"{context}.data.Time"
        )
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

        temperature = _base._optional_numeric_vector(
            data, "Temperature_measured", context=f"{context}.data"
        )
        if temperature is not None and len(temperature) != len(elapsed):
            raise ValueError(f"{context}: Temperature_measured length must match Time")

        capacity, issue, observed = _capacity_observation(
            data.get("Capacity"), present="Capacity" in data
        )
        if issue is not None:
            inventory["excluded_discharge_operation_count"] += 1
            inventory["invalid_capacity_operation_count"] += 1
            inventory[f"{issue}_capacity_operation_count"] += 1
            warnings.append(
                _invalid_capacity_warning(
                    issue=issue,
                    observed=observed,
                    source_location=source.source_location,
                    battery_id=battery_id,
                    operation_index=operation_index,
                    discharge_index=discharge_index,
                )
            )
            continue
        if capacity is None:
            raise RuntimeError("validated discharge capacity unexpectedly missing")

        ambient = _base._optional_scalar(operation.get("ambient_temperature"))
        started_at = _base._parse_matlab_datetime(operation.get("time"))
        if elapsed[0] != 0.0:
            warnings.append(
                _base._warning(
                    "discharge_time_does_not_start_at_zero",
                    "Source discharge Time was retained without shifting; verify the source timing convention.",
                    source_location=source.source_location,
                    battery_id=battery_id,
                    source_operation_index=operation_index,
                    cycle_index=discharge_index,
                )
            )

        inventory["imported_discharge_operation_count"] += 1
        cycle_rows.append(
            {
                "battery_id": battery_id,
                "cycle_index": discharge_index,
                "discharge_capacity_ah": float(capacity),
                "ambient_temperature_c": ambient,
                "source_mat_file": source.source_location,
                "source_operation_index": operation_index,
                "_operation_started_at": started_at,
            }
        )
        cumulative_capacity = _base._cumulative_capacity_ah(current, elapsed)
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
        inventory["skip_reason"] = (
            "no_valid_discharge_operations"
            if inventory["discharge_operation_count"]
            else "no_discharge_operations"
        )
        return battery_id, [], [], inventory, warnings
    inventory["imported"] = True
    return battery_id, cycle_rows, raw_rows, inventory, warnings


def _count_inventory(inventory: pd.DataFrame, column: str) -> int:
    countable = inventory[
        inventory["skip_reason"].fillna("") != _DUPLICATE_SKIP_REASON
    ]
    return int(countable.get(column, pd.Series(dtype=int)).fillna(0).sum())


def _write_excluded_operations(
    output: Path, inventory: pd.DataFrame
) -> tuple[Path, pd.DataFrame]:
    warnings_path = output / "nasa_pcoe_import_warnings.csv"
    warnings = pd.read_csv(warnings_path)
    excluded = warnings[
        warnings.get("code", pd.Series(dtype=str)).eq(
            "invalid_discharge_capacity_excluded"
        )
    ].copy()
    duplicate_locations = set(
        inventory.loc[
            inventory["skip_reason"].fillna("") == _DUPLICATE_SKIP_REASON,
            "source_location",
        ].astype(str)
    )
    if duplicate_locations and "source_location" in excluded:
        excluded = excluded[
            ~excluded["source_location"].astype(str).isin(duplicate_locations)
        ].copy()
    columns = [
        "source_location",
        "battery_id",
        "source_operation_index",
        "cycle_index",
        "capacity_issue",
        "observed_value",
        "severity",
        "code",
        "message",
    ]
    for column in columns:
        if column not in excluded:
            excluded[column] = pd.Series(dtype="object")
    excluded = excluded[columns].sort_values(
        ["battery_id", "cycle_index", "source_operation_index"],
        kind="mergesort",
        na_position="last",
    )
    path = output / _EXCLUDED_OPERATIONS_FILENAME
    excluded.to_csv(path, index=False, lineterminator="\n")
    return path, excluded


def _enrich_audit_outputs(output: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    inventory_path = output / "nasa_pcoe_source_inventory.csv"
    provenance_path = output / "nasa_pcoe_raw_signal_provenance.json"
    inventory = pd.read_csv(inventory_path)

    counts = {
        "imported_discharge_operation_count": _count_inventory(
            inventory, "imported_discharge_operation_count"
        ),
        "excluded_discharge_operation_count": _count_inventory(
            inventory, "excluded_discharge_operation_count"
        ),
        "invalid_capacity_operation_count": _count_inventory(
            inventory, "invalid_capacity_operation_count"
        ),
    }
    for reason in _INVALID_CAPACITY_REASONS:
        counts[f"{reason}_capacity_operation_count"] = _count_inventory(
            inventory, f"{reason}_capacity_operation_count"
        )

    excluded_path, excluded_table = _write_excluded_operations(output, inventory)
    if len(excluded_table) != counts["invalid_capacity_operation_count"]:
        raise RuntimeError(
            "excluded-operation artifact count does not reconcile with inventory"
        )

    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    transformation = provenance.setdefault("transformation", {})
    transformation["invalid_capacity_policy"] = (
        "A discharge operation whose Capacity target is missing, nonnumeric, "
        "non-scalar, complex-valued, non-finite, zero, or negative is retained in source inventory "
        "and exclusion artifacts but omitted from canonical cycle-summary and "
        "raw-signal tables. Later discharge ordinals are not renumbered. Measured "
        "trajectory vectors are validated before quarantine. No capacity value is "
        "imputed, clipped, interpolated, smoothed, or inferred."
    )
    transformation["excluded_invalid_capacity_operation_count"] = counts[
        "invalid_capacity_operation_count"
    ]
    transformation["invalid_capacity_counts_by_reason"] = {
        reason: counts[f"{reason}_capacity_operation_count"]
        for reason in _INVALID_CAPACITY_REASONS
    }
    provenance_path.write_text(canonical_json(provenance), encoding="utf-8")

    manifest.update(counts)
    manifest["excluded_operation_artifact_count"] = int(len(excluded_table))
    manifest["outputs"]["excluded_operations"] = str(excluded_path)
    manifest["output_sha256"]["excluded_operations"] = file_sha256(excluded_path)
    manifest["output_sha256"]["raw_signal_provenance"] = file_sha256(
        provenance_path
    )
    manifest["scientific_boundary"] = (
        str(manifest["scientific_boundary"])
        + " Invalid source Capacity operations are explicit target quarantines, "
        "not evidence of physical zero capacity and not silently repaired data."
    )
    manifest_path = output / "nasa_pcoe_import_manifest.json"
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
    return manifest


def import_nasa_pcoe_battery(
    *,
    input_path: str | Path,
    output_dir: str | Path,
    retrieval_receipt_path: str | Path | None = None,
    retrieved_at: str | None = None,
    source_identifier: str = _base.NASA_PCOE_SOURCE_IDENTIFIER,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Import NASA PCoE data with auditable invalid-capacity quarantine."""
    output = Path(output_dir)
    with _IMPORT_LOCK:
        original_loader = _base._load_source
        _base._load_source = _load_source_with_invalid_capacity_quarantine
        try:
            manifest = _base.import_nasa_pcoe_battery(
                input_path=input_path,
                output_dir=output,
                retrieval_receipt_path=retrieval_receipt_path,
                retrieved_at=retrieved_at,
                source_identifier=source_identifier,
                overwrite=overwrite,
            )
        finally:
            _base._load_source = original_loader
    return _enrich_audit_outputs(output, manifest)
