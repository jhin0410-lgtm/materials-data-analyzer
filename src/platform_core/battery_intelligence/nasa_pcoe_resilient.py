"""Public NASA PCoE importer with explicit invalid-capacity quarantine.

The official NASA archive contains a small number of discharge operations whose
scalar ``Capacity`` field is zero or negative. Those operations cannot serve as
physical degradation targets. They are therefore excluded from the canonical
cycle-summary and raw-signal tables, while their original discharge ordinal,
source operation index, observed value, and exclusion counts remain auditable.

No value is imputed, clipped, smoothed, or renumbered.
"""
from __future__ import annotations

import json
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


def _load_source_with_invalid_capacity_quarantine(
    source: Any,
) -> tuple[
    str | None,
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
]:
    """Load one MAT source while quarantining nonpositive capacity operations."""
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
    inventory = _base._empty_inventory(source)
    inventory["imported_discharge_operation_count"] = 0
    inventory["excluded_discharge_operation_count"] = 0
    inventory["nonpositive_capacity_operation_count"] = 0
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

        capacity = _base._optional_scalar(data.get("Capacity"))
        if capacity is None:
            raise ValueError(
                f"{context}.data.Capacity must contain one finite numeric value"
            )
        if capacity <= 0:
            inventory["excluded_discharge_operation_count"] += 1
            inventory["nonpositive_capacity_operation_count"] += 1
            warning = _base._warning(
                "nonpositive_discharge_capacity_excluded",
                (
                    f"Source discharge Capacity={capacity!r} Ah is not a valid "
                    "positive degradation target. The operation was excluded from "
                    "canonical cycle and raw-signal tables without changing later "
                    "source discharge ordinals. No value was imputed or clipped."
                ),
                source_location=source.source_location,
                battery_id=battery_id,
                source_operation_index=operation_index,
                cycle_index=discharge_index,
            )
            warning["observed_value"] = float(capacity)
            warnings.append(warning)
            continue

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
        return None, [], [], inventory, warnings
    inventory["imported"] = True
    return battery_id, cycle_rows, raw_rows, inventory, warnings


def _enrich_audit_outputs(output: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    inventory_path = output / "nasa_pcoe_source_inventory.csv"
    provenance_path = output / "nasa_pcoe_raw_signal_provenance.json"
    inventory = pd.read_csv(inventory_path)
    countable = inventory[
        inventory["skip_reason"].fillna("") != _DUPLICATE_SKIP_REASON
    ]

    excluded = int(
        countable.get(
            "excluded_discharge_operation_count", pd.Series(dtype=int)
        ).fillna(0).sum()
    )
    nonpositive = int(
        countable.get(
            "nonpositive_capacity_operation_count", pd.Series(dtype=int)
        ).fillna(0).sum()
    )
    imported = int(
        countable.get(
            "imported_discharge_operation_count", pd.Series(dtype=int)
        ).fillna(0).sum()
    )

    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    transformation = provenance.setdefault("transformation", {})
    transformation["nonpositive_capacity_policy"] = (
        "A discharge operation with finite Capacity <= 0 Ah is retained in source "
        "inventory and import warnings but excluded from canonical cycle-summary "
        "and raw-signal tables. Later discharge ordinals are not renumbered. No "
        "imputation, clipping, interpolation, smoothing, or outlier deletion is used."
    )
    transformation["excluded_nonpositive_capacity_operation_count"] = nonpositive
    provenance_path.write_text(canonical_json(provenance), encoding="utf-8")

    manifest["imported_discharge_operation_count"] = imported
    manifest["excluded_discharge_operation_count"] = excluded
    manifest["nonpositive_capacity_operation_count"] = nonpositive
    manifest["output_sha256"]["raw_signal_provenance"] = file_sha256(
        provenance_path
    )
    manifest["scientific_boundary"] = (
        str(manifest["scientific_boundary"])
        + " Nonpositive source Capacity operations are explicit quarantines, not "
        "evidence of zero physical capacity and not silently repaired data."
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
    """Import NASA PCoE data with auditable nonpositive-capacity quarantine."""
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
