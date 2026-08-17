"""Validate and structurally audit provenance-bound NIST AM-Bench Stage 1 trace augmentation."""
from __future__ import annotations

import argparse
import hashlib
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

from audit_nist_ambench_2018_02_process_design import run_audit  # noqa: E402
from build_nist_ambench_2018_02_case_study import run_case_study  # noqa: E402
from materials_data_analyzer.research_loop.nist_ambench_augmented_trace_intake import (  # noqa: E402
    combine_with_frozen_baseline,
    deterministic_json,
    structural_audit_input,
    validate_augmented_manifest,
)

BASELINE_DIR = "01_frozen_baseline"
INTAKE_DIR = "02_validated_stage1_intake"
AUDIT_DIR = "03_augmented_process_design_audit"
STAGE1_TABLE = "stage1_validated_joined_records.csv"
INTAKE_REPORT = "stage1_intake_validation.json"
AUGMENTED_TABLE = "augmented_integrated_table.csv"
STRUCTURAL_INPUT = "augmented_structural_audit_input.csv"
SUMMARY_FILE = "augmented_trace_workflow_summary.json"
REPORT_FILE = "augmented_trace_workflow_report.md"
MANIFEST_FILE = "augmented_trace_workflow_manifest.json"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_output(output: Path) -> None:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(
            f"Augmented workflow output directory must be new or empty: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def build_summary(
    *,
    intake_report: dict[str, Any],
    augmented: pd.DataFrame,
    structural: pd.DataFrame,
    audit: dict[str, Any],
) -> dict[str, Any]:
    interaction = audit["design_models"]["main_effects_plus_interaction"]
    return {
        "schema_version": "1.0",
        "workflow": "nist_ambench_2018_02_augmented_stage1_trace_workflow",
        "status": "completed",
        "evidence_level": "Diagnostic",
        "counts": {
            "frozen_baseline_trace_count": 10,
            "validated_stage1_record_count": int(
                intake_report["identity_validation"]["process_record_count"]
            ),
            "augmented_trace_count_including_preserved_failed_or_censored": int(
                len(augmented)
            ),
            "structural_audit_trace_count": int(len(structural)),
            "structural_audit_condition_count": int(audit["unique_condition_count"]),
        },
        "stage1": intake_report["stage1"],
        "structural_audit": {
            "full_factorial_coverage_fraction": float(
                audit["factor_support"]["factorial_coverage_fraction"]
            ),
            "interaction_matrix_rank": int(interaction["matrix_rank"]),
            "interaction_parameter_count": int(interaction["parameter_count"]),
            "interaction_structurally_estimable": bool(
                audit["structural_estimability"]["interaction_estimable"]
            ),
            "interaction_condition_level_residual_df": int(
                interaction["condition_level_residual_df"]
            ),
            "interaction_sample_level_residual_df": int(
                interaction["sample_level_residual_df"]
            ),
            "overall_readiness": audit["readiness"]["overall"],
        },
        "scientific_boundary": intake_report["scientific_boundary"],
        "software_validation": {
            **intake_report["software_validation"],
            "frozen_representative_workflow_mutated": False,
            "existing_process_design_audit_reused": True,
            "row_order_join_used": False,
            "physical_origin_promoted_from_self_declaration": False,
        },
        "relationship_to_issue_76": {
            "software_intake_gap_exercised": True,
            "issue_76_scientific_requirement_satisfied_by_this_workflow_alone": False,
            "reason": (
                "The workflow authenticates bytes, provenance fields, explicit identity "
                "joins, target-cell coverage, and structural estimability. It cannot "
                "independently prove that self-declared measured records originated from "
                "the required physical experiment."
            ),
        },
    }


def build_report(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    stage1 = summary["stage1"]
    audit = summary["structural_audit"]
    return f"""# NIST AM-Bench Stage 1 Augmented-Trace Intake

## Decision

**Evidence level: Diagnostic**

The augmented intake completed without promoting scientific status. The software
validated explicit provenance bindings and reran the existing structural
process-design audit; it did not fit a response model or authenticate physical
origin from self-declared metadata.

## Counts

- Frozen baseline traces: `{counts['frozen_baseline_trace_count']}`
- Validated Stage 1 records: `{counts['validated_stage1_record_count']}`
- Augmented rows, including preserved failed/censored records: `{counts['augmented_trace_count_including_preserved_failed_or_censored']}`
- Structurally eligible audit traces: `{counts['structural_audit_trace_count']}`
- Audited process conditions: `{counts['structural_audit_condition_count']}`

## Stage 1 Gate

- Three predeclared cells structurally complete: `{str(stage1['structural_trace_requirement_complete']).lower()}`
- Three cells complete with declared measured candidates: `{str(stage1['declared_measured_candidate_requirement_complete']).lower()}`
- Physical origin authenticated by software: `false`
- Scientific Stage 1 complete: `false`

## Structural Audit

- Full observed-level factorial coverage: `{audit['full_factorial_coverage_fraction']:.6f}`
- Interaction rank / parameters: `{audit['interaction_matrix_rank']} / {audit['interaction_parameter_count']}`
- Interaction structurally estimable: `{str(audit['interaction_structurally_estimable']).lower()}`
- Interaction residual df at unique-condition level: `{audit['interaction_condition_level_residual_df']}`
- Interaction residual df at trace level: `{audit['interaction_sample_level_residual_df']}`
- Overall scientific readiness: `{audit['overall_readiness']}`

Structural estimability is not evidence of an interaction effect and is not
predictive, causal, optimization, or engineering-release validation.

## Scientific Boundary

The software authenticates manifest/artifact bytes, SHA-256 and size, path
containment, explicit units, provenance completeness, target-cell assignment,
and the `sample_id + trace_id` one-to-one process-characterization join. It does
not independently authenticate the physical origin of a self-declared
measurement or the scientific validity of its reported values.

Issue #76 therefore remains scientifically blocked until authoritative real
physical traces exist and their origin/provenance are independently established.
"""


def run_workflow(
    *,
    manifest_path: Path,
    intake_root: Path,
    output_dir: Path,
) -> dict[str, Path]:
    # Preflight all externally supplied bytes before creating any workflow output.
    stage1_joined, intake_report = validate_augmented_manifest(
        manifest_path, intake_root
    )
    _prepare_output(output_dir)

    baseline_dir = output_dir / BASELINE_DIR
    baseline_paths = run_case_study(baseline_dir)
    baseline_integrated_path = Path(baseline_paths["integrated_table"])
    baseline = pd.read_csv(baseline_integrated_path)

    intake_dir = output_dir / INTAKE_DIR
    intake_dir.mkdir(parents=True, exist_ok=False)
    stage1_path = intake_dir / STAGE1_TABLE
    intake_report_path = intake_dir / INTAKE_REPORT
    augmented_path = intake_dir / AUGMENTED_TABLE
    structural_path = intake_dir / STRUCTURAL_INPUT

    stage1_joined.to_csv(stage1_path, index=False)
    intake_report_path.write_text(
        deterministic_json(intake_report), encoding="utf-8"
    )

    augmented = combine_with_frozen_baseline(baseline, stage1_joined)
    structural = structural_audit_input(augmented)
    augmented.to_csv(augmented_path, index=False)
    structural.to_csv(structural_path, index=False)

    audit_dir = output_dir / AUDIT_DIR
    audit_paths = run_audit(structural_path, audit_dir)
    audit = _read_json(Path(audit_paths["audit"]))

    summary = build_summary(
        intake_report=intake_report,
        augmented=augmented,
        structural=structural,
        audit=audit,
    )
    summary_path = output_dir / SUMMARY_FILE
    report_path = output_dir / REPORT_FILE
    manifest_out_path = output_dir / MANIFEST_FILE
    summary_path.write_text(deterministic_json(summary), encoding="utf-8")
    report_path.write_text(build_report(summary), encoding="utf-8")

    artifacts = {
        "baseline_integrated_table": baseline_integrated_path,
        "stage1_validated_joined_records": stage1_path,
        "stage1_intake_validation": intake_report_path,
        "augmented_integrated_table": augmented_path,
        "augmented_structural_audit_input": structural_path,
        "process_design_audit": Path(audit_paths["audit"]),
        "process_design_audit_manifest": Path(audit_paths["manifest"]),
        "summary": summary_path,
        "report": report_path,
    }
    workflow_manifest = {
        "schema_version": "1.0",
        "workflow": summary["workflow"],
        "status": "completed",
        "evidence_level": "Diagnostic",
        "input": {
            "manifest_filename": manifest_path.name,
            "raw_manifest_sha256": intake_report["raw_manifest_sha256"],
            "canonical_manifest_sha256": intake_report[
                "canonical_manifest_sha256"
            ],
        },
        "artifacts": {
            name: {
                "path": path.relative_to(output_dir).as_posix(),
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for name, path in sorted(artifacts.items())
        },
        "scientific_status_promoted": False,
        "model_trained": False,
        "optimization_performed": False,
        "network_access_performed": False,
    }
    manifest_out_path.write_text(
        deterministic_json(workflow_manifest), encoding="utf-8"
    )
    artifacts["manifest"] = manifest_out_path
    return artifacts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--intake-root", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = run_workflow(
            manifest_path=Path(args.manifest),
            intake_root=Path(args.intake_root),
            output_dir=Path(args.output),
        )
    except (OSError, ValueError, TypeError, KeyError, pd.errors.EmptyDataError) as exc:
        print(f"NIST augmented trace intake failed: {exc}", file=sys.stderr)
        return 1

    print("NIST AM-Bench augmented trace intake completed.")
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
