"""Run the representative NIST process-characterization workflow end to end.

This orchestration intentionally reuses the existing verified case, process-design
audit, and bounded experiment-planning entry points. It does not introduce a new
scientific analyzer, fit a model, or approve experimental settings.
"""
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
from plan_nist_ambench_2018_02_design_augmentation import run_plan  # noqa: E402
from run_nist_ambench_2018_02_workflow import run_integrated_workflow  # noqa: E402

CASE_DIR_NAME = "01_verified_case"
AUDIT_DIR_NAME = "02_process_design_audit"
PLAN_DIR_NAME = "03_minimum_design_plan"
SUMMARY_NAME = "representative_workflow_summary.json"
REPORT_NAME = "representative_workflow_report.md"
MANIFEST_NAME = "representative_workflow_manifest.json"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
            "Representative workflow output directory must be new or empty; "
            f"existing files were preserved: {output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _validate_component_results(
    case_manifest: dict[str, Any],
    audit: dict[str, Any],
    plan: dict[str, Any],
) -> None:
    if case_manifest.get("generation_status") != "completed":
        raise ValueError("Representative case workflow did not complete.")
    if str(case_manifest.get("scientific_status", "")).lower() != "diagnostic":
        raise ValueError("Representative case scientific status must remain diagnostic.")
    if case_manifest.get("model_trained") is not False:
        raise ValueError("Representative case unexpectedly reports model training.")
    if case_manifest.get("optimization_performed") is not False:
        raise ValueError("Representative case unexpectedly reports optimization.")

    if audit.get("status") != "completed":
        raise ValueError("Process-design audit did not complete.")
    if audit.get("evidence_level") != "Diagnostic":
        raise ValueError("Process-design audit evidence level must remain Diagnostic.")
    if audit.get("readiness", {}).get("overall") != (
        "not_ready_for_predictive_or_causal_modeling"
    ):
        raise ValueError("Process-design audit readiness decision changed unexpectedly.")
    if audit.get("software_validation", {}).get("model_trained") is not False:
        raise ValueError("Process-design audit unexpectedly reports model training.")

    if plan.get("status") != "completed":
        raise ValueError("Minimum design-augmentation plan did not complete.")
    if plan.get("evidence_level") != "Diagnostic":
        raise ValueError("Design-augmentation evidence level must remain Diagnostic.")
    if plan.get("decision", {}).get("recommended_next_action") != (
        "execute_stage_1_only"
    ):
        raise ValueError("Minimum design-plan next action changed unexpectedly.")
    if plan.get("software_validation", {}).get("response_model_fitted") is not False:
        raise ValueError("Design plan unexpectedly reports response-model fitting.")
    if plan.get("software_validation", {}).get("optimization_performed") is not False:
        raise ValueError("Design plan unexpectedly reports optimization.")


def build_summary(
    *,
    output_dir: Path,
    integrated_table_path: Path,
    case_manifest_path: Path,
    audit_path: Path,
    audit_manifest_path: Path,
    plan_path: Path,
    plan_manifest_path: Path,
) -> dict[str, Any]:
    case_manifest = _read_json(case_manifest_path, "integrated case workflow manifest")
    audit = _read_json(audit_path, "process-design audit")
    audit_manifest = _read_json(audit_manifest_path, "process-design audit manifest")
    plan = _read_json(plan_path, "minimum design-augmentation plan")
    plan_manifest = _read_json(plan_manifest_path, "minimum design-plan manifest")
    _validate_component_results(case_manifest, audit, plan)

    integrated = pd.read_csv(integrated_table_path)
    if len(integrated) != 10:
        raise ValueError("Representative integrated table must contain ten NIST traces.")
    if integrated["sample_id"].isna().any() or integrated["sample_id"].duplicated().any():
        raise ValueError("Representative integrated table sample_id values must be complete and unique.")

    stage_1 = plan["stages"]["stage_1_complete_observed_grid"]
    stage_2 = plan["stages"]["stage_2_add_midpoint_power"]
    return {
        "schema_version": "1.0",
        "workflow": "representative_nist_process_characterization_workflow",
        "status": "completed",
        "evidence_level": "Diagnostic",
        "purpose": (
            "Provide one reproducible user entry point from provenance-bound real "
            "process-characterization data through readiness gating and a bounded "
            "next-experiment recommendation."
        ),
        "components": {
            "verified_case": {
                "directory": CASE_DIR_NAME,
                "manifest": _relative(case_manifest_path, output_dir),
                "manifest_sha256": sha256_file(case_manifest_path),
                "trace_count": int(len(integrated)),
                "scientific_status": case_manifest["scientific_status"],
                "model_trained": False,
                "optimization_performed": False,
            },
            "process_design_audit": {
                "directory": AUDIT_DIR_NAME,
                "audit": _relative(audit_path, output_dir),
                "manifest": _relative(audit_manifest_path, output_dir),
                "manifest_sha256": sha256_file(audit_manifest_path),
                "unique_condition_count": int(audit["unique_condition_count"]),
                "factorial_coverage_fraction": float(
                    audit["factor_support"]["factorial_coverage_fraction"]
                ),
                "readiness": audit["readiness"]["overall"],
                "model_trained": False,
                "optimization_performed": False,
            },
            "minimum_design_plan": {
                "directory": PLAN_DIR_NAME,
                "plan": _relative(plan_path, output_dir),
                "manifest": _relative(plan_manifest_path, output_dir),
                "manifest_sha256": sha256_file(plan_manifest_path),
                "recommended_next_action": plan["decision"][
                    "recommended_next_action"
                ],
                "stage_1_new_conditions": int(stage_1["new_condition_count"]),
                "stage_1_new_traces": int(stage_1["planned_new_trace_count"]),
                "stage_2_is_conditional": True,
                "stage_2_candidate_midpoint_power_w": float(
                    stage_2["candidate_midpoint_power_w"]
                ),
                "response_model_fitted": False,
                "optimization_performed": False,
                "machine_feasibility_assumed": False,
            },
        },
        "user_decision": {
            "now": (
                "Use the verified case for diagnostic demonstration and, if a real "
                "follow-up experiment is available, execute Stage 1 only: add the "
                "three missing observed-level power-speed combinations with at least "
                "three independently traceable traces per condition."
            ),
            "next": (
                "Add the midpoint-power stage only when curvature or optimization is "
                "an explicit objective and machine feasibility is independently confirmed."
            ),
            "later": (
                "Reserve predeclared conditions from an independent run, day, or build "
                "block for validation; do not use them for fitting or tuning."
            ),
        },
        "scientific_closeout": {
            "result": "representative_workflow_completed_with_modeling_gate_active",
            "strongest_evidence": (
                "Ten explicitly identified NIST IN625 traces pass source, schema, "
                "sample-handoff, artifact-integrity, and process-design checks."
            ),
            "primary_limitation": (
                "Only three coupled process conditions are observed; the current data "
                "remain unsuitable for predictive, causal, or optimization claims."
            ),
            "evidence_that_would_change_the_conclusion": (
                "Successfully executed and provenance-complete Stage 1 conditions, "
                "followed by purpose-specific curvature points and genuinely independent "
                "validation when those claims are required."
            ),
            "suitable_for": [
                "repository quickstart and portfolio demonstration",
                "software and provenance validation",
                "diagnostic process-characterization comparison",
                "bounded next-experiment planning",
            ],
            "unsuitable_for": [
                "predictive model training on the current three conditions",
                "causal attribution of laser power or scan speed",
                "process optimization",
                "machine control or process safety approval",
                "engineering release decisions",
            ],
        },
        "software_validation": {
            "existing_component_workflows_reused": True,
            "new_scientific_analyzer_added": False,
            "response_model_fitted": False,
            "response_values_inferred": False,
            "optimization_performed": False,
            "machine_feasibility_assumed": False,
            "row_order_join_used": False,
        },
    }


def build_report(summary: dict[str, Any]) -> str:
    case = summary["components"]["verified_case"]
    audit = summary["components"]["process_design_audit"]
    plan = summary["components"]["minimum_design_plan"]
    closeout = summary["scientific_closeout"]
    return f"""# Representative Process–Characterization Workflow

## Decision

**Evidence level: {summary['evidence_level']}**

The workflow completed with the modeling gate active. It is a reproducible user
entry point and portfolio case study, not an optimization or deployment system.

## One-command evidence chain

```text
tracked NIST process and optical-metrology tables
-> source, schema, and sample identity validation
-> 40 provenance-bearing characterization records
-> explicit sample_id integration for 10 traces
-> artifact and summary integrity verification
-> process-design identifiability audit
-> bounded minimum next-experiment plan
-> diagnostic scientific closeout
```

## Component results

| Component | Result |
|---|---|
| Verified real case | {case['trace_count']} matched traces; status `{case['scientific_status']}` |
| Design readiness | {audit['unique_condition_count']} conditions; factorial coverage `{audit['factorial_coverage_fraction']:.2f}` |
| Modeling gate | `{audit['readiness']}` |
| Immediate experiment plan | {plan['stage_1_new_conditions']} conditions / {plan['stage_1_new_traces']} traces |
| Conditional midpoint candidate | {plan['stage_2_candidate_midpoint_power_w']} W; not machine-approved |

## Now

{summary['user_decision']['now']}

## Next

{summary['user_decision']['next']}

## Later

{summary['user_decision']['later']}

## Main directories

- `{CASE_DIR_NAME}/`: integrated case tables, figures, reports, and manifests;
- `{AUDIT_DIR_NAME}/`: process-design rank, factor support, and readiness decision;
- `{PLAN_DIR_NAME}/`: staged recommended conditions and scientific boundaries.

## Scientific closeout

- **Result:** {closeout['result']}
- **Strongest evidence:** {closeout['strongest_evidence']}
- **Primary limitation:** {closeout['primary_limitation']}
- **Evidence needed:** {closeout['evidence_that_would_change_the_conclusion']}

No new analyzer was added. No response model was fitted, no missing response was
inferred, no optimization was performed, and machine feasibility was not assumed.
"""


def _artifact_inventory(output_dir: Path) -> dict[str, str]:
    return {
        path.relative_to(output_dir).as_posix(): sha256_file(path)
        for path in sorted(output_dir.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file() and path.name != MANIFEST_NAME
    }


def run_representative_workflow(output_dir: str | Path) -> dict[str, Path]:
    output = Path(output_dir)
    _prepare_output_dir(output)

    case_dir = output / CASE_DIR_NAME
    audit_dir = output / AUDIT_DIR_NAME
    plan_dir = output / PLAN_DIR_NAME

    case_outputs = run_integrated_workflow(case_dir)
    integrated_table = case_outputs.get("integrated_table")
    if not isinstance(integrated_table, Path):
        raise ValueError("Integrated case workflow did not expose integrated_table.")

    audit_outputs = run_audit(integrated_table, audit_dir)
    plan_outputs = run_plan(integrated_table, plan_dir)

    case_manifest_path = case_outputs["integrated_workflow_manifest"]
    audit_path = audit_outputs["audit"]
    audit_manifest_path = audit_outputs["manifest"]
    plan_path = plan_outputs["plan"]
    plan_manifest_path = plan_outputs["manifest"]

    summary = build_summary(
        output_dir=output,
        integrated_table_path=integrated_table,
        case_manifest_path=case_manifest_path,
        audit_path=audit_path,
        audit_manifest_path=audit_manifest_path,
        plan_path=plan_path,
        plan_manifest_path=plan_manifest_path,
    )

    summary_path = output / SUMMARY_NAME
    report_path = output / REPORT_NAME
    manifest_path = output / MANIFEST_NAME
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(build_report(summary), encoding="utf-8")

    artifact_sha256 = _artifact_inventory(output)
    manifest = {
        "schema_version": "1.0",
        "workflow": summary["workflow"],
        "generation_status": "completed",
        "scientific_status": summary["evidence_level"],
        "entry_point": "scripts/run_representative_process_characterization_workflow.py",
        "component_directories": [CASE_DIR_NAME, AUDIT_DIR_NAME, PLAN_DIR_NAME],
        "summary": SUMMARY_NAME,
        "report": REPORT_NAME,
        "artifact_count": len(artifact_sha256),
        "artifact_sha256": artifact_sha256,
        "network_access_performed": False,
        "new_scientific_analyzer_added": False,
        "response_model_fitted": False,
        "optimization_performed": False,
        "machine_feasibility_assumed": False,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return {
        "case_directory": case_dir,
        "audit_directory": audit_dir,
        "plan_directory": plan_dir,
        "summary": summary_path,
        "report": report_path,
        "manifest": manifest_path,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        required=True,
        help="New or empty output directory for the representative workflow.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = run_representative_workflow(args.output)
    except (OSError, ValueError, TypeError, KeyError, pd.errors.EmptyDataError) as exc:
        print(f"Representative process-characterization workflow failed: {exc}", file=sys.stderr)
        return 1

    print("Representative process-characterization workflow completed.")
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
