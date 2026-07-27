"""Build the NIST AM-Bench 2018-02 process-characterization case study."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from loaders.characterization_features import (  # noqa: E402
    run_characterization_handoff,
    sha256_file,
)

CASE_DIR = PROJECT_ROOT / "data" / "case_studies" / "nist_ambench_2018_02"
PROCESS_SOURCE = CASE_DIR / "source_process_conditions.csv"
MEASUREMENT_SOURCE = CASE_DIR / "source_melt_pool_measurements.csv"

RESULTS_URL = "https://www.nist.gov/ambench/chal-amb2018-02-mp-xsection"
DESCRIPTION_URL = "https://www.nist.gov/ambench/amb2018-02-description"
DATASET_DOI = "https://doi.org/10.18434/mds2-3830"
DATASET_VERSION = "1.0.3"
PUBLICATION_DOI = "https://doi.org/10.1007/s40192-020-00169-1"

PROCESS_COLUMNS = [
    "sample_id",
    "case_id",
    "trace_number",
    "actual_laser_power_w",
    "scan_speed_mm_s",
    "system",
    "material",
]
MEASUREMENT_COLUMNS = [
    "sample_id",
    "case_id",
    "trace_number",
    "melt_pool_width_mean_um",
    "melt_pool_width_std_dev_um",
    "melt_pool_depth_mean_um",
    "melt_pool_depth_std_dev_um",
]
EXPECTED_CASES = {
    "A": {"count": 3, "power": 137.9, "speed": 400.0},
    "B": {"count": 3, "power": 179.2, "speed": 800.0},
    "C": {"count": 4, "power": 179.2, "speed": 1200.0},
}
EXPECTED_ROUNDED_CLASS_SUMMARY = {
    "A": {"width_mean": 147.9, "width_std": 3.7, "depth_mean": 42.5, "depth_std": 1.7},
    "B": {"width_mean": 123.5, "width_std": 6.5, "depth_mean": 36.0, "depth_std": 1.9},
    "C": {"width_mean": 106.0, "width_std": 1.4, "depth_mean": 29.6, "depth_std": 0.6},
}
FEATURE_SPECS = [
    ("melt_pool_width_mean_um", "melt_pool_width_mean", "um"),
    ("melt_pool_width_std_dev_um", "melt_pool_width_std_dev", "um"),
    ("melt_pool_depth_mean_um", "melt_pool_depth_mean", "um"),
    ("melt_pool_depth_std_dev_um", "melt_pool_depth_std_dev", "um"),
]
WIDTH_KEY = "char__optical_microscopy_metrology__melt_pool_width_mean__um"
DEPTH_KEY = "char__optical_microscopy_metrology__melt_pool_depth_mean__um"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic NIST AM-Bench 2018-02 process-characterization "
            "case study from tracked source tables without network access."
        )
    )
    parser.add_argument("--output", required=True, help="Output directory.")
    return parser.parse_args()


def _validate_columns(table: pd.DataFrame, expected: list[str], name: str) -> None:
    missing = [column for column in expected if column not in table.columns]
    extra = [column for column in table.columns if column not in expected]
    if missing or extra:
        raise ValueError(
            f"{name} schema mismatch; missing={missing}, extra={extra}."
        )


def _validate_finite_numeric(
    table: pd.DataFrame,
    columns: list[str],
    name: str,
) -> None:
    for column in columns:
        numeric = pd.to_numeric(table[column], errors="coerce")
        if numeric.isna().any() or not numeric.map(
            lambda value: math.isfinite(float(value))
        ).all():
            raise ValueError(f"{name} contains invalid numeric values in {column}.")
        table[column] = numeric


def validate_source_tables(
    process: pd.DataFrame,
    measurements: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate source schema, identifiers, case mapping, and physical ranges."""
    process = process.copy()
    measurements = measurements.copy()
    _validate_columns(process, PROCESS_COLUMNS, "process source")
    _validate_columns(measurements, MEASUREMENT_COLUMNS, "measurement source")

    for table, name in ((process, "process source"), (measurements, "measurement source")):
        for column in ("sample_id", "case_id"):
            table[column] = table[column].astype("string").str.strip()
            if table[column].isna().any() or table[column].eq("").any():
                raise ValueError(f"{name} contains blank {column} values.")
        if table["sample_id"].duplicated().any():
            raise ValueError(f"{name} sample_id values must be unique.")

    _validate_finite_numeric(
        process,
        ["trace_number", "actual_laser_power_w", "scan_speed_mm_s"],
        "process source",
    )
    _validate_finite_numeric(
        measurements,
        [
            "trace_number",
            "melt_pool_width_mean_um",
            "melt_pool_width_std_dev_um",
            "melt_pool_depth_mean_um",
            "melt_pool_depth_std_dev_um",
        ],
        "measurement source",
    )
    process["trace_number"] = process["trace_number"].astype(int)
    measurements["trace_number"] = measurements["trace_number"].astype(int)

    expected_traces = list(range(1, 11))
    if sorted(process["trace_number"].tolist()) != expected_traces:
        raise ValueError("Process source must contain trace numbers 1 through 10 exactly once.")
    if sorted(measurements["trace_number"].tolist()) != expected_traces:
        raise ValueError("Measurement source must contain trace numbers 1 through 10 exactly once.")
    if set(process["sample_id"]) != set(measurements["sample_id"]):
        raise ValueError("Process and measurement sample_id sets must match exactly.")

    identity = process[["sample_id", "case_id", "trace_number"]].merge(
        measurements[["sample_id", "case_id", "trace_number"]],
        on="sample_id",
        how="outer",
        suffixes=("_process", "_measurement"),
        validate="one_to_one",
        indicator=True,
    )
    if not identity["_merge"].eq("both").all():
        raise ValueError("Process and measurement identities are not one-to-one.")
    if not identity["case_id_process"].eq(identity["case_id_measurement"]).all():
        raise ValueError("Case IDs differ between process and measurement sources.")
    if not identity["trace_number_process"].eq(identity["trace_number_measurement"]).all():
        raise ValueError("Trace numbers differ between process and measurement sources.")

    if set(process["case_id"]) != set(EXPECTED_CASES):
        raise ValueError("Process source must contain cases A, B, and C.")
    for case_id, expected in EXPECTED_CASES.items():
        group = process.loc[process["case_id"].eq(case_id)]
        if len(group) != expected["count"]:
            raise ValueError(f"Case {case_id} has the wrong replication count.")
        if group["actual_laser_power_w"].nunique() != 1 or not math.isclose(
            float(group["actual_laser_power_w"].iloc[0]), expected["power"]
        ):
            raise ValueError(f"Case {case_id} has an unexpected corrected laser power.")
        if group["scan_speed_mm_s"].nunique() != 1 or not math.isclose(
            float(group["scan_speed_mm_s"].iloc[0]), expected["speed"]
        ):
            raise ValueError(f"Case {case_id} has an unexpected scan speed.")

    if set(process["system"]) != {"AMMT"}:
        raise ValueError("This case study is restricted to the NIST AMMT system.")
    if set(process["material"]) != {"IN625"}:
        raise ValueError("This case study is restricted to IN625.")
    if (process["actual_laser_power_w"] <= 0).any() or (process["scan_speed_mm_s"] <= 0).any():
        raise ValueError("Power and scan speed must be positive.")

    mean_columns = ["melt_pool_width_mean_um", "melt_pool_depth_mean_um"]
    std_columns = ["melt_pool_width_std_dev_um", "melt_pool_depth_std_dev_um"]
    if (measurements[mean_columns] <= 0).any().any():
        raise ValueError("Melt-pool width and depth means must be positive.")
    if (measurements[std_columns] < 0).any().any():
        raise ValueError("Reported standard deviations must be non-negative.")

    return (
        process.sort_values("trace_number").reset_index(drop=True),
        measurements.sort_values("trace_number").reset_index(drop=True),
    )


def build_characterization_long(
    measurements: pd.DataFrame,
    source_sha256: str,
) -> pd.DataFrame:
    """Convert source-reported measurements to the stable feature contract."""
    records: list[dict[str, Any]] = []
    for row in measurements.itertuples(index=False):
        for source_column, feature_name, unit in FEATURE_SPECS:
            records.append(
                {
                    "sample_id": row.sample_id,
                    "measurement_id": f"{row.sample_id}_xsection",
                    "instrument": "optical_microscopy_metrology",
                    "feature_name": feature_name,
                    "feature_label": None,
                    "value": float(getattr(row, source_column)),
                    "unit": unit,
                    "method": "nist_microscope_control_metrology_mode_reported_table",
                    "source_file": MEASUREMENT_SOURCE.name,
                    "source_sha256": source_sha256,
                    "preprocessing_id": "nist_reported_table_values_v1",
                    "quality_flag": "source_reported",
                }
            )
    return pd.DataFrame(records)


def build_process_table(process: pd.DataFrame) -> pd.DataFrame:
    """Add one explicit, physically named line-energy descriptor."""
    output = process.copy()
    output["linear_energy_density_j_mm"] = (
        output["actual_laser_power_w"] / output["scan_speed_mm_s"]
    )
    return output


def build_case_summary(integrated: pd.DataFrame) -> pd.DataFrame:
    """Build process-case descriptive summaries without fitting a model."""
    required = {"case_id", "actual_laser_power_w", "scan_speed_mm_s", WIDTH_KEY, DEPTH_KEY}
    missing = sorted(required - set(integrated.columns))
    if missing:
        raise ValueError(f"Integrated table is missing required case-study columns: {missing}")

    summary = (
        integrated.groupby("case_id", sort=True)
        .agg(
            n_traces=("sample_id", "size"),
            actual_laser_power_w=("actual_laser_power_w", "first"),
            scan_speed_mm_s=("scan_speed_mm_s", "first"),
            linear_energy_density_j_mm=("linear_energy_density_j_mm", "first"),
            melt_pool_width_mean_um=(WIDTH_KEY, "mean"),
            melt_pool_width_between_trace_std_um=(WIDTH_KEY, "std"),
            melt_pool_depth_mean_um=(DEPTH_KEY, "mean"),
            melt_pool_depth_between_trace_std_um=(DEPTH_KEY, "std"),
        )
        .reset_index()
    )
    _validate_class_summary(summary)
    return summary


def _validate_class_summary(summary: pd.DataFrame) -> None:
    for row in summary.itertuples(index=False):
        expected = EXPECTED_ROUNDED_CLASS_SUMMARY[row.case_id]
        actual = {
            "width_mean": round(float(row.melt_pool_width_mean_um), 1),
            "width_std": round(float(row.melt_pool_width_between_trace_std_um), 1),
            "depth_mean": round(float(row.melt_pool_depth_mean_um), 1),
            "depth_std": round(float(row.melt_pool_depth_between_trace_std_um), 1),
        }
        if actual != expected:
            raise ValueError(
                f"Case {row.case_id} summary does not reproduce NIST Table 2: "
                f"actual={actual}, expected={expected}."
            )


def _plot_trace_response(
    integrated: pd.DataFrame,
    output_path: Path,
    response_column: str,
    ylabel: str,
    title: str,
) -> None:
    figure, axis = plt.subplots(figsize=(8, 5))
    for case_id, group in integrated.groupby("case_id", sort=True):
        axis.scatter(
            group["linear_energy_density_j_mm"],
            group[response_column],
            label=f"Case {case_id}",
        )
        for row in group.itertuples(index=False):
            axis.annotate(
                str(row.trace_number),
                (
                    row.linear_energy_density_j_mm,
                    getattr(row, response_column),
                ),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=8,
            )
    axis.set_xlabel("Actual laser power / scan speed (J/mm)")
    axis.set_ylabel(ylabel)
    axis.set_title(title)
    axis.legend()
    axis.grid(True, alpha=0.3)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def _summary_markdown(summary: pd.DataFrame) -> str:
    lines = [
        "| Case | n | Power (W) | Speed (mm/s) | Line energy (J/mm) | Width mean (µm) | Width between-trace SD (µm) | Depth mean (µm) | Depth between-trace SD (µm) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary.itertuples(index=False):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.case_id),
                    str(int(row.n_traces)),
                    f"{row.actual_laser_power_w:.1f}",
                    f"{row.scan_speed_mm_s:.0f}",
                    f"{row.linear_energy_density_j_mm:.6f}",
                    f"{row.melt_pool_width_mean_um:.3f}",
                    f"{row.melt_pool_width_between_trace_std_um:.3f}",
                    f"{row.melt_pool_depth_mean_um:.3f}",
                    f"{row.melt_pool_depth_between_trace_std_um:.3f}",
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def build_report(summary: pd.DataFrame) -> str:
    return f"""# NIST AM-Bench 2018-02 Process–Characterization Report

## Result

Scientific status: **Diagnostic**.

The workflow joined all ten NIST AMMT laser traces to their source-reported
optical-microscopy melt-pool measurements through explicit `sample_id` values.
The recomputed case-level means and between-trace standard deviations reproduce
NIST Table 2 after source-level rounding.

## Case Summary

{_summary_markdown(summary)}

## Interpretation

Within this small benchmark, the highest line-energy case A has the largest
mean melt-pool width and depth, case B is intermediate, and case C is lowest.
This is a descriptive observation across three predeclared process conditions,
not an independently identified causal law. Power and speed vary together, and
line energy omits spot size, absorptivity, thermal boundary conditions, and
other physical variables.

## Software Validation

- two tracked source tables were schema- and identity-validated;
- corrected AMMT actual power values were preserved;
- ten of ten samples joined one-to-one by `sample_id`;
- four source-reported characterization features were retained per trace;
- no row-order join, silent averaging, network access, model training, or metric
  optimization was performed;
- outputs are deterministic for the tracked inputs.

## Scientific Limitations

- only ten traces and three unique process conditions are available;
- measurements come from one material, machine, substrate preparation, and
  experimental context;
- the tracked source values are a transcription of the official NIST result
  table rather than a reanalysis of the optical image files;
- source-reported within-trace measurement statistics and between-trace process
  variability are distinct and are not combined into one uncertainty model;
- no external cohort or held-out process condition is available;
- no predictive, optimization, powder-bed, cross-machine, or cross-material
  claim is supported.

## Source

- Results: {RESULTS_URL}
- Description: {DESCRIPTION_URL}
- Dataset DOI: {DATASET_DOI}
- Associated publication: {PUBLICATION_DOI}

This project is not endorsed or certified by NIST.
"""


def run_case_study(output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    process_raw = pd.read_csv(PROCESS_SOURCE)
    measurements_raw = pd.read_csv(MEASUREMENT_SOURCE)
    process, measurements = validate_source_tables(process_raw, measurements_raw)

    process_sha = sha256_file(PROCESS_SOURCE)
    measurement_sha = sha256_file(MEASUREMENT_SOURCE)
    process_table = build_process_table(process)
    long_table = build_characterization_long(measurements, measurement_sha)

    process_output = output_dir / "ambench_process_conditions_normalized.csv"
    long_output = output_dir / "ambench_characterization_features_long.csv"
    process_table.to_csv(process_output, index=False)
    long_table.to_csv(long_output, index=False)

    handoff_paths = run_characterization_handoff(
        [long_output],
        output_dir,
        process_table_path=process_output,
    )
    integrated = pd.read_csv(handoff_paths["integrated_table"])
    audit = pd.read_csv(handoff_paths["join_audit"])
    if len(integrated) != 10 or not audit["join_status"].eq("matched").all():
        raise ValueError("All ten NIST traces must join as matched samples.")

    summary = build_case_summary(integrated)
    summary_path = output_dir / "ambench_case_summary.csv"
    summary.to_csv(summary_path, index=False)

    width_plot = output_dir / "melt_pool_width_by_linear_energy.png"
    depth_plot = output_dir / "melt_pool_depth_by_linear_energy.png"
    _plot_trace_response(
        integrated,
        width_plot,
        WIDTH_KEY,
        "Melt-pool width mean (µm)",
        "NIST AM-Bench 2018-02 Melt-Pool Width",
    )
    _plot_trace_response(
        integrated,
        depth_plot,
        DEPTH_KEY,
        "Melt-pool depth mean (µm)",
        "NIST AM-Bench 2018-02 Melt-Pool Depth",
    )

    report_path = output_dir / "ambench_case_study_report.md"
    report_path.write_text(build_report(summary), encoding="utf-8")

    outputs: dict[str, Path] = {
        "normalized_process_table": process_output,
        "characterization_long": long_output,
        **handoff_paths,
        "case_summary": summary_path,
        "width_plot": width_plot,
        "depth_plot": depth_plot,
        "report": report_path,
    }
    manifest_path = output_dir / "ambench_case_study_manifest.json"
    artifact_checksums = {
        name: sha256_file(path)
        for name, path in outputs.items()
        if name != "manifest"
    }
    manifest = {
        "schema_version": "1.0",
        "case_study_id": "nist_ambench_2018_02_process_characterization",
        "source": {
            "organization": "National Institute of Standards and Technology",
            "results_url": RESULTS_URL,
            "description_url": DESCRIPTION_URL,
            "dataset_doi": DATASET_DOI,
            "dataset_version_recorded": DATASET_VERSION,
            "publication_doi": PUBLICATION_DOI,
            "process_source_sha256": process_sha,
            "measurement_source_sha256": measurement_sha,
            "network_access_performed": False,
            "raw_images_redistributed": False,
        },
        "counts": {
            "trace_count": 10,
            "process_condition_count": 3,
            "characterization_record_count": int(len(long_table)),
            "matched_sample_count": int(audit["join_status"].eq("matched").sum()),
        },
        "derived_features": {
            "linear_energy_density_j_mm": {
                "formula": "actual_laser_power_w / scan_speed_mm_s",
                "role": "descriptive_line_energy_proxy",
                "not_volumetric_energy_density": True,
            }
        },
        "validation": {
            "source_schema_verified": True,
            "source_identity_mapping_verified": True,
            "corrected_actual_power_used": True,
            "official_rounded_class_summary_reproduced": True,
            "row_order_join_used": False,
            "model_trained": False,
            "optimization_performed": False,
        },
        "scientific_closeout": {
            "status": "diagnostic",
            "result": "source_reported_process_characterization_relationships_reproduced",
            "strongest_evidence": (
                "Ten trace-level process rows and optical-metrology width/depth "
                "rows join one-to-one and reproduce the official rounded class summary."
            ),
            "primary_limitation": (
                "Only ten traces and three coupled power-speed conditions from one "
                "AMMT IN625 experiment are available."
            ),
            "suitable_for": [
                "software handoff validation",
                "descriptive process-characterization comparison",
                "portfolio case-study demonstration",
            ],
            "unsuitable_for": [
                "predictive modeling",
                "process optimization",
                "causal attribution",
                "cross-machine or cross-material generalization",
                "production engineering decisions",
            ],
        },
        "artifact_checksums": artifact_checksums,
        "outputs": {name: str(path) for name, path in outputs.items()},
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    outputs["case_manifest"] = manifest_path
    return outputs


def main() -> None:
    args = parse_args()
    try:
        outputs = run_case_study(Path(args.output))
    except (FileNotFoundError, pd.errors.EmptyDataError, ValueError) as exc:
        print(f"NIST AM-Bench case study failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print("NIST AM-Bench 2018-02 case study completed.")
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
