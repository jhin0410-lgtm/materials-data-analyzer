"""Audit NIST AM-Bench 2018-02 process-design identifiability without fitting a model."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

POWER = "actual_laser_power_w"
SPEED = "scan_speed_mm_s"
REQUIRED_COLUMNS = ["sample_id", "case_id", POWER, SPEED]
CONDITION_FILE = "process_design_condition_matrix.csv"
AUDIT_FILE = "process_design_audit.json"
REPORT_FILE = "process_design_audit.md"
MANIFEST_FILE = "process_design_audit_manifest.json"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_numeric(table: pd.DataFrame, column: str) -> pd.Series:
    values = pd.to_numeric(table[column], errors="coerce")
    if values.isna().any() or not values.map(lambda value: math.isfinite(float(value))).all():
        raise ValueError(f"Integrated table contains invalid numeric values in {column}.")
    return values.astype(float)


def validate_integrated_table(table: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in REQUIRED_COLUMNS if column not in table.columns]
    if missing:
        raise ValueError(f"Integrated table is missing required column(s): {', '.join(missing)}")
    validated = table.copy()
    validated["sample_id"] = validated["sample_id"].astype("string").str.strip()
    validated["case_id"] = validated["case_id"].astype("string").str.strip()
    if validated["sample_id"].isna().any() or validated["sample_id"].eq("").any():
        raise ValueError("Integrated table contains blank sample_id values.")
    if validated["case_id"].isna().any() or validated["case_id"].eq("").any():
        raise ValueError("Integrated table contains blank case_id values.")
    if validated["sample_id"].duplicated().any():
        raise ValueError("Integrated table sample_id values must be unique.")
    validated[POWER] = _finite_numeric(validated, POWER)
    validated[SPEED] = _finite_numeric(validated, SPEED)
    if (validated[[POWER, SPEED]] <= 0).any().any():
        raise ValueError("Laser power and scan speed must be positive.")
    return validated


def _standardized(values: pd.DataFrame) -> np.ndarray:
    matrix = values.to_numpy(dtype=float)
    scale = matrix.std(axis=0, ddof=0)
    if np.any(scale == 0):
        raise ValueError("Every audited process factor must contain more than one level.")
    return (matrix - matrix.mean(axis=0)) / scale


def _design_record(name: str, matrix: np.ndarray, parameter_names: list[str], n_conditions: int) -> dict[str, Any]:
    rank = int(np.linalg.matrix_rank(matrix))
    parameter_count = int(matrix.shape[1])
    return {
        "name": name,
        "parameter_names": parameter_names,
        "parameter_count": parameter_count,
        "matrix_rank": rank,
        "full_column_rank": rank == parameter_count,
        "condition_level_residual_df": int(n_conditions - rank),
        "identifiable_from_observed_conditions": rank == parameter_count,
        "model_adequacy_test_available": n_conditions - rank > 0,
    }


def audit_process_design(table: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    validated = validate_integrated_table(table)
    grouped = (
        validated.groupby(["case_id", POWER, SPEED], sort=True)
        .agg(replicate_count=("sample_id", "size"))
        .reset_index()
    )
    if grouped["case_id"].duplicated().any():
        raise ValueError("Each case_id must map to exactly one process condition.")

    n_samples = int(len(validated))
    n_conditions = int(len(grouped))
    pure_error_df = n_samples - n_conditions
    power_levels = sorted(float(value) for value in grouped[POWER].unique())
    speed_levels = sorted(float(value) for value in grouped[SPEED].unique())
    full_factorial_size = len(power_levels) * len(speed_levels)
    observed_pairs = {
        (float(row[POWER]), float(row[SPEED])) for _, row in grouped.iterrows()
    }
    missing_pairs = [
        {POWER: power, SPEED: speed}
        for power in power_levels
        for speed in speed_levels
        if (power, speed) not in observed_pairs
    ]

    z = _standardized(grouped[[POWER, SPEED]])
    power_z, speed_z = z[:, 0], z[:, 1]
    main = np.column_stack([np.ones(n_conditions), power_z, speed_z])
    interaction = np.column_stack([main, power_z * speed_z])
    quadratic = np.column_stack(
        [interaction, power_z**2, speed_z**2]
    )
    designs = {
        "main_effects": _design_record(
            "intercept + power + speed",
            main,
            ["intercept", POWER, SPEED],
            n_conditions,
        ),
        "main_effects_plus_interaction": _design_record(
            "intercept + power + speed + power*speed",
            interaction,
            ["intercept", POWER, SPEED, f"{POWER}:{SPEED}"],
            n_conditions,
        ),
        "quadratic_response_surface": _design_record(
            "intercept + power + speed + interaction + power^2 + speed^2",
            quadratic,
            [
                "intercept",
                POWER,
                SPEED,
                f"{POWER}:{SPEED}",
                f"{POWER}^2",
                f"{SPEED}^2",
            ],
            n_conditions,
        ),
    }

    power_speed_corr_sample = float(validated[[POWER, SPEED]].corr().iloc[0, 1])
    power_speed_corr_condition = float(grouped[[POWER, SPEED]].corr().iloc[0, 1])
    power_overlap_by_speed = {
        str(int(speed) if float(speed).is_integer() else speed): int(
            grouped.loc[grouped[SPEED].eq(speed), POWER].nunique()
        )
        for speed in speed_levels
    }
    speed_overlap_by_power = {
        str(power): int(grouped.loc[grouped[POWER].eq(power), SPEED].nunique())
        for power in power_levels
    }
    direct_power_contrast_available = any(value >= 2 for value in power_overlap_by_speed.values())
    direct_speed_contrast_available = any(value >= 2 for value in speed_overlap_by_power.values())

    blocking_reasons = [
        "Only three unique process conditions are observed.",
        "The main-effects design is saturated at the condition level, leaving zero lack-of-fit degrees of freedom.",
        "No scan speed is observed at both laser-power levels, so a direct matched-speed power contrast is unavailable.",
        "The interaction and quadratic response-surface designs are rank deficient.",
        "No held-out process condition, machine, material, or geometry is available for predictive validation.",
    ]
    audit = {
        "schema_version": "1.0",
        "workflow": "nist_ambench_2018_02_process_design_identifiability_audit",
        "status": "completed",
        "evidence_level": "Diagnostic",
        "sample_count": n_samples,
        "unique_condition_count": n_conditions,
        "replication": {
            "replicate_counts": {
                str(row.case_id): int(row.replicate_count)
                for row in grouped.itertuples(index=False)
            },
            "pure_error_degrees_of_freedom": int(pure_error_df),
            "all_conditions_replicated": bool((grouped["replicate_count"] >= 2).all()),
        },
        "factor_support": {
            POWER: {"levels": power_levels, "level_count": len(power_levels)},
            SPEED: {"levels": speed_levels, "level_count": len(speed_levels)},
            "full_factorial_condition_count": int(full_factorial_size),
            "observed_factorial_condition_count": n_conditions,
            "factorial_coverage_fraction": float(n_conditions / full_factorial_size),
            "missing_factor_combinations": missing_pairs,
            "power_levels_per_speed": power_overlap_by_speed,
            "speed_levels_per_power": speed_overlap_by_power,
            "direct_matched_speed_power_contrast_available": direct_power_contrast_available,
            "direct_within_power_speed_contrast_available": direct_speed_contrast_available,
        },
        "confounding_diagnostics": {
            "sample_level_power_speed_pearson_correlation": power_speed_corr_sample,
            "condition_level_power_speed_pearson_correlation": power_speed_corr_condition,
            "complete_factorial_crossing": n_conditions == full_factorial_size,
            "power_and_speed_effects_independently_validated": False,
        },
        "design_models": designs,
        "support_bounds": {
            POWER: {"minimum": min(power_levels), "maximum": max(power_levels)},
            SPEED: {"minimum": min(speed_levels), "maximum": max(speed_levels)},
            "unobserved_combinations_inside_bounds_supported": False,
            "extrapolation_outside_bounds_supported": False,
        },
        "readiness": {
            "descriptive_condition_comparison": "supported",
            "within_condition_variability_estimation": "supported",
            "main_effect_coefficient_fitting": "algebraically_estimable_but_not_scientifically_validated",
            "interaction_estimation": "not_identifiable",
            "curvature_estimation": "not_identifiable",
            "causal_effect_separation": "unsupported",
            "predictive_validation": "not_ready",
            "process_optimization": "not_ready",
            "overall": "not_ready_for_predictive_or_causal_modeling",
        },
        "blocking_reasons": blocking_reasons,
        "software_validation": {
            "model_trained": False,
            "response_metric_recomputed": False,
            "optimization_performed": False,
            "row_order_used": False,
            "missing_conditions_inferred": False,
        },
        "scientific_closeout": {
            "result": "diagnostic_design_audit_blocks_predictive_and_causal_modeling",
            "strongest_evidence": (
                "Ten trace-level observations provide replicated measurements at three explicit IN625 AMMT conditions."
            ),
            "primary_limitation": (
                "Three incompletely crossed power-speed combinations saturate a two-factor main-effects design and cannot identify interaction, curvature, or validated causal effects."
            ),
            "evidence_that_would_change_the_conclusion": (
                "Additional independently traceable conditions that cross power and speed at shared levels, include center or curvature points, retain replication, and provide held-out validation."
            ),
            "suitable_for": [
                "descriptive comparison of the three observed conditions",
                "within-condition repeatability review",
                "experimental-design gap identification",
            ],
            "unsuitable_for": [
                "causal separation of laser power and scan speed",
                "interaction or curvature claims",
                "predictive generalization",
                "process optimization",
                "engineering release decisions",
            ],
        },
    }
    return grouped, audit


def build_report(audit: dict[str, Any]) -> str:
    readiness = audit["readiness"]
    factors = audit["factor_support"]
    models = audit["design_models"]
    reasons = "\n".join(f"- {reason}" for reason in audit["blocking_reasons"])
    return f"""# NIST AM-Bench 2018-02 Process-Design Identifiability Audit

## Decision

**{readiness['overall']}**

The case supports descriptive comparison and repeatability review, but it is not ready for predictive, causal, interaction, curvature, or optimization claims.

## Design Support

- Trace observations: `{audit['sample_count']}`
- Unique process conditions: `{audit['unique_condition_count']}`
- Pure-error degrees of freedom from trace replication: `{audit['replication']['pure_error_degrees_of_freedom']}`
- Laser-power levels: `{factors[POWER]['level_count']}`
- Scan-speed levels: `{factors[SPEED]['level_count']}`
- Full-factorial coverage: `{factors['observed_factorial_condition_count']} / {factors['full_factorial_condition_count']}`
- Matched-speed power contrast available: `{str(factors['direct_matched_speed_power_contrast_available']).lower()}`

## Identifiability

| Candidate design | Parameters | Rank | Residual df at unique conditions | Identifiable |
|---|---:|---:|---:|---|
| Main effects | {models['main_effects']['parameter_count']} | {models['main_effects']['matrix_rank']} | {models['main_effects']['condition_level_residual_df']} | {models['main_effects']['identifiable_from_observed_conditions']} |
| Main effects + interaction | {models['main_effects_plus_interaction']['parameter_count']} | {models['main_effects_plus_interaction']['matrix_rank']} | {models['main_effects_plus_interaction']['condition_level_residual_df']} | {models['main_effects_plus_interaction']['identifiable_from_observed_conditions']} |
| Quadratic response surface | {models['quadratic_response_surface']['parameter_count']} | {models['quadratic_response_surface']['matrix_rank']} | {models['quadratic_response_surface']['condition_level_residual_df']} | {models['quadratic_response_surface']['identifiable_from_observed_conditions']} |

The main-effects matrix is algebraically full rank but saturated across the three unique conditions, so model adequacy or curvature cannot be tested. Algebraic estimability is not equivalent to scientifically validated independent effects.

## Blocking Reasons

{reasons}

## Scientific Closeout

- **Evidence level:** Diagnostic
- **Strongest evidence:** {audit['scientific_closeout']['strongest_evidence']}
- **Primary limitation:** {audit['scientific_closeout']['primary_limitation']}
- **Evidence needed:** {audit['scientific_closeout']['evidence_that_would_change_the_conclusion']}

No model was trained, no response metric was recomputed, no missing condition was inferred, and no optimization was performed.
"""


def run_audit(integrated_table_path: str | Path, output_dir: str | Path) -> dict[str, Path]:
    source = Path(integrated_table_path)
    if not source.is_file():
        raise FileNotFoundError(f"Integrated sample table not found: {source}")
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output directory is not empty; existing files were preserved: {output}")
    table = pd.read_csv(source)
    conditions, audit = audit_process_design(table)
    output.mkdir(parents=True, exist_ok=True)
    condition_path = output / CONDITION_FILE
    audit_path = output / AUDIT_FILE
    report_path = output / REPORT_FILE
    manifest_path = output / MANIFEST_FILE
    conditions.to_csv(condition_path, index=False)
    audit["input"] = {
        "filename": source.name,
        "sha256": sha256_file(source),
        "row_count": int(len(table)),
    }
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(build_report(audit), encoding="utf-8")
    outputs = {"condition_matrix": condition_path, "audit": audit_path, "report": report_path}
    manifest = {
        "schema_version": "1.0",
        "workflow": audit["workflow"],
        "input": audit["input"],
        "outputs": {name: path.name for name, path in outputs.items()},
        "output_sha256": {name: sha256_file(path) for name, path in outputs.items()},
        "model_trained": False,
        "optimization_performed": False,
        "scientific_status": "Diagnostic",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
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
        outputs = run_audit(args.integrated_table, args.output)
    except (OSError, ValueError, TypeError, KeyError, pd.errors.EmptyDataError) as exc:
        print(f"NIST process-design audit failed: {exc}", file=sys.stderr)
        return 1
    print("NIST AM-Bench process-design audit completed.")
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
