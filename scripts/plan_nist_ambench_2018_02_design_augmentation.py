"""Plan the minimum staged NIST AM-Bench 2018-02 design augmentation without fitting a response model."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_nist_ambench_2018_02_process_design import (  # noqa: E402
    POWER,
    SPEED,
    audit_process_design,
)

CONDITIONS_FILE = "nist_design_augmentation_conditions.csv"
PLAN_FILE = "nist_design_augmentation_plan.json"
REPORT_FILE = "nist_design_augmentation_plan.md"
MANIFEST_FILE = "nist_design_augmentation_manifest.json"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _design_record(matrix: np.ndarray, parameter_names: list[str]) -> dict[str, Any]:
    rank = int(np.linalg.matrix_rank(matrix))
    parameter_count = int(matrix.shape[1])
    return {
        "parameter_names": parameter_names,
        "parameter_count": parameter_count,
        "matrix_rank": rank,
        "full_column_rank": rank == parameter_count,
        "condition_level_residual_df": int(matrix.shape[0] - rank),
    }


def summarize_design(points: list[tuple[float, float]]) -> dict[str, Any]:
    if len(points) < 2:
        raise ValueError("At least two process conditions are required.")
    frame = pd.DataFrame(points, columns=[POWER, SPEED]).drop_duplicates()
    frame = frame.sort_values([POWER, SPEED]).reset_index(drop=True)
    matrix = frame[[POWER, SPEED]].to_numpy(dtype=float)
    scale = matrix.std(axis=0, ddof=0)
    if np.any(scale == 0):
        raise ValueError("Both process factors must contain more than one level.")
    standardized = (matrix - matrix.mean(axis=0)) / scale
    power_z, speed_z = standardized[:, 0], standardized[:, 1]
    intercept = np.ones(len(frame))
    main = np.column_stack([intercept, power_z, speed_z])
    interaction = np.column_stack([main, power_z * speed_z])
    speed_curvature = np.column_stack([interaction, speed_z**2])
    full_quadratic = np.column_stack([interaction, power_z**2, speed_z**2])
    return {
        "unique_condition_count": int(len(frame)),
        "power_level_count": int(frame[POWER].nunique()),
        "speed_level_count": int(frame[SPEED].nunique()),
        "models": {
            "main_effects": _design_record(main, ["intercept", POWER, SPEED]),
            "main_effects_plus_interaction": _design_record(
                interaction,
                ["intercept", POWER, SPEED, f"{POWER}:{SPEED}"],
            ),
            "interaction_plus_speed_curvature": _design_record(
                speed_curvature,
                [
                    "intercept",
                    POWER,
                    SPEED,
                    f"{POWER}:{SPEED}",
                    f"{SPEED}^2",
                ],
            ),
            "full_quadratic_response_surface": _design_record(
                full_quadratic,
                [
                    "intercept",
                    POWER,
                    SPEED,
                    f"{POWER}:{SPEED}",
                    f"{POWER}^2",
                    f"{SPEED}^2",
                ],
            ),
        },
    }


def _condition_row(
    *,
    stage: str,
    sequence: int,
    power: float,
    speed: float,
    replicates: int,
    target_status: str,
    purpose: str,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "sequence": sequence,
        "condition_id": f"{stage}_condition_{sequence:02d}",
        POWER: float(power),
        SPEED: float(speed),
        "minimum_trace_replicates": int(replicates),
        "planned_new_trace_count": int(replicates),
        "target_status": target_status,
        "machine_feasibility_confirmed": False,
        "actual_power_calibration_required": True,
        "included_in_model_fit": True,
        "scientific_purpose": purpose,
    }


def build_augmentation_plan(table: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    conditions, audit = audit_process_design(table)
    power_levels = [float(value) for value in audit["factor_support"][POWER]["levels"]]
    speed_levels = [float(value) for value in audit["factor_support"][SPEED]["levels"]]
    if len(power_levels) != 2 or len(speed_levels) != 3:
        raise ValueError(
            "The NIST staged plan requires exactly two observed power levels and three observed speed levels."
        )
    if audit["unique_condition_count"] >= 6:
        raise ValueError("The observed two-by-three factor grid is already complete.")

    minimum_replicates = max(
        3,
        min(int(value) for value in audit["replication"]["replicate_counts"].values()),
    )
    observed = {
        (float(row[POWER]), float(row[SPEED]))
        for _, row in conditions.iterrows()
    }
    complete_observed_grid = [
        (power, speed) for power in power_levels for speed in speed_levels
    ]
    stage_1_points = sorted(set(complete_observed_grid) - observed)
    if not stage_1_points:
        raise ValueError("No missing observed-level factor combinations were found.")

    midpoint_power = (min(power_levels) + max(power_levels)) / 2.0
    if midpoint_power in power_levels:
        raise ValueError("A distinct midpoint power level could not be derived.")
    stage_2_points = [(midpoint_power, speed) for speed in speed_levels]

    rows: list[dict[str, Any]] = []
    for index, (power, speed) in enumerate(stage_1_points, start=1):
        rows.append(
            _condition_row(
                stage="stage_1_complete_observed_grid",
                sequence=index,
                power=power,
                speed=speed,
                replicates=minimum_replicates,
                target_status="derived_from_observed_level_crossing",
                purpose=(
                    "Create matched power contrasts at shared speeds and make the "
                    "power-by-speed interaction structurally estimable."
                ),
            )
        )
    for index, (power, speed) in enumerate(stage_2_points, start=1):
        rows.append(
            _condition_row(
                stage="stage_2_add_midpoint_power",
                sequence=index,
                power=power,
                speed=speed,
                replicates=minimum_replicates,
                target_status="mathematical_midpoint_candidate_unverified",
                purpose=(
                    "Add a third calibrated power level so two-factor quadratic "
                    "curvature becomes structurally estimable."
                ),
            )
        )

    recommendations = pd.DataFrame(rows).sort_values(
        ["stage", POWER, SPEED]
    ).reset_index(drop=True)

    current_points = sorted(observed)
    after_stage_1 = sorted(set(current_points) | set(stage_1_points))
    after_stage_2 = sorted(set(after_stage_1) | set(stage_2_points))
    current_design = summarize_design(current_points)
    stage_1_design = summarize_design(after_stage_1)
    stage_2_design = summarize_design(after_stage_2)

    stage_1_traces = int(len(stage_1_points) * minimum_replicates)
    stage_2_traces = int(len(stage_2_points) * minimum_replicates)
    plan = {
        "schema_version": "1.0",
        "workflow": "nist_ambench_2018_02_minimum_design_augmentation_plan",
        "status": "completed",
        "evidence_level": "Diagnostic",
        "current_design": {
            "sample_count": int(audit["sample_count"]),
            "unique_condition_count": int(audit["unique_condition_count"]),
            "replicate_counts": audit["replication"]["replicate_counts"],
            "power_levels_w": power_levels,
            "speed_levels_mm_s": speed_levels,
            "design_summary": current_design,
            "readiness": audit["readiness"],
        },
        "replication_policy": {
            "recommended_minimum_trace_replicates_per_new_condition": minimum_replicates,
            "basis": (
                "Use at least three independently traceable traces per new condition, "
                "matching the minimum replication already present in the NIST table."
            ),
            "randomization_required": True,
            "block_metadata_required": [
                "run_or_build_id",
                "acquisition_order",
                "spatial_location",
                "actual_calibrated_power",
                "measurement_batch",
            ],
        },
        "stages": {
            "stage_1_complete_observed_grid": {
                "priority": "Now",
                "new_condition_count": len(stage_1_points),
                "planned_new_trace_count": stage_1_traces,
                "conditions": [
                    {POWER: power, SPEED: speed}
                    for power, speed in stage_1_points
                ],
                "resulting_design": stage_1_design,
                "readiness_after_successful_execution": {
                    "matched_power_contrasts_at_shared_speeds": "structurally_available",
                    "main_effects": "structurally_estimable_with_condition_residual_df",
                    "power_speed_interaction": "structurally_estimable_with_condition_residual_df",
                    "speed_curvature": "structurally_estimable_with_limited_condition_residual_df",
                    "power_curvature": "not_identifiable_with_two_power_levels",
                    "predictive_validation": "not_ready",
                    "process_optimization": "not_ready",
                },
                "decision": (
                    "Stop after this stage when the immediate objective is defensible "
                    "factor separation and interaction diagnosis within the observed levels."
                ),
            },
            "stage_2_add_midpoint_power": {
                "priority": "Next only if curvature or optimization is an actual objective",
                "candidate_midpoint_power_w": midpoint_power,
                "candidate_status": (
                    "Mathematically derived only; machine feasibility and achieved calibrated "
                    "power must be confirmed before execution."
                ),
                "new_condition_count": len(stage_2_points),
                "planned_new_trace_count": stage_2_traces,
                "conditions": [
                    {POWER: power, SPEED: speed}
                    for power, speed in stage_2_points
                ],
                "resulting_design": stage_2_design,
                "readiness_after_successful_execution": {
                    "full_quadratic_response_surface": (
                        "structurally_estimable_with_condition_residual_df"
                    ),
                    "predictive_validation": "still_not_ready",
                    "process_optimization": (
                        "blocked_until_physical_feasibility_and_independent_validation"
                    ),
                },
            },
            "stage_3_independent_validation": {
                "priority": "Later",
                "numeric_conditions_automatically_selected": False,
                "minimum_distinct_validation_conditions": 2,
                "minimum_trace_replicates_per_condition": minimum_replicates,
                "requirements": [
                    "Predeclare validation conditions before inspecting their responses.",
                    "Do not use validation rows for fitting, feature selection, or threshold tuning.",
                    "Acquire validation traces in an independent run, day, or build block.",
                    "Keep material, system, geometry, calibration, and metrology definitions comparable.",
                    "Record achieved calibrated power rather than relying on commanded power.",
                    "Select conditions only after machine-safe and physically meaningful bounds are confirmed.",
                ],
                "claim_boundary": (
                    "Two interior validation conditions provide only a minimum diagnostic "
                    "interpolation check. Broader predictive claims require more conditions, "
                    "independent blocks, and transfer evidence."
                ),
            },
        },
        "totals": {
            "stage_1_new_conditions": len(stage_1_points),
            "stage_1_new_traces": stage_1_traces,
            "stage_2_additional_conditions": len(stage_2_points),
            "stage_2_additional_traces": stage_2_traces,
            "cumulative_new_conditions_through_stage_2": len(stage_1_points)
            + len(stage_2_points),
            "cumulative_new_traces_through_stage_2": stage_1_traces
            + stage_2_traces,
        },
        "decision": {
            "recommended_next_action": "execute_stage_1_only",
            "reason": (
                "Stage 1 is the smallest augmentation that removes the missing matched-power "
                "contrasts and makes the interaction structurally estimable without prematurely "
                "committing to a quadratic optimization program."
            ),
            "do_not_do_now": [
                "fit a predictive model to the current three conditions",
                "interpret the current saturated main-effects coefficients causally",
                "treat line energy as a sufficient physical mechanism",
                "run optimization before independent validation",
                "select validation conditions using observed responses",
            ],
        },
        "software_validation": {
            "response_model_fitted": False,
            "response_values_read": False,
            "optimization_performed": False,
            "missing_response_values_inferred": False,
            "machine_feasibility_assumed": False,
        },
        "scientific_closeout": {
            "result": "staged_minimum_design_augmentation_defined",
            "strongest_evidence": (
                "The existing three replicated conditions expose exactly which observed-level "
                "power-speed combinations are missing and which model matrices are rank deficient."
            ),
            "primary_limitation": (
                "The proposed targets are a statistical design plan, not proof that every target "
                "is machine-safe, physically meaningful, or achievable as calibrated actual power."
            ),
            "suitable_for": [
                "planning the next bounded NIST-style experiment",
                "estimating the minimum new condition and trace count",
                "preventing premature regression and optimization",
            ],
            "unsuitable_for": [
                "claiming future experiment success before execution",
                "machine control",
                "process safety approval",
                "causal or predictive claims from the current data",
            ],
        },
    }
    return recommendations, plan


def build_report(plan: dict[str, Any]) -> str:
    stage_1 = plan["stages"]["stage_1_complete_observed_grid"]
    stage_2 = plan["stages"]["stage_2_add_midpoint_power"]
    stage_3 = plan["stages"]["stage_3_independent_validation"]
    totals = plan["totals"]
    stage_1_rows = "\n".join(
        f"| {row[POWER]} | {row[SPEED]} | {plan['replication_policy']['recommended_minimum_trace_replicates_per_new_condition']} |"
        for row in stage_1["conditions"]
    )
    stage_2_rows = "\n".join(
        f"| {row[POWER]} | {row[SPEED]} | {plan['replication_policy']['recommended_minimum_trace_replicates_per_new_condition']} |"
        for row in stage_2["conditions"]
    )
    return f"""# NIST AM-Bench 2018-02 Minimum Design Augmentation

## Decision

**Execute Stage 1 only as the immediate next step.**

It is the smallest bounded augmentation that creates matched power contrasts at every observed speed and makes the power-speed interaction structurally estimable. It does not authorize causal claims or predictive modeling before the new measurements exist and pass comparability checks.

## Now — Complete the observed 2 × 3 grid

| Target actual power (W) | Scan speed (mm/s) | Minimum traces |
|---:|---:|---:|
{stage_1_rows}

- New conditions: `{stage_1['new_condition_count']}`
- New traces: `{stage_1['planned_new_trace_count']}`
- Resulting unique conditions: `{stage_1['resulting_design']['unique_condition_count']}`
- Interaction rank: `{stage_1['resulting_design']['models']['main_effects_plus_interaction']['matrix_rank']} / {stage_1['resulting_design']['models']['main_effects_plus_interaction']['parameter_count']}`
- Full quadratic rank: `{stage_1['resulting_design']['models']['full_quadratic_response_surface']['matrix_rank']} / {stage_1['resulting_design']['models']['full_quadratic_response_surface']['parameter_count']}`

Stage 1 supports direct factor separation and interaction diagnosis within the observed levels. It still cannot identify laser-power curvature because only two power levels exist.

## Next — Add a third calibrated power level only when curvature matters

Candidate mathematical midpoint: **{stage_2['candidate_midpoint_power_w']} W**

| Candidate actual power (W) | Scan speed (mm/s) | Minimum traces |
|---:|---:|---:|
{stage_2_rows}

- Additional conditions: `{stage_2['new_condition_count']}`
- Additional traces: `{stage_2['planned_new_trace_count']}`
- Resulting full-quadratic rank: `{stage_2['resulting_design']['models']['full_quadratic_response_surface']['matrix_rank']} / {stage_2['resulting_design']['models']['full_quadratic_response_surface']['parameter_count']}`
- Condition-level residual df: `{stage_2['resulting_design']['models']['full_quadratic_response_surface']['condition_level_residual_df']}`

The midpoint is mathematically derived, not machine-approved. Confirm safe operation and achieved calibrated power before use.

## Later — Independent validation

- Minimum distinct validation conditions: `{stage_3['minimum_distinct_validation_conditions']}`
- Minimum traces per condition: `{stage_3['minimum_trace_replicates_per_condition']}`
- Validation rows must remain excluded from fitting and tuning.
- Use an independent run, day, or build block.
- Select exact validation conditions only after machine-safe and physically meaningful bounds are confirmed.

This is only a minimum diagnostic interpolation check, not evidence of transfer across machines, materials, geometries, or metrology pipelines.

## Resource Summary

- Stage 1: `{totals['stage_1_new_conditions']}` conditions / `{totals['stage_1_new_traces']}` traces
- Stage 2 additional: `{totals['stage_2_additional_conditions']}` conditions / `{totals['stage_2_additional_traces']}` traces
- Through Stage 2: `{totals['cumulative_new_conditions_through_stage_2']}` conditions / `{totals['cumulative_new_traces_through_stage_2']}` traces

## Scientific Boundary

No response model was fitted, no melt-pool response was read or recomputed, no optimization was performed, and machine feasibility was not assumed. The output is a staged experimental-design recommendation only.
"""


def run_plan(integrated_table_path: str | Path, output_dir: str | Path) -> dict[str, Path]:
    source = Path(integrated_table_path)
    if not source.is_file():
        raise FileNotFoundError(f"Integrated sample table not found: {source}")
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(
            f"Output directory is not empty; existing files were preserved: {output}"
        )
    table = pd.read_csv(source)
    recommendations, plan = build_augmentation_plan(table)
    output.mkdir(parents=True, exist_ok=True)

    conditions_path = output / CONDITIONS_FILE
    plan_path = output / PLAN_FILE
    report_path = output / REPORT_FILE
    manifest_path = output / MANIFEST_FILE
    recommendations.to_csv(conditions_path, index=False)

    plan["input"] = {
        "filename": source.name,
        "sha256": sha256_file(source),
        "row_count": int(len(table)),
    }
    plan_path.write_text(
        json.dumps(plan, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(build_report(plan), encoding="utf-8")

    outputs = {
        "recommended_conditions": conditions_path,
        "plan": plan_path,
        "report": report_path,
    }
    manifest = {
        "schema_version": "1.0",
        "workflow": plan["workflow"],
        "input": plan["input"],
        "outputs": {name: path.name for name, path in outputs.items()},
        "output_sha256": {
            name: sha256_file(path) for name, path in outputs.items()
        },
        "response_model_fitted": False,
        "optimization_performed": False,
        "machine_feasibility_assumed": False,
        "scientific_status": "Diagnostic",
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    outputs["manifest"] = manifest_path
    return outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--integrated-table", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = run_plan(args.integrated_table, args.output)
    except (OSError, ValueError, TypeError, KeyError, pd.errors.EmptyDataError) as exc:
        print(f"NIST design-augmentation planning failed: {exc}", file=sys.stderr)
        return 1
    print("NIST AM-Bench minimum design-augmentation plan completed.")
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
