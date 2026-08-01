"""NASA PCoE import wrapper with source-rated capacity normalization.

The NASA Li-ion Battery Aging Dataset describes end of life as 30 percent fade
from a rated 2 Ah capacity to 1.4 Ah. A battery's first recorded discharge is
not necessarily a full rated-capacity discharge because load, temperature, and
cutoff voltage vary across experiments. Therefore the first observed discharge
must not silently define 100 percent retention.

This module preserves every source Capacity value and the resilient invalid-
capacity quarantine, then derives the forecasting target against the documented
2 Ah rated capacity. Protocol dependence remains explicit: rated-capacity
normalization does not make different current, temperature, or cutoff-voltage
conditions scientifically interchangeable.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .common import canonical_json, file_sha256
from .nasa_pcoe_resilient import import_nasa_pcoe_battery as _import_resilient

NASA_PCOE_RATED_CAPACITY_AH = 2.0
NASA_PCOE_REFERENCE_CAPACITY_METHOD = "source_rated_capacity_2_ah"
NASA_PCOE_RATED_CAPACITY_EVIDENCE = (
    "NASA Open Data Portal, Li-ion Battery Aging Datasets: experiments stop at "
    "30% fade in rated capacity, from 2 Ah to 1.4 Ah."
)


def _finite_positive(series: pd.Series, *, field: str) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    valid = np.isfinite(values.to_numpy(dtype=float)) & (values.to_numpy(dtype=float) > 0)
    if not bool(np.all(valid)):
        raise ValueError(
            f"NASA rated-capacity normalization requires finite positive {field}"
        )
    return values.astype(float)


def _rewrite_cycle_summary(output: Path) -> tuple[Path, pd.DataFrame]:
    path = output / "nasa_pcoe_cycle_summary.csv"
    cycle_summary = pd.read_csv(path)
    required = {"battery_id", "cycle_index", "discharge_capacity_ah"}
    missing = sorted(required - set(cycle_summary.columns))
    if missing:
        raise ValueError(
            "NASA cycle summary missing rated-reference columns: "
            + ", ".join(missing)
        )

    discharge = _finite_positive(
        cycle_summary["discharge_capacity_ah"], field="discharge_capacity_ah"
    )
    cycle_summary["reference_capacity_ah"] = NASA_PCOE_RATED_CAPACITY_AH
    cycle_summary["reference_capacity_method"] = (
        NASA_PCOE_REFERENCE_CAPACITY_METHOD
    )
    cycle_summary["capacity_retention_percent"] = (
        100.0 * discharge / NASA_PCOE_RATED_CAPACITY_AH
    )

    preferred = [
        "battery_id",
        "cycle_index",
        "discharge_capacity_ah",
        "reference_capacity_ah",
        "reference_capacity_method",
        "capacity_retention_percent",
        "ambient_temperature_c",
        "operation_started_at_source_time",
        "source_mat_file",
        "source_operation_index",
    ]
    ordered = [column for column in preferred if column in cycle_summary.columns]
    ordered.extend(column for column in cycle_summary.columns if column not in ordered)
    cycle_summary = cycle_summary[ordered]
    cycle_summary.to_csv(path, index=False, lineterminator="\n")
    return path, cycle_summary


def _rewrite_protocol_summary(
    output: Path, cycle_summary: pd.DataFrame
) -> tuple[Path, pd.DataFrame]:
    path = output / "nasa_pcoe_protocol_summary.csv"
    protocol = pd.read_csv(path)
    retention = (
        cycle_summary.groupby("battery_id", sort=True)["capacity_retention_percent"]
        .agg(["min", "median", "max"])
        .rename(
            columns={
                "min": "minimum_capacity_retention_percent",
                "median": "median_capacity_retention_percent",
                "max": "maximum_capacity_retention_percent",
            }
        )
        .reset_index()
    )
    protocol = protocol.drop(
        columns=[
            column
            for column in retention.columns
            if column != "battery_id" and column in protocol.columns
        ],
        errors="ignore",
    ).merge(retention, on="battery_id", how="left", validate="one_to_one")
    protocol["rated_capacity_ah"] = NASA_PCOE_RATED_CAPACITY_AH
    protocol["reference_capacity_method"] = NASA_PCOE_REFERENCE_CAPACITY_METHOD
    if "initial_discharge_capacity_ah" in protocol.columns:
        initial = pd.to_numeric(
            protocol["initial_discharge_capacity_ah"], errors="coerce"
        )
        protocol["initial_discharge_capacity_fraction_of_rated"] = (
            initial / NASA_PCOE_RATED_CAPACITY_AH
        )
    protocol.to_csv(path, index=False, lineterminator="\n")
    return path, protocol


def _rewrite_provenance(output: Path) -> Path:
    path = output / "nasa_pcoe_raw_signal_provenance.json"
    provenance = json.loads(path.read_text(encoding="utf-8"))
    unit_declarations = provenance.setdefault("unit_declarations", {})
    unit_declarations.update(
        {
            "discharge_capacity_ah": "Ah",
            "reference_capacity_ah": "Ah",
            "capacity_retention_percent": "% of documented 2 Ah rated capacity",
        }
    )
    transformation = provenance.setdefault("transformation", {})
    transformation.update(
        {
            "capacity_retention_reference_method": (
                NASA_PCOE_REFERENCE_CAPACITY_METHOD
            ),
            "source_rated_capacity_ah": NASA_PCOE_RATED_CAPACITY_AH,
            "source_rated_capacity_evidence": NASA_PCOE_RATED_CAPACITY_EVIDENCE,
            "first_observed_capacity_used_as_reference": False,
            "capacity_retention_derivation": (
                "100 * source scalar discharge Capacity / documented 2 Ah rated "
                "capacity. Source Capacity is preserved without clipping, "
                "smoothing, interpolation, or replacement."
            ),
            "protocol_dependence_warning": (
                "Discharge Capacity depends on current, ambient temperature, and "
                "voltage cutoff. A common 2 Ah denominator improves target semantics "
                "but does not establish cross-protocol comparability."
            ),
        }
    )
    path.write_text(canonical_json(provenance), encoding="utf-8")
    return path


def _rewrite_manifest(
    output: Path,
    manifest: dict[str, Any],
    *,
    cycle_path: Path,
    protocol_path: Path,
    provenance_path: Path,
) -> dict[str, Any]:
    manifest["target_reference"] = {
        "method": NASA_PCOE_REFERENCE_CAPACITY_METHOD,
        "rated_capacity_ah": NASA_PCOE_RATED_CAPACITY_AH,
        "evidence": NASA_PCOE_RATED_CAPACITY_EVIDENCE,
        "first_observed_capacity_used_as_reference": False,
        "source_capacity_values_preserved": True,
    }
    manifest.setdefault("outputs", {})["cycle_summary"] = str(cycle_path)
    manifest["outputs"]["protocol_summary"] = str(protocol_path)
    manifest["outputs"]["raw_signal_provenance"] = str(provenance_path)
    checksums = manifest.setdefault("output_sha256", {})
    checksums["cycle_summary"] = file_sha256(cycle_path)
    checksums["protocol_summary"] = file_sha256(protocol_path)
    checksums["raw_signal_provenance"] = file_sha256(provenance_path)
    limitation = (
        " Capacity retention uses the documented 2 Ah rated capacity rather than "
        "the first observed discharge. Current, temperature, and cutoff-voltage "
        "differences still require protocol-aware interpretation."
    )
    if limitation.strip() not in str(manifest.get("scientific_boundary", "")):
        manifest["scientific_boundary"] = (
            str(manifest.get("scientific_boundary", "")).rstrip() + limitation
        ).strip()
    manifest_path = output / "nasa_pcoe_import_manifest.json"
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
    return manifest


def _apply_source_rated_reference(
    output: Path, manifest: dict[str, Any]
) -> dict[str, Any]:
    cycle_path, cycle_summary = _rewrite_cycle_summary(output)
    protocol_path, _ = _rewrite_protocol_summary(output, cycle_summary)
    provenance_path = _rewrite_provenance(output)
    return _rewrite_manifest(
        output,
        manifest,
        cycle_path=cycle_path,
        protocol_path=protocol_path,
        provenance_path=provenance_path,
    )


def import_nasa_pcoe_battery(
    *,
    input_path: str | Path,
    output_dir: str | Path,
    retrieval_receipt_path: str | Path | None = None,
    retrieved_at: str | None = None,
    source_identifier: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Import NASA PCoE data and derive retention from documented 2 Ah rating."""
    manifest = _import_resilient(
        input_path=input_path,
        output_dir=output_dir,
        retrieval_receipt_path=retrieval_receipt_path,
        retrieved_at=retrieved_at,
        source_identifier=source_identifier,
        overwrite=overwrite,
    )
    return _apply_source_rated_reference(Path(output_dir), manifest)
