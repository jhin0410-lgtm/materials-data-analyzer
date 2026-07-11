"""Run Materials Project v1.3.4 group-aware baseline validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analyzers.grouped_regression_validation import (  # noqa: E402
    SplitConfig,
    ValidationConfig,
    calculate_file_sha256,
    default_model_configs,
    evaluate_validation,
    write_outputs,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Run fixed Materials Project v1.3.4 baseline validation. "
            "No API calls, descriptor generation, tuning, SHAP, or screening "
            "recommendations are performed."
        )
    )
    parser.add_argument(
        "--input",
        default="data/processed/materials_project_v1_3_analysis_ready.csv",
        help="v1.3.3 local-only analysis-ready descriptor CSV.",
    )
    parser.add_argument(
        "--inventory",
        default="data/processed/materials_project_v1_3_descriptor_inventory.csv",
        help="Descriptor inventory with primary_feature flags.",
    )
    parser.add_argument(
        "--ambiguity-summary",
        default="data/processed/materials_project_v1_3_composition_ambiguity_summary.csv",
        help="Composition ambiguity summary from v1.3.3.",
    )
    parser.add_argument(
        "--spec",
        default="data/case_studies/materials_project/validation_spec_v1_3.json",
        help="v1.3.4 validation specification.",
    )
    parser.add_argument(
        "--predictions-output",
        default="data/processed/materials_project_v1_3_validation_predictions.csv",
        help="Local-only row-level prediction output.",
    )
    parser.add_argument(
        "--metrics-output",
        default="data/processed/materials_project_v1_3_validation_metrics.csv",
        help="Compact fold-level validation metrics.",
    )
    parser.add_argument(
        "--comparison-output",
        default="data/processed/materials_project_v1_3_model_comparison_summary.csv",
        help="Compact model comparison summary.",
    )
    parser.add_argument(
        "--split-diagnostics-output",
        default="data/processed/materials_project_v1_3_split_diagnostics.csv",
        help="Split diagnostic summary.",
    )
    parser.add_argument(
        "--screening-output",
        default="data/processed/materials_project_v1_3_screening_metrics_summary.csv",
        help="Screening-aligned metric summary.",
    )
    return parser.parse_args()


def main() -> None:
    """Run validation and print compact JSON summary."""
    args = parse_args()
    spec = _load_json(args.spec)
    input_sha_before = calculate_file_sha256(args.input)
    analysis = pd.read_csv(args.input)
    inventory = pd.read_csv(args.inventory)
    ambiguity = pd.read_csv(args.ambiguity_summary)
    feature_columns = _feature_columns_from_inventory(inventory)
    _validate_spec_against_inventory(spec, feature_columns)
    analysis = _add_ambiguity_group_status(analysis, ambiguity)
    _validate_no_forbidden_features(feature_columns, spec)

    config = ValidationConfig(
        identifier_column=spec["identifier_column"],
        target_column=spec["target_column"],
        feature_columns=feature_columns,
        split_configs=[
            SplitConfig(
                name="random",
                splitter_type="shuffle",
                n_splits=int(spec["n_splits"]),
                test_size=float(spec["test_size"]),
                random_state=int(spec["random_state"]),
            ),
            SplitConfig(
                name="reduced_formula_group",
                splitter_type="group_shuffle",
                group_column="reduced_formula_group",
                n_splits=int(spec["n_splits"]),
                test_size=float(spec["test_size"]),
                random_state=int(spec["random_state"]),
            ),
            SplitConfig(
                name="chemical_system_group",
                splitter_type="group_shuffle",
                group_column="chemical_system_group",
                n_splits=int(spec["n_splits"]),
                test_size=float(spec["test_size"]),
                random_state=int(spec["random_state"]),
            ),
        ],
        model_configs=default_model_configs(random_state=int(spec["random_state"])),
        theoretical_column="theoretical",
        formula_group_column="reduced_formula_group",
        chemical_system_group_column="chemical_system_group",
        ambiguity_group_column="ambiguity_group_status",
    )

    outputs = evaluate_validation(
        analysis,
        config,
        forbidden_features=spec["forbidden_features"]
        + spec.get("evaluation_only_columns", []),
    )
    write_outputs(
        outputs,
        predictions_path=args.predictions_output,
        metrics_path=args.metrics_output,
        comparison_path=args.comparison_output,
        split_diagnostics_path=args.split_diagnostics_output,
        screening_path=args.screening_output,
    )
    input_sha_after = calculate_file_sha256(args.input)
    if input_sha_before != input_sha_after:
        raise RuntimeError("Source analysis-ready CSV changed during validation.")

    summary = _build_console_summary(outputs, feature_columns)
    summary.update(
        {
            "input_rows": int(len(analysis)),
            "feature_count": int(len(feature_columns)),
            "source_sha_unchanged": input_sha_before == input_sha_after,
            "input_sha256": input_sha_after,
            "output_sizes": {
                str(path): Path(path).stat().st_size
                for path in [
                    args.predictions_output,
                    args.metrics_output,
                    args.comparison_output,
                    args.split_diagnostics_output,
                    args.screening_output,
                ]
            },
        }
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


def _load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Validation spec must contain a JSON object.")
    return data


def _feature_columns_from_inventory(inventory: pd.DataFrame) -> list[str]:
    mask = inventory["primary_feature"].astype(str).str.lower().eq("true")
    return inventory.loc[mask, "column_name"].tolist()


def _validate_spec_against_inventory(spec: dict[str, Any], feature_columns: list[str]) -> None:
    if spec["feature_columns"] != feature_columns:
        raise ValueError("Validation spec feature_columns do not match descriptor inventory.")
    feature_hash = hashlib.sha256(
        json.dumps(feature_columns, sort_keys=True).encode("utf-8")
    ).hexdigest()
    if spec.get("feature_columns_sha256") != feature_hash:
        raise ValueError("Validation spec feature_columns_sha256 does not match inventory.")


def _validate_no_forbidden_features(feature_columns: list[str], spec: dict[str, Any]) -> None:
    forbidden = set(spec["forbidden_features"]) | set(spec.get("evaluation_only_columns", []))
    leaked = sorted(set(feature_columns).intersection(forbidden))
    if leaked:
        raise ValueError("Forbidden/evaluation-only features included: " + ", ".join(leaked))


def _add_ambiguity_group_status(
    analysis: pd.DataFrame,
    ambiguity: pd.DataFrame,
) -> pd.DataFrame:
    output = analysis.copy()
    ambiguous = set(
        ambiguity.loc[
            ambiguity["ambiguity_flag"].astype(str).str.lower().eq("true"),
            "reduced_formula_group",
        ].astype(str)
    )
    row_counts = dict(zip(ambiguity["reduced_formula_group"].astype(str), ambiguity["row_count"]))
    statuses = []
    for formula in output["reduced_formula_group"].astype(str):
        if formula in ambiguous:
            statuses.append("ambiguous_formula_group")
        elif int(row_counts.get(formula, 0)) <= 1:
            statuses.append("singleton_formula_group")
        else:
            statuses.append("non_ambiguous_formula_group")
    output["ambiguity_group_status"] = statuses
    return output


def _build_console_summary(
    outputs: dict[str, pd.DataFrame],
    feature_columns: list[str],
) -> dict[str, Any]:
    metrics = outputs["metrics"]
    split = outputs["split_diagnostics"]
    comparison = outputs["model_comparison"]
    screening = outputs["screening_metrics"]
    valid_metrics = metrics[metrics["status"].eq("valid")]
    return {
        "feature_count": len(feature_columns),
        "split_counts": split["split_strategy"].value_counts(dropna=False).to_dict(),
        "valid_metric_rows": int(len(valid_metrics)),
        "model_variants": sorted(metrics["model_variant"].dropna().unique().tolist()),
        "best_median_mae_by_strategy": _best_metric(comparison, "mae", minimize=True),
        "best_median_r2_by_strategy": _best_metric(comparison, "r2", minimize=False),
        "best_median_precision_at_10pct_by_strategy": _best_screening(
            screening,
            "precision_at_10pct",
        ),
        "validation_conclusion": _validation_conclusion(comparison),
    }


def _best_metric(comparison: pd.DataFrame, metric: str, *, minimize: bool) -> dict[str, Any]:
    result: dict[str, Any] = {}
    subset = comparison[comparison["metric"].eq(metric)]
    for strategy, group in subset.groupby("strategy"):
        group = group.sort_values("median", ascending=minimize, kind="mergesort")
        if not group.empty:
            row = group.iloc[0]
            result[strategy] = {
                "model_variant": row["model_variant"],
                "median": float(row["median"]),
            }
    return result


def _best_screening(screening: pd.DataFrame, metric: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    subset = screening[screening["metric"].eq(metric)]
    for strategy, group in subset.groupby("strategy"):
        values = group.dropna(subset=["median"]).sort_values("median", ascending=False, kind="mergesort")
        if not values.empty:
            row = values.iloc[0]
            result[strategy] = {
                "model_variant": row["model_variant"],
                "median": float(row["median"]),
            }
    return result


def _validation_conclusion(comparison: pd.DataFrame) -> dict[str, str]:
    conclusions = {}
    r2 = comparison[comparison["metric"].eq("r2")]
    for strategy, domain in [
        ("random", "interpolation/random"),
        ("reduced_formula_group", "unseen_formula_generalization"),
        ("chemical_system_group", "unseen_chemical_system_generalization"),
    ]:
        strategy_r2 = r2[r2["strategy"].eq(strategy)]
        best_median = strategy_r2["median"].max() if not strategy_r2.empty else float("nan")
        if pd.isna(best_median):
            status = "insufficient_evidence"
        elif strategy == "random" and best_median > 0:
            status = "validated_for_interpolation_only"
        elif best_median > 0:
            status = "limited"
        else:
            status = "not_validated_for_group_generalization"
        conclusions[domain] = status
    conclusions["descriptive_screening_utility"] = "limited"
    return conclusions


if __name__ == "__main__":
    main()

