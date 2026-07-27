"""NIST AM-Bench 2018-02 single-track process/characterization loader."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

REQUIRED_COLUMNS = [
    "sample_id",
    "case_id",
    "trace_number",
    "material",
    "machine",
    "commanded_laser_power_w",
    "calibrated_laser_power_w",
    "scan_speed_mm_s",
    "legacy_reported_spot_size_fwhm_um",
    "corrected_spot_size_fwhm_um",
    "melt_pool_width_mean_um",
    "melt_pool_width_std_dev_um",
    "melt_pool_depth_mean_um",
    "melt_pool_depth_std_dev_um",
]
NUMERIC_COLUMNS = REQUIRED_COLUMNS[5:]
FEATURE_COLUMNS = [
    ("melt_pool_width_mean", "melt_pool_width_mean_um", "um"),
    ("melt_pool_width_std_dev", "melt_pool_width_std_dev_um", "um"),
    ("melt_pool_depth_mean", "melt_pool_depth_mean_um", "um"),
    ("melt_pool_depth_std_dev", "melt_pool_depth_std_dev_um", "um"),
]


def sha256_file(path: str | Path) -> str:
    """Return a streaming SHA-256 digest."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_source_contract(path: str | Path) -> dict[str, Any]:
    """Load and minimally validate the tracked source contract."""
    with Path(path).open(encoding="utf-8") as handle:
        contract = json.load(handle)
    required = {
        "schema_version",
        "case_study_id",
        "provenance_status",
        "source",
        "tracked_source_table",
        "experiment",
        "cases",
        "scientific_boundary",
    }
    missing = sorted(required - set(contract))
    if missing:
        raise ValueError(
            "NIST AM-Bench source contract is missing field(s): "
            + ", ".join(missing)
        )
    if set(contract["cases"]) != {"A", "B", "C"}:
        raise ValueError("NIST AM-Bench source contract must define cases A, B, and C.")
    digest = str(contract["tracked_source_table"].get("sha256", ""))
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest.lower()
    ):
        raise ValueError("tracked_source_table.sha256 must be a SHA-256 digest.")
    return contract


def load_trace_measurements(
    table_path: str | Path,
    contract: dict[str, Any],
) -> pd.DataFrame:
    """Load, hash-check, and validate the manually transcribed official table."""
    table_path = Path(table_path)
    if not table_path.is_file():
        raise FileNotFoundError(f"NIST AM-Bench trace table not found: {table_path}")
    expected_sha = contract["tracked_source_table"]["sha256"]
    actual_sha = sha256_file(table_path)
    if actual_sha != expected_sha:
        raise ValueError(
            "NIST AM-Bench trace table SHA-256 does not match the source contract."
        )
    table = pd.read_csv(table_path)
    return validate_trace_measurements(table, contract)


def validate_trace_measurements(
    table: pd.DataFrame,
    contract: dict[str, Any],
) -> pd.DataFrame:
    """Validate identifiers, units encoded by schema, and official case settings."""
    missing = [column for column in REQUIRED_COLUMNS if column not in table.columns]
    if missing:
        raise ValueError(
            "NIST AM-Bench trace table is missing required column(s): "
            + ", ".join(missing)
        )
    normalized = table.loc[:, REQUIRED_COLUMNS].copy()
    for column in ("sample_id", "case_id", "material", "machine"):
        normalized[column] = normalized[column].map(_clean_text)
        if normalized[column].isna().any():
            raise ValueError(f"NIST AM-Bench trace table contains blank {column}.")
    for column in NUMERIC_COLUMNS:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
        if normalized[column].isna().any() or not normalized[column].map(
            lambda value: math.isfinite(float(value))
        ).all():
            raise ValueError(f"NIST AM-Bench trace table contains invalid {column}.")
    normalized["trace_number"] = pd.to_numeric(
        normalized["trace_number"], errors="coerce"
    )
    if normalized["trace_number"].isna().any() or not normalized[
        "trace_number"
    ].map(lambda value: float(value).is_integer()).all():
        raise ValueError("NIST AM-Bench trace_number values must be finite integers.")
    normalized["trace_number"] = normalized["trace_number"].astype(int)

    expected_row_count = int(contract["tracked_source_table"]["row_count"])
    if len(normalized) != expected_row_count:
        raise ValueError(
            f"NIST AM-Bench trace table must contain {expected_row_count} rows."
        )
    if normalized["sample_id"].duplicated().any():
        raise ValueError("NIST AM-Bench sample_id values must be unique.")
    if normalized["trace_number"].duplicated().any():
        raise ValueError("NIST AM-Bench trace_number values must be unique.")

    expected_traces = list(contract["experiment"]["trace_numbers"])
    if sorted(normalized["trace_number"].tolist()) != expected_traces:
        raise ValueError("NIST AM-Bench trace numbers do not match the source contract.")
    expected_sample_ids = {
        trace: f"amb2018_02_trace_{trace:02d}" for trace in expected_traces
    }
    actual_sample_ids = dict(
        normalized[["trace_number", "sample_id"]].itertuples(index=False, name=None)
    )
    if actual_sample_ids != expected_sample_ids:
        raise ValueError(
            "NIST AM-Bench sample_id values must map exactly to trace numbers."
        )

    experiment = contract["experiment"]
    if set(normalized["material"]) != {experiment["material"]}:
        raise ValueError("NIST AM-Bench material does not match the source contract.")
    if set(normalized["machine"]) != {experiment["machine"]}:
        raise ValueError("NIST AM-Bench machine does not match the source contract.")

    for case_id, definition in contract["cases"].items():
        case_rows = normalized.loc[normalized["case_id"].eq(case_id)]
        if sorted(case_rows["trace_number"].tolist()) != definition["trace_numbers"]:
            raise ValueError(
                f"Case {case_id} trace membership does not match the source contract."
            )
        for column in (
            "commanded_laser_power_w",
            "calibrated_laser_power_w",
            "scan_speed_mm_s",
        ):
            if not _all_close(case_rows[column], float(definition[column])):
                raise ValueError(f"Case {case_id} has inconsistent {column} values.")

    legacy_spot = float(experiment["legacy_reported_spot_size_fwhm_um"])
    corrected_spot = float(experiment["corrected_spot_size_fwhm_um"])
    if not _all_close(
        normalized["legacy_reported_spot_size_fwhm_um"], legacy_spot
    ):
        raise ValueError("Legacy spot-size values do not match the source contract.")
    if not _all_close(normalized["corrected_spot_size_fwhm_um"], corrected_spot):
        raise ValueError("Corrected spot-size values do not match the source contract.")

    measurement_columns = [column for _, column, _ in FEATURE_COLUMNS]
    if (normalized[measurement_columns] < 0).any().any():
        raise ValueError(
            "NIST AM-Bench reported dimensions and deviations must be non-negative."
        )
    return normalized.sort_values("trace_number").reset_index(drop=True)


def build_process_table(table: pd.DataFrame, contract: dict[str, Any]) -> pd.DataFrame:
    """Build one process row per trace using corrected NIST metadata."""
    validated = validate_trace_measurements(table, contract)
    process = validated[
        [
            "sample_id",
            "case_id",
            "trace_number",
            "material",
            "machine",
            "commanded_laser_power_w",
            "calibrated_laser_power_w",
            "scan_speed_mm_s",
            "corrected_spot_size_fwhm_um",
        ]
    ].copy()
    process["linear_energy_j_mm"] = (
        process["calibrated_laser_power_w"] / process["scan_speed_mm_s"]
    )
    process["spot_size_metadata_status"] = "corrected_nist_value_used"
    return process


def build_characterization_feature_table(
    table: pd.DataFrame,
    contract: dict[str, Any],
) -> pd.DataFrame:
    """Convert reported optical measurements to the stable handoff contract."""
    validated = validate_trace_measurements(table, contract)
    source_url = contract["source"]["measurement_results_url"]
    method = contract["experiment"]["measurement_method"]
    records: list[dict[str, Any]] = []
    for row in validated.itertuples(index=False):
        for feature_name, source_column, unit in FEATURE_COLUMNS:
            records.append(
                {
                    "sample_id": row.sample_id,
                    "measurement_id": f"{row.sample_id}-optical-cross-section",
                    "instrument": "optical_microscopy",
                    "feature_name": feature_name,
                    "feature_label": None,
                    "value": float(getattr(row, source_column)),
                    "unit": unit,
                    "method": method,
                    "source_file": source_url,
                    "source_sha256": None,
                    "preprocessing_id": "nist_amb2018_02_reported_table_v1",
                    "quality_flag": "official_reported_measurement",
                }
            )
    return pd.DataFrame(records)


def build_case_summary(table: pd.DataFrame, contract: dict[str, Any]) -> pd.DataFrame:
    """Reproduce case-level descriptive statistics from the ten trace rows."""
    validated = validate_trace_measurements(table, contract)
    summary = (
        validated.groupby("case_id", sort=True)
        .agg(
            trace_count=("trace_number", "count"),
            calibrated_laser_power_w=("calibrated_laser_power_w", "first"),
            scan_speed_mm_s=("scan_speed_mm_s", "first"),
            width_mean_um=("melt_pool_width_mean_um", "mean"),
            width_between_trace_std_dev_um=("melt_pool_width_mean_um", "std"),
            depth_mean_um=("melt_pool_depth_mean_um", "mean"),
            depth_between_trace_std_dev_um=("melt_pool_depth_mean_um", "std"),
        )
        .reset_index()
    )
    summary["linear_energy_j_mm"] = (
        summary["calibrated_laser_power_w"] / summary["scan_speed_mm_s"]
    )
    validate_case_summary_against_contract(summary, contract)
    return summary[
        [
            "case_id",
            "trace_count",
            "calibrated_laser_power_w",
            "scan_speed_mm_s",
            "linear_energy_j_mm",
            "width_mean_um",
            "width_between_trace_std_dev_um",
            "depth_mean_um",
            "depth_between_trace_std_dev_um",
        ]
    ]


def validate_case_summary_against_contract(
    summary: pd.DataFrame,
    contract: dict[str, Any],
) -> None:
    """Check recomputed rounded case statistics against the official table."""
    indexed = summary.set_index("case_id")
    comparisons = {
        "width_mean_um": "reported_class_width_mean_um",
        "width_between_trace_std_dev_um": "reported_class_width_std_dev_um",
        "depth_mean_um": "reported_class_depth_mean_um",
        "depth_between_trace_std_dev_um": "reported_class_depth_std_dev_um",
    }
    for case_id, definition in contract["cases"].items():
        if case_id not in indexed.index:
            raise ValueError(f"Case summary is missing case {case_id}.")
        for calculated_column, contract_field in comparisons.items():
            calculated = round(float(indexed.loc[case_id, calculated_column]), 1)
            reported = round(float(definition[contract_field]), 1)
            if calculated != reported:
                raise ValueError(
                    f"Case {case_id} {calculated_column} does not reproduce "
                    "the official rounded value."
                )


def _all_close(
    series: pd.Series,
    expected: float,
    *,
    tolerance: float = 1e-9,
) -> bool:
    return bool(
        series.map(lambda value: abs(float(value) - expected) <= tolerance).all()
    )


def _clean_text(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None
