"""Run the NIST AM-Bench 2018-02 process-to-characterization case study."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from loaders.characterization_features import run_characterization_handoff  # noqa: E402
from loaders.nist_ambench_single_track import (  # noqa: E402
    build_case_summary,
    build_characterization_feature_table,
    build_process_table,
    load_source_contract,
    load_trace_measurements,
    sha256_file,
)

DEFAULT_TABLE = (
    PROJECT_ROOT
    / "data"
    / "case_studies"
    / "nist_ambench_2018_single_track"
    / "trace_measurements.csv"
)
DEFAULT_CONTRACT = (
    PROJECT_ROOT
    / "data"
    / "case_studies"
    / "nist_ambench_2018_single_track"
    / "source_contract.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a bounded real-data process-to-characterization case study "
            "from the official NIST AM-Bench 2018-02 reported table."
        )
    )
    parser.add_argument("--source-table", default=str(DEFAULT_TABLE))
    parser.add_argument("--source-contract", default=str(DEFAULT_CONTRACT))
    parser.add_argument(
        "--output",
        default="outputs/nist_ambench_2018_single_track",
    )
    return parser.parse_args()


def run_case_study(
    source_table_path: str | Path,
    source_contract_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Build validated tables, handoff artifacts, plots, report, and manifest."""
    source_table_path = Path(source_table_path)
    source_contract_path = Path(source_contract_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    contract = load_source_contract(source_contract_path)
    table_sha_before = sha256_file(source_table_path)
    contract_sha_before = sha256_file(source_contract_path)
    measurements = load_trace_measurements(source_table_path, contract)
    process = build_process_table(measurements, contract)
    features = build_characterization_feature_table(measurements, contract)
    summary = build_case_summary(measurements, contract)
    if sha256_file(source_table_path) != table_sha_before:
        raise ValueError("NIST AM-Bench source table changed during execution.")
    if sha256_file(source_contract_path) != contract_sha_before:
        raise ValueError("NIST AM-Bench source contract changed during execution.")

    paths = {
        "validated_source_table": output_dir / "validated_trace_measurements.csv",
        "process_table": output_dir / "process_conditions.csv",
        "characterization_features": output_dir
        / "characterization_features_long.csv",
        "case_summary": output_dir / "case_summary.csv",
        "width_plot": output_dir / "melt_pool_width_vs_linear_energy.png",
        "depth_plot": output_dir / "melt_pool_depth_vs_linear_energy.png",
        "report": output_dir / "case_study_report.md",
        "manifest": output_dir / "case_study_manifest.json",
    }
    measurements.to_csv(paths["validated_source_table"], index=False)
    process.to_csv(paths["process_table"], index=False)
    features.to_csv(paths["characterization_features"], index=False)
    summary.to_csv(paths["case_summary"], index=False)
    _plot_dimension(
        process,
        measurements,
        value_column="melt_pool_width_mean_um",
        ylabel="Melt-pool width (um)",
        output_path=paths["width_plot"],
    )
    _plot_dimension(
        process,
        measurements,
        value_column="melt_pool_depth_mean_um",
        ylabel="Melt-pool depth (um)",
        output_path=paths["depth_plot"],
    )

    handoff_dir = output_dir / "handoff"
    handoff_paths = run_characterization_handoff(
        [paths["characterization_features"]],
        handoff_dir,
        process_table_path=paths["process_table"],
    )
    join_audit = pd.read_csv(handoff_paths["join_audit"])
    if not join_audit["join_status"].eq("matched").all() or len(join_audit) != 10:
        raise ValueError("All ten NIST traces must match through explicit sample_id.")

    paths["report"].write_text(
        _build_report(contract, measurements, summary, handoff_paths),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "1.0",
        "case_study_id": contract["case_study_id"],
        "source": contract["source"],
        "provenance_status": contract["provenance_status"],
        "source_artifacts": {
            "trace_table": {
                "path": str(source_table_path),
                "sha256": table_sha_before,
                "row_count": int(len(measurements)),
            },
            "source_contract": {
                "path": str(source_contract_path),
                "sha256": contract_sha_before,
            },
        },
        "counts": {
            "trace_count": int(len(measurements)),
            "case_count": int(measurements["case_id"].nunique()),
            "unique_process_setting_count": int(
                process[
                    [
                        "calibrated_laser_power_w",
                        "scan_speed_mm_s",
                        "corrected_spot_size_fwhm_um",
                    ]
                ]
                .drop_duplicates()
                .shape[0]
            ),
            "characterization_feature_record_count": int(len(features)),
            "matched_sample_count": int(
                join_audit["join_status"].eq("matched").sum()
            ),
        },
        "metadata_corrections": {
            "legacy_spot_size_fwhm_um": contract["experiment"][
                "legacy_reported_spot_size_fwhm_um"
            ],
            "corrected_spot_size_fwhm_um": contract["experiment"][
                "corrected_spot_size_fwhm_um"
            ],
            "corrected_value_used_for_process_table": True,
            "note": contract["experiment"]["spot_size_correction_note"],
        },
        "outputs": {
            name: str(path)
            for name, path in {
                **paths,
                **{
                    f"handoff_{key}": value
                    for key, value in handoff_paths.items()
                },
            }.items()
            if name != "manifest"
        },
        "software_validation": {
            "status": "supported",
            "official_row_count_reproduced": True,
            "official_rounded_case_statistics_reproduced": True,
            "all_samples_matched_by_explicit_sample_id": True,
        },
        "scientific_closeout": {
            "status": "diagnostic",
            "strongest_evidence": (
                "The official NIST process settings and reported optical "
                "cross-section measurements are linked for ten trace identifiers."
            ),
            "primary_limitation": (
                "Only three unique process settings and ten traces are available; "
                "the tracked table is a transcription of reported results rather "
                "than an independent raw-image remeasurement."
            ),
            "suitable_for": [
                "end-to-end process-to-characterization integration demonstration",
                "descriptive comparison of the three NIST settings",
            ],
            "unsuitable_for": [
                "causal optimization",
                "predictive model validation",
                "generalization beyond the reported IN625 AMMT traces",
            ],
        },
        "model_training_performed": False,
        "metric_optimization_performed": False,
        "raw_image_reanalysis_performed": False,
    }
    paths["manifest"].write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        **paths,
        **{f"handoff_{key}": value for key, value in handoff_paths.items()},
    }


def _plot_dimension(
    process: pd.DataFrame,
    measurements: pd.DataFrame,
    *,
    value_column: str,
    ylabel: str,
    output_path: Path,
) -> None:
    plot_table = process[["sample_id", "case_id", "linear_energy_j_mm"]].merge(
        measurements[["sample_id", value_column]],
        on="sample_id",
        validate="one_to_one",
    )
    fig, axis = plt.subplots(figsize=(7.0, 4.8))
    for case_id, group in plot_table.groupby("case_id", sort=True):
        axis.scatter(
            group["linear_energy_j_mm"],
            group[value_column],
            label=f"Case {case_id}",
        )
    axis.set_xlabel("Calibrated linear energy (J/mm)")
    axis.set_ylabel(ylabel)
    axis.set_title("NIST AM-Bench 2018-02 reported cross-section measurements")
    axis.grid(alpha=0.25)
    axis.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def _build_report(
    contract: dict[str, object],
    measurements: pd.DataFrame,
    summary: pd.DataFrame,
    handoff_paths: dict[str, Path],
) -> str:
    rows = [
        "# NIST AM-Bench 2018-02 Single-Track Case Study",
        "",
        "## Result",
        "",
        "**Scientific closeout: Diagnostic.**",
        "",
        (
            "This case study links official NIST AMMT process settings to "
            "reported optical-microscopy melt-pool width and depth measurements "
            "through explicit trace-level `sample_id` values."
        ),
        "",
        "## Source and provenance",
        "",
        f"- Measurement page: {contract['source']['measurement_results_url']}",
        f"- Experiment description: {contract['source']['experiment_description_url']}",
        f"- Data record DOI: {contract['source']['data_record_doi']}",
        f"- Tracked rows: {len(measurements)}",
        (
            "- Provenance status: manual transcription from the official NIST "
            "result table; not a raw instrument export."
        ),
        (
            "- Metadata correction: the legacy results table reports a 45 um "
            "spot-size FWHM, while the current NIST description corrects the "
            "AMMT value to 100 um. Both are preserved and the corrected value "
            "is used."
        ),
        "",
        "## Case-level descriptive reproduction",
        "",
        _summary_markdown(summary),
        "",
        "## Handoff",
        "",
        f"- Integrated table: `{handoff_paths['integrated_table']}`",
        f"- Join audit: `{handoff_paths['join_audit']}`",
        "- All ten traces are matched through explicit identifiers.",
        (
            "- No row-order join, duplicate aggregation, model fitting, or "
            "metric tuning is used."
        ),
        "",
        "## Scientific limitations",
        "",
        "- There are only three unique process settings and ten trace measurements.",
        "- Replicate traces do not provide independent coverage of the process space.",
        "- Melt-pool dimensions are reported NIST measurements; raw images were not remeasured.",
        "- Linear energy is descriptive and is not a complete physical process model.",
        "- The result does not establish causality, optimization validity, or external generalization.",
        "",
    ]
    return "\n".join(rows)


def _summary_markdown(summary: pd.DataFrame) -> str:
    columns = [
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
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = []
    for record in summary[columns].itertuples(index=False, name=None):
        cells = []
        for value in record:
            if isinstance(value, float):
                cells.append(f"{value:.4f}")
            else:
                cells.append(str(value))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, divider, *rows])


def main() -> None:
    args = parse_args()
    try:
        paths = run_case_study(
            args.source_table,
            args.source_contract,
            args.output,
        )
    except (FileNotFoundError, ValueError, pd.errors.EmptyDataError) as exc:
        print(f"NIST AM-Bench case study failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print("NIST AM-Bench single-track case study completed.")
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
