"""Build, verify, and close out the NIST AM-Bench 2018-02 case study."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SRC_DIR = PROJECT_ROOT / "src"
for directory in (SCRIPTS_DIR, SRC_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from build_nist_ambench_2018_02_case_study import (  # noqa: E402
    DESCRIPTION_URL,
    DATASET_DOI,
    PUBLICATION_DOI,
    RESULTS_URL,
    run_case_study,
)
from loaders.characterization_features import sha256_file  # noqa: E402
from verify_nist_ambench_2018_02_case_study import verify_case_study  # noqa: E402

CASE_MANIFEST_NAME = "ambench_case_study_manifest.json"
HANDOFF_MANIFEST_NAME = "characterization_handoff_manifest.json"
SUMMARY_NAME = "ambench_integrated_summary.json"
REPORT_NAME = "ambench_integrated_report.md"
WORKFLOW_MANIFEST_NAME = "ambench_integrated_workflow_manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the complete NIST AM-Bench 2018-02 process-characterization "
            "workflow: build, integrity verification, and integrated closeout."
        )
    )
    parser.add_argument(
        "--output",
        required=True,
        help="New or empty output directory for the complete workflow.",
    )
    return parser.parse_args()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object.")
    return value


def _prepare_output_dir(output_dir: Path) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(
            "Integrated workflow output directory must be new or empty: "
            f"{output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)


def _case_rows(summary: pd.DataFrame) -> list[dict[str, Any]]:
    expected_columns = [
        "case_id",
        "n_traces",
        "actual_laser_power_w",
        "scan_speed_mm_s",
        "linear_energy_density_j_mm",
        "melt_pool_width_mean_um",
        "melt_pool_width_between_trace_std_um",
        "melt_pool_depth_mean_um",
        "melt_pool_depth_between_trace_std_um",
    ]
    if summary.columns.tolist() != expected_columns:
        raise ValueError(
            "NIST AM-Bench case summary schema changed; integrated reporting "
            "requires an explicit compatibility update."
        )
    if summary["case_id"].tolist() != ["A", "B", "C"]:
        raise ValueError("NIST AM-Bench case summary must contain cases A, B, and C.")

    rows: list[dict[str, Any]] = []
    for row in summary.itertuples(index=False):
        rows.append(
            {
                "case_id": str(row.case_id),
                "n_traces": int(row.n_traces),
                "actual_laser_power_w": round(float(row.actual_laser_power_w), 6),
                "scan_speed_mm_s": round(float(row.scan_speed_mm_s), 6),
                "linear_energy_density_j_mm": round(
                    float(row.linear_energy_density_j_mm), 6
                ),
                "melt_pool_width_mean_um": round(
                    float(row.melt_pool_width_mean_um), 6
                ),
                "melt_pool_width_between_trace_std_um": round(
                    float(row.melt_pool_width_between_trace_std_um), 6
                ),
                "melt_pool_depth_mean_um": round(
                    float(row.melt_pool_depth_mean_um), 6
                ),
                "melt_pool_depth_between_trace_std_um": round(
                    float(row.melt_pool_depth_between_trace_std_um), 6
                ),
            }
        )
    return rows


def build_integrated_summary(
    case_manifest: dict[str, Any],
    verification: dict[str, Any],
    case_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    source = case_manifest.get("source")
    closeout = case_manifest.get("scientific_closeout")
    validation = case_manifest.get("validation")
    if not isinstance(source, dict):
        raise ValueError("Case manifest source must be an object.")
    if not isinstance(closeout, dict):
        raise ValueError("Case manifest scientific_closeout must be an object.")
    if not isinstance(validation, dict):
        raise ValueError("Case manifest validation must be an object.")

    return {
        "schema_version": "1.0",
        "workflow": "nist_ambench_2018_02_integrated_process_characterization",
        "case_study_id": case_manifest.get("case_study_id"),
        "result": {
            "scientific_status": closeout.get("status"),
            "integrity_status": verification.get("status"),
            "interpretation": (
                "Within the three source-defined AMMT conditions, higher line "
                "energy coincides with larger mean melt-pool width and depth. "
                "This is descriptive and does not isolate a causal process variable."
            ),
        },
        "source": {
            "organization": source.get("organization"),
            "results_url": source.get("results_url"),
            "description_url": source.get("description_url"),
            "dataset_doi": source.get("dataset_doi"),
            "dataset_version_recorded": source.get("dataset_version_recorded"),
            "publication_doi": source.get("publication_doi"),
            "process_source_sha256": source.get("process_source_sha256"),
            "measurement_source_sha256": source.get("measurement_source_sha256"),
            "network_access_performed": source.get("network_access_performed"),
            "raw_images_redistributed": source.get("raw_images_redistributed"),
        },
        "software_validation": {
            "integrity_verification": verification,
            "source_schema_verified": validation.get("source_schema_verified"),
            "source_identity_mapping_verified": validation.get(
                "source_identity_mapping_verified"
            ),
            "official_rounded_class_summary_reproduced": validation.get(
                "official_rounded_class_summary_reproduced"
            ),
            "row_order_join_used": validation.get("row_order_join_used"),
            "model_trained": validation.get("model_trained"),
            "optimization_performed": validation.get("optimization_performed"),
        },
        "case_summary": case_rows,
        "scientific_closeout": {
            **closeout,
            "evidence_that_would_change_the_conclusion": (
                "A larger independently admissible cohort with comparable specimen "
                "identity, additional decoupled process conditions, uncertainty "
                "treatment, and held-out machine or material validation."
            ),
            "decision_use": {
                "exploration": True,
                "portfolio_demonstration": True,
                "engineering_decision": False,
                "causal_scientific_claim": False,
            },
        },
        "report_boundary": {
            "new_scientific_metrics_computed": False,
            "existing_case_summary_reformatted": True,
            "missing_metadata_inferred": False,
            "predictive_model_added": False,
        },
    }


def _summary_table(case_rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Case | n | Power (W) | Speed (mm/s) | Line energy (J/mm) | Width mean (µm) | Width between-trace SD (µm) | Depth mean (µm) | Depth between-trace SD (µm) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in case_rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["case_id"]),
                    str(row["n_traces"]),
                    f'{row["actual_laser_power_w"]:.1f}',
                    f'{row["scan_speed_mm_s"]:.0f}',
                    f'{row["linear_energy_density_j_mm"]:.6f}',
                    f'{row["melt_pool_width_mean_um"]:.3f}',
                    f'{row["melt_pool_width_between_trace_std_um"]:.3f}',
                    f'{row["melt_pool_depth_mean_um"]:.3f}',
                    f'{row["melt_pool_depth_between_trace_std_um"]:.3f}',
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def build_integrated_report(summary: dict[str, Any]) -> str:
    result = summary["result"]
    validation = summary["software_validation"]
    closeout = summary["scientific_closeout"]
    verification = validation["integrity_verification"]
    case_rows = summary["case_summary"]

    suitable_for = ", ".join(closeout.get("suitable_for", []))
    unsuitable_for = ", ".join(closeout.get("unsuitable_for", []))
    return f"""# NIST AM-Bench 2018-02 Integrated Process–Characterization Closeout

## Decision

- Scientific status: **{str(result['scientific_status']).title()}**
- Integrity status: **{str(result['integrity_status']).title()}**
- Matched samples: **{verification['matched_sample_count']} / 10**
- Model training performed: **No**
- Process optimization performed: **No**

{result['interpretation']}

## Evidence Chain

```text
tracked NIST process and measurement tables
-> source/schema and sample-identity validation
-> 40 provenance-bearing characterization feature records
-> explicit one-to-one sample_id handoff
-> 10 matched integrated trace rows
-> source-summary reproduction
-> artifact and manifest integrity verification
-> diagnostic scientific closeout
```

## Case Summary

{_summary_table(case_rows)}

The line-energy value is actual laser power divided by scan speed. It is not
volumetric energy density and does not isolate power or speed as an independent
causal variable.

## Software Validation

- all recorded case artifacts passed their stored SHA-256 checks;
- every feature record remained bound to the tracked NIST measurement table;
- the handoff manifest remained bound to the generated process and feature inputs;
- all ten process and characterization records joined through explicit
  `sample_id` values;
- no row-order join, silent feature aggregation, model training, or optimization
  was performed.

## Scientific Validation

**Evidence level:** {str(closeout['status']).title()}.

**Strongest evidence:** {closeout['strongest_evidence']}

**Primary limitation:** {closeout['primary_limitation']}

**Evidence that would change the conclusion:**
{closeout['evidence_that_would_change_the_conclusion']}

**Suitable for:** {suitable_for}.

**Not suitable for:** {unsuitable_for}.

## Main Artifacts

- `integrated_sample_table.csv`: one row per NIST trace after the explicit handoff;
- `sample_join_audit.csv`: matched/process-only/characterization-only audit;
- `ambench_case_summary.csv`: three source-defined process-condition summaries;
- `melt_pool_width_by_linear_energy.png` and
  `melt_pool_depth_by_linear_energy.png`: descriptive figures;
- `ambench_case_study_manifest.json`: source, validation, closeout, and artifact
  checksums;
- `characterization_handoff_manifest.json`: feature and process handoff lineage;
- `{SUMMARY_NAME}`: machine-readable integrated closeout;
- `{WORKFLOW_MANIFEST_NAME}`: complete workflow artifact inventory and checksums.

## Source and Attribution

- Results: {RESULTS_URL}
- Description: {DESCRIPTION_URL}
- Dataset DOI: {DATASET_DOI}
- Associated publication: {PUBLICATION_DOI}

This project is not endorsed or certified by NIST. The report reformats verified
existing results; it does not perform new scientific metric computation or create
new predictive evidence.
"""


def run_integrated_workflow(output_dir: str | Path) -> dict[str, Path]:
    """Build, verify, and write one integrated closeout package."""
    output_dir = Path(output_dir)
    _prepare_output_dir(output_dir)

    case_outputs = run_case_study(output_dir)
    verification = verify_case_study(output_dir)
    case_manifest = _read_json(
        output_dir / CASE_MANIFEST_NAME,
        "NIST AM-Bench case manifest",
    )
    case_summary = pd.read_csv(case_outputs["case_summary"])
    case_rows = _case_rows(case_summary)
    integrated_summary = build_integrated_summary(
        case_manifest,
        verification,
        case_rows,
    )

    summary_path = output_dir / SUMMARY_NAME
    report_path = output_dir / REPORT_NAME
    workflow_manifest_path = output_dir / WORKFLOW_MANIFEST_NAME
    summary_path.write_text(
        json.dumps(integrated_summary, indent=2, ensure_ascii=False, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        build_integrated_report(integrated_summary),
        encoding="utf-8",
    )

    artifact_checksums = {
        path.name: sha256_file(path)
        for path in sorted(output_dir.iterdir(), key=lambda item: item.name)
        if path.is_file() and path.name != WORKFLOW_MANIFEST_NAME
    }
    workflow_manifest = {
        "schema_version": "1.0",
        "workflow": "nist_ambench_2018_02_integrated_process_characterization",
        "generation_status": "completed",
        "integrity_verification": verification,
        "scientific_status": integrated_summary["result"]["scientific_status"],
        "network_access_performed": False,
        "model_trained": False,
        "optimization_performed": False,
        "artifact_checksums": artifact_checksums,
        "generated_files": sorted(artifact_checksums),
    }
    workflow_manifest_path.write_text(
        json.dumps(workflow_manifest, indent=2, ensure_ascii=False, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )

    return {
        **case_outputs,
        "integrated_summary": summary_path,
        "integrated_report": report_path,
        "integrated_workflow_manifest": workflow_manifest_path,
    }


def main() -> None:
    args = parse_args()
    try:
        outputs = run_integrated_workflow(args.output)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        pd.errors.EmptyDataError,
    ) as exc:
        print(f"NIST AM-Bench integrated workflow failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print("NIST AM-Bench 2018-02 integrated workflow completed.")
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
