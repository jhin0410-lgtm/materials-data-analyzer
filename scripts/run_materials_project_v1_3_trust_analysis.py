"""Run Materials Project v1.3.5 trust-boundary diagnostics.

This script does not call the Materials Project API, regenerate descriptors,
fit new predictive models, tune hyperparameters, run SHAP, or recommend
candidate materials. It reads existing v1.3.4 validation artifacts and adds
conservative applicability-domain and claim-boundary diagnostics.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analyzers.applicability_domain import (  # noqa: E402
    ApplicabilityConfig,
    build_applicability_diagnostics,
    safe_spearman,
    summarize_distance_error_relationship,
    summarize_error_by_stratum,
)
from analyzers.grouped_regression_validation import calculate_file_sha256  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Run v1.3.5 Materials Project trust-boundary diagnostics over "
            "existing validation artifacts. No API/network call or model "
            "retraining is performed."
        )
    )
    parser.add_argument(
        "--analysis-input",
        default="data/processed/materials_project_v1_3_analysis_ready.csv",
        help="Local-only v1.3 analysis-ready descriptor CSV.",
    )
    parser.add_argument(
        "--predictions-input",
        default="data/processed/materials_project_v1_3_validation_predictions.csv",
        help="Local-only v1.3.4 row-level validation predictions.",
    )
    parser.add_argument(
        "--metrics-input",
        default="data/processed/materials_project_v1_3_validation_metrics.csv",
        help="Fold-level validation metrics.",
    )
    parser.add_argument(
        "--comparison-input",
        default="data/processed/materials_project_v1_3_model_comparison_summary.csv",
        help="Model comparison summary.",
    )
    parser.add_argument(
        "--screening-input",
        default="data/processed/materials_project_v1_3_screening_metrics_summary.csv",
        help="Screening metric summary.",
    )
    parser.add_argument(
        "--split-diagnostics-input",
        default="data/processed/materials_project_v1_3_split_diagnostics.csv",
        help="Existing split diagnostics.",
    )
    parser.add_argument(
        "--descriptor-inventory",
        default="data/processed/materials_project_v1_3_descriptor_inventory.csv",
        help="Descriptor inventory with primary_feature flags.",
    )
    parser.add_argument(
        "--ambiguity-summary",
        default="data/processed/materials_project_v1_3_composition_ambiguity_summary.csv",
        help="Formula ambiguity summary.",
    )
    parser.add_argument(
        "--validation-spec",
        default="data/case_studies/materials_project/validation_spec_v1_3.json",
        help="v1.3.4 validation spec.",
    )
    parser.add_argument(
        "--trust-spec",
        default="data/case_studies/materials_project/trust_spec_v1_3.json",
        help="v1.3.5 trust analysis spec.",
    )
    parser.add_argument(
        "--trust-output",
        default="data/processed/materials_project_v1_3_trust_diagnostics.csv",
        help="Local-only row-level trust diagnostics.",
    )
    parser.add_argument(
        "--applicability-output",
        default="data/processed/materials_project_v1_3_applicability_summary.csv",
        help="Compact applicability-domain summary.",
    )
    parser.add_argument(
        "--error-structure-output",
        default="data/processed/materials_project_v1_3_error_structure_summary.csv",
        help="Compact error structure summary.",
    )
    parser.add_argument(
        "--claim-boundary-output",
        default="data/processed/materials_project_v1_3_claim_boundary.csv",
        help="Machine-readable claim boundary summary.",
    )
    parser.add_argument(
        "--trust-conclusion-output",
        default="data/processed/materials_project_v1_3_trust_conclusion.csv",
        help="Compact v1.3 trust conclusion.",
    )
    return parser.parse_args()


def main() -> None:
    """Run trust diagnostics and print a compact JSON summary."""
    args = parse_args()
    summary = run_trust_analysis(args)
    print(json.dumps(summary, indent=2, sort_keys=True))


def run_trust_analysis(args: argparse.Namespace) -> dict[str, Any]:
    """Run trust analysis from parsed CLI arguments."""
    trust_spec = _load_json(args.trust_spec)
    validation_spec = _load_json(args.validation_spec)
    analysis_sha_before = calculate_file_sha256(args.analysis_input)
    predictions_sha_before = calculate_file_sha256(args.predictions_input)

    analysis = pd.read_csv(args.analysis_input)
    predictions = pd.read_csv(args.predictions_input)
    metrics = pd.read_csv(args.metrics_input)
    comparison = pd.read_csv(args.comparison_input)
    screening = pd.read_csv(args.screening_input)
    split_diagnostics = pd.read_csv(args.split_diagnostics_input)
    inventory = pd.read_csv(args.descriptor_inventory)
    ambiguity = pd.read_csv(args.ambiguity_summary)

    feature_columns = _feature_columns_from_inventory(inventory)
    _validate_feature_contract(feature_columns, validation_spec)
    _validate_required_inputs(analysis, predictions, feature_columns, validation_spec)
    analysis = _add_ambiguity_group_status(analysis, ambiguity)
    analysis["target_stratum"] = assign_target_strata(analysis[validation_spec["target_column"]])

    domain = build_split_applicability_table(
        analysis=analysis,
        predictions=predictions,
        feature_columns=feature_columns,
        identifier_column=validation_spec["identifier_column"],
        formula_column="reduced_formula_group",
        chemical_system_column="chemical_system_group",
        k_neighbors=int(trust_spec["applicability_domain_method"].get("k_neighbors", 5)),
    )
    trust_diagnostics = build_trust_diagnostics(predictions, domain)
    applicability_summary = build_applicability_summary(trust_diagnostics)
    error_structure = build_error_structure_summary(trust_diagnostics)
    eligibility = build_model_eligibility(metrics, comparison, screening)
    claim_boundary = build_claim_boundary(eligibility, comparison)
    trust_conclusion = build_trust_conclusion(
        eligibility=eligibility,
        applicability_summary=applicability_summary,
        comparison=comparison,
        split_diagnostics=split_diagnostics,
    )

    outputs = {
        "trust_diagnostics": trust_diagnostics,
        "applicability_summary": applicability_summary,
        "error_structure_summary": error_structure,
        "claim_boundary": claim_boundary,
        "trust_conclusion": trust_conclusion,
    }
    for name, df in outputs.items():
        _validate_no_credentials_or_absolute_paths(df, name)

    _write_csv(trust_diagnostics, args.trust_output)
    _write_csv(applicability_summary, args.applicability_output)
    _write_csv(error_structure, args.error_structure_output)
    _write_csv(claim_boundary, args.claim_boundary_output)
    _write_csv(trust_conclusion, args.trust_conclusion_output)

    if analysis_sha_before != calculate_file_sha256(args.analysis_input):
        raise RuntimeError("Source analysis-ready CSV changed during trust analysis.")
    if predictions_sha_before != calculate_file_sha256(args.predictions_input):
        raise RuntimeError("Source validation predictions CSV changed during trust analysis.")

    return {
        "analysis_rows": int(len(analysis)),
        "feature_count": int(len(feature_columns)),
        "trust_diagnostic_rows": int(len(trust_diagnostics)),
        "applicability_summary_rows": int(len(applicability_summary)),
        "error_structure_rows": int(len(error_structure)),
        "model_eligibility_counts": eligibility["eligibility_status"].value_counts().to_dict(),
        "representative_model_decision": trust_conclusion.loc[
            trust_conclusion["field"].eq("representative_model_decision"),
            "value",
        ].iloc[0],
        "shap_decision": trust_conclusion.loc[
            trust_conclusion["field"].eq("shap_decision"),
            "value",
        ].iloc[0],
        "analysis_sha_unchanged": True,
        "predictions_sha_unchanged": True,
        "output_sizes": {
            str(path): Path(path).stat().st_size
            for path in [
                args.trust_output,
                args.applicability_output,
                args.error_structure_output,
                args.claim_boundary_output,
                args.trust_conclusion_output,
            ]
        },
    }


def build_split_applicability_table(
    *,
    analysis: pd.DataFrame,
    predictions: pd.DataFrame,
    feature_columns: list[str],
    identifier_column: str,
    formula_column: str,
    chemical_system_column: str,
    k_neighbors: int,
) -> pd.DataFrame:
    """Reconstruct train/test membership from existing prediction rows."""
    rows: list[pd.DataFrame] = []
    split_keys = predictions[["split_strategy", "split_index", identifier_column]].drop_duplicates()
    for (strategy, split_index), split_test in split_keys.groupby(
        ["split_strategy", "split_index"],
        sort=True,
    ):
        test_ids = set(split_test[identifier_column].astype(str))
        test_df = analysis[analysis[identifier_column].astype(str).isin(test_ids)].copy()
        if len(test_df) != len(test_ids):
            raise RuntimeError(
                f"Prediction rows do not match analysis rows for {strategy}/{split_index}."
            )
        train_df = analysis[~analysis[identifier_column].astype(str).isin(test_ids)].copy()
        if train_df.empty:
            raise RuntimeError(f"Empty train fold reconstructed for {strategy}/{split_index}.")
        config = ApplicabilityConfig(
            feature_columns=feature_columns,
            identifier_column=identifier_column,
            k_neighbors=k_neighbors,
        )
        diagnostics, _ = build_applicability_diagnostics(train_df, test_df, config)
        train_formula = set(train_df[formula_column].astype(str)) if formula_column in train_df else set()
        train_chemsys = (
            set(train_df[chemical_system_column].astype(str))
            if chemical_system_column in train_df
            else set()
        )
        diagnostics.insert(0, "split_index", int(split_index))
        diagnostics.insert(0, "split_strategy", str(strategy))
        diagnostics["formula_seen_in_train_distance_context"] = (
            test_df[formula_column].astype(str).isin(train_formula).to_numpy()
            if formula_column in test_df
            else False
        )
        diagnostics["chemical_system_seen_in_train_distance_context"] = (
            test_df[chemical_system_column].astype(str).isin(train_chemsys).to_numpy()
            if chemical_system_column in test_df
            else False
        )
        diagnostics["target_stratum"] = test_df["target_stratum"].to_numpy()
        diagnostics["ambiguity_status"] = test_df["ambiguity_group_status"].to_numpy()
        rows.append(diagnostics)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def build_trust_diagnostics(predictions: pd.DataFrame, domain: pd.DataFrame) -> pd.DataFrame:
    """Join existing predictions with split-level applicability diagnostics."""
    merged = predictions.merge(
        domain,
        on=["split_strategy", "split_index", "material_id"],
        how="left",
        validate="many_to_one",
        suffixes=("", "_distance"),
    )
    if merged["nearest_train_distance"].isna().any():
        raise RuntimeError("Missing applicability diagnostics after prediction merge.")
    output = pd.DataFrame(
        {
            "split_strategy": merged["split_strategy"],
            "split_index": merged["split_index"],
            "model_variant": merged["model_variant"],
            "material_id": merged["material_id"],
            "actual_target": merged["actual_target"],
            "prediction": merged["constrained_prediction"],
            "absolute_error": merged["absolute_error"],
            "nearest_train_distance": merged["nearest_train_distance"],
            "knn_mean_distance": merged["knn_mean_distance"],
            "train_distance_percentile": merged["train_distance_percentile"],
            "applicability_status": merged["applicability_status"],
            "descriptor_seen": merged["descriptor_seen_in_train"],
            "formula_seen": merged["formula_seen_in_train"],
            "chemical_system_seen": merged["chemical_system_seen_in_train"],
            "ambiguity_status": merged["ambiguity_status"],
            "target_stratum": merged["target_stratum"],
            "theoretical": merged["theoretical"],
            "negative_prediction": merged["negative_prediction"],
        }
    )
    output["distance_metric"] = "train_scaled_euclidean"
    output["threshold_policy"] = "train_nn_p90_boundary_p95_out"
    return output


def build_applicability_summary(trust_diagnostics: pd.DataFrame) -> pd.DataFrame:
    """Build compact applicability and distance/error summaries."""
    status_summary = summarize_error_by_stratum(
        trust_diagnostics,
        stratum_type="domain_distance",
        stratum_column="applicability_status",
    )
    relationship = summarize_distance_error_relationship(trust_diagnostics)
    relationship["stratum_type"] = "distance_error_relationship"
    return pd.concat([status_summary, relationship], ignore_index=True, sort=False)


def build_error_structure_summary(trust_diagnostics: pd.DataFrame) -> pd.DataFrame:
    """Build compact error summaries across trust-boundary strata."""
    frames = [
        summarize_error_by_stratum(
            trust_diagnostics,
            stratum_type="domain_distance",
            stratum_column="applicability_status",
        ),
        summarize_error_by_stratum(
            trust_diagnostics.assign(
                descriptor_seen_status=np.where(
                    trust_diagnostics["descriptor_seen"], "descriptor_seen", "descriptor_novel"
                )
            ),
            stratum_type="descriptor_novelty",
            stratum_column="descriptor_seen_status",
        ),
        summarize_error_by_stratum(
            trust_diagnostics.assign(
                formula_seen_status=np.where(
                    trust_diagnostics["formula_seen"], "formula_seen", "formula_unseen"
                )
            ),
            stratum_type="formula_novelty",
            stratum_column="formula_seen_status",
        ),
        summarize_error_by_stratum(
            trust_diagnostics.assign(
                chemical_system_seen_status=np.where(
                    trust_diagnostics["chemical_system_seen"],
                    "chemical_system_seen",
                    "chemical_system_unseen",
                )
            ),
            stratum_type="chemical_system_novelty",
            stratum_column="chemical_system_seen_status",
        ),
        summarize_error_by_stratum(
            trust_diagnostics,
            stratum_type="formula_ambiguity",
            stratum_column="ambiguity_status",
        ),
        summarize_error_by_stratum(
            trust_diagnostics,
            stratum_type="target_stratum",
            stratum_column="target_stratum",
        ),
        summarize_error_by_stratum(
            trust_diagnostics.assign(theoretical_status="theoretical=" + trust_diagnostics["theoretical"].astype(str)),
            stratum_type="dataset_metadata",
            stratum_column="theoretical_status",
        ),
    ]
    return pd.concat(frames, ignore_index=True, sort=False)


def build_model_eligibility(
    metrics: pd.DataFrame,
    comparison: pd.DataFrame,
    screening: pd.DataFrame,
) -> pd.DataFrame:
    """Evaluate conservative model eligibility against the dummy baseline."""
    valid = metrics[metrics["status"].eq("valid")].copy()
    dummy = valid[valid["model_variant"].eq("dummy_median")].copy()
    rows: list[dict[str, Any]] = []
    non_dummy_models = sorted(set(valid["model_variant"]) - {"dummy_median"})
    for model in non_dummy_models:
        model_rows = valid[valid["model_variant"].eq(model)].copy()
        joined = model_rows.merge(
            dummy[
                [
                    "split_strategy",
                    "split_index",
                    "mae",
                    "median_absolute_error",
                    "r2",
                ]
            ],
            on=["split_strategy", "split_index"],
            suffixes=("", "_dummy"),
            how="left",
            validate="one_to_one",
        )
        mae_improvement_rate = float((joined["mae"] < joined["mae_dummy"]).mean())
        median_ae_improvement_rate = float(
            (joined["median_absolute_error"] < joined["median_absolute_error_dummy"]).mean()
        )
        spearman_positive_rate = float((joined["spearman"] > 0).mean())
        catastrophic_negative_r2_rate = float((joined["r2"] < -1.0).mean())
        formula_r2_median = _summary_metric(
            comparison,
            "reduced_formula_group",
            model,
            "r2",
            "median",
        )
        chemical_r2_median = _summary_metric(
            comparison,
            "chemical_system_group",
            model,
            "r2",
            "median",
        )
        formula_spearman_median = _summary_metric(
            comparison,
            "reduced_formula_group",
            model,
            "spearman",
            "median",
        )
        chemical_spearman_median = _summary_metric(
            comparison,
            "chemical_system_group",
            model,
            "spearman",
            "median",
        )
        screening_improved_count = _screening_improved_count(screening, model)
        eligible = (
            mae_improvement_rate >= 0.7
            and median_ae_improvement_rate >= 0.7
            and spearman_positive_rate >= 0.7
            and _positive(formula_r2_median)
            and _positive(chemical_r2_median)
            and _positive(formula_spearman_median)
            and _positive(chemical_spearman_median)
            and screening_improved_count >= 2
            and catastrophic_negative_r2_rate <= 0.2
        )
        diagnostic = (
            mae_improvement_rate > 0
            or median_ae_improvement_rate > 0
            or spearman_positive_rate > 0
            or _positive(formula_r2_median)
            or _positive(chemical_r2_median)
        )
        if eligible:
            status = "eligible_for_interpretation"
        elif diagnostic:
            status = "diagnostic_only"
        else:
            status = "not_eligible"
        rows.append(
            {
                "model_variant": model,
                "eligibility_status": status,
                "mae_improvement_rate_vs_dummy": mae_improvement_rate,
                "median_ae_improvement_rate_vs_dummy": median_ae_improvement_rate,
                "spearman_positive_rate": spearman_positive_rate,
                "formula_group_median_r2": formula_r2_median,
                "chemical_system_group_median_r2": chemical_r2_median,
                "formula_group_median_spearman": formula_spearman_median,
                "chemical_system_group_median_spearman": chemical_spearman_median,
                "screening_metric_improved_strategy_count": screening_improved_count,
                "catastrophic_negative_r2_rate": catastrophic_negative_r2_rate,
                "decision_basis": _eligibility_basis(status),
            }
        )
    return pd.DataFrame(rows)


def build_claim_boundary(
    eligibility: pd.DataFrame,
    comparison: pd.DataFrame,
) -> pd.DataFrame:
    """Create machine-readable allowed/prohibited claim boundaries."""
    any_eligible = eligibility["eligibility_status"].eq("eligible_for_interpretation").any()
    best_group_r2 = comparison[
        comparison["strategy"].isin(["reduced_formula_group", "chemical_system_group"])
        & comparison["metric"].eq("r2")
    ]["median"].max()
    allowed = [
        (
            "exact provenance dataset was acquired and validated",
            "allowed",
            "v1.3 acquisition and provenance artifacts are present",
            "Retrieval timestamp/API version limitations remain documented.",
            "The exact-provenance dataset was acquired and validated for this case study.",
        ),
        (
            "composition-only descriptors were generated reproducibly",
            "allowed",
            "60 primary descriptors are defined in the descriptor inventory",
            "Descriptors omit crystal structure and calculation settings.",
            "Composition-only descriptors were generated reproducibly.",
        ),
        (
            "random split contains substantial descriptor/formula overlap",
            "allowed",
            "split diagnostics record overlap under random validation",
            "Overlap is interpolation context, not leakage proof by itself.",
            "Random split results should be read as interpolation-like.",
        ),
        (
            "group-aware generalization is limited",
            "allowed",
            f"best group-aware median R2 observed: {best_group_r2:.4f}",
            "The conclusion is limited to this dataset and descriptor set.",
            "Group-aware generalization was limited.",
        ),
        (
            "deterministic descriptive screening of observed MP properties remains valid",
            "allowed",
            "v1.2 descriptive ranking uses observed calculated properties",
            "This is not predictive screening of new materials.",
            "Observed-property descriptive screening remains reproducible.",
        ),
    ]
    prohibited = [
        "accurate prediction of energy above hull",
        "reliable discovery of novel stable materials",
        "DFT replacement",
        "experimental synthesizability prediction",
        "causal physical mechanism",
        "robust unseen-chemical-system recommendation",
        "calibrated uncertainty",
        "production-ready screening model",
    ]
    rows = [
        {
            "claim": claim,
            "status": status,
            "evidence": evidence,
            "limitation": limitation,
            "allowed_wording": wording,
        }
        for claim, status, evidence, limitation, wording in allowed
    ]
    for claim in prohibited:
        rows.append(
            {
                "claim": claim,
                "status": "prohibited",
                "evidence": "No eligible predictive model was found."
                if not any_eligible
                else "Evidence is insufficient for this claim.",
                "limitation": "v1.3 is a validation and trust-boundary case study.",
                "allowed_wording": "Do not claim this from v1.3 results.",
            }
        )
    return pd.DataFrame(rows)


def build_trust_conclusion(
    *,
    eligibility: pd.DataFrame,
    applicability_summary: pd.DataFrame,
    comparison: pd.DataFrame,
    split_diagnostics: pd.DataFrame,
) -> pd.DataFrame:
    """Build compact final v1.3 trust conclusion rows."""
    any_eligible = eligibility["eligibility_status"].eq("eligible_for_interpretation").any()
    relationship = applicability_summary[
        applicability_summary.get("summary_type", pd.Series(dtype=object)).eq(
            "distance_error_relationship"
        )
    ]
    corr_median = (
        float(relationship["nearest_distance_absolute_error_spearman"].median())
        if not relationship.empty
        else np.nan
    )
    random_r2 = _best_median(comparison, "random", "r2", maximize=True)
    formula_r2 = _best_median(comparison, "reduced_formula_group", "r2", maximize=True)
    chemsys_r2 = _best_median(comparison, "chemical_system_group", "r2", maximize=True)
    random_overlap = _median_column(split_diagnostics, "random", "descriptor_vector_overlap_count")
    rows = [
        (
            "model_eligibility",
            "no_model_eligible_for_interpretation" if not any_eligible else "eligible_model_exists",
            "Non-dummy models failed the full conservative eligibility gate.",
        ),
        (
            "representative_model_decision",
            "none_selected" if not any_eligible else "eligible_model_available",
            "No representative model is selected when validation remains weak.",
        ),
        (
            "applicability_diagnostic_utility",
            _distance_utility_label(corr_median),
            f"Median nearest-distance/absolute-error Spearman: {_fmt(corr_median)}.",
        ),
        (
            "interpolation_conclusion",
            "weak_interpolation_evidence",
            f"Best random median R2: {_fmt(random_r2)}; median descriptor overlap count: {_fmt(random_overlap)}.",
        ),
        (
            "formula_generalization_conclusion",
            "limited",
            f"Best reduced-formula-group median R2: {_fmt(formula_r2)}.",
        ),
        (
            "chemical_system_generalization_conclusion",
            "limited",
            f"Best chemical-system-group median R2: {_fmt(chemsys_r2)}.",
        ),
        (
            "predictive_screening_conclusion",
            "not_defensible_for_novel_material_recommendation",
            "Screening metrics are affected by tied dummy predictions and weak group validation.",
        ),
        (
            "descriptive_screening_conclusion",
            "reproducible_for_observed_properties",
            "Observed Materials Project property ranking remains a deterministic descriptive analysis.",
        ),
        (
            "shap_decision",
            "deferred",
            "Model validity precedes XAI; no eligible predictive model was selected.",
        ),
        (
            "next_project_phase",
            "v1.4_smart_factory_process_quality_case_study",
            "Move to manufacturing process quality data with equipment/lot/time structure.",
        ),
    ]
    for _, row in eligibility.sort_values("model_variant").iterrows():
        rows.append(
            (
                f"model_eligibility_{row['model_variant']}",
                str(row["eligibility_status"]),
                str(row["decision_basis"]),
            )
        )
    return pd.DataFrame(rows, columns=["field", "value", "evidence"])


def assign_target_strata(target: pd.Series) -> pd.Series:
    """Assign fixed descriptive target strata for error analysis."""
    numeric = pd.to_numeric(target, errors="coerce")
    positive = numeric[numeric > 0]
    if positive.empty:
        return pd.Series(["exact_zero" if value == 0 else "unknown" for value in numeric])
    q25, q50, q75, q95 = positive.quantile([0.25, 0.50, 0.75, 0.95]).tolist()

    def label(value: float) -> str:
        if pd.isna(value):
            return "unknown"
        if abs(float(value)) <= 1e-12:
            return "exact_zero"
        if value <= q25:
            return "near_zero"
        if value <= q50:
            return "low"
        if value <= q75:
            return "middle"
        if value <= q95:
            return "high"
        return "extreme_tail"

    return numeric.map(label)


def _load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON object expected: {path}")
    return data


def _feature_columns_from_inventory(inventory: pd.DataFrame) -> list[str]:
    mask = inventory["primary_feature"].astype(str).str.lower().eq("true")
    return inventory.loc[mask, "column_name"].tolist()


def _validate_feature_contract(feature_columns: list[str], spec: dict[str, Any]) -> None:
    if spec["feature_columns"] != feature_columns:
        raise ValueError("Validation spec feature_columns do not match descriptor inventory.")


def _validate_required_inputs(
    analysis: pd.DataFrame,
    predictions: pd.DataFrame,
    feature_columns: list[str],
    spec: dict[str, Any],
) -> None:
    analysis_required = [
        spec["identifier_column"],
        spec["target_column"],
        "reduced_formula_group",
        "chemical_system_group",
        "theoretical",
        *feature_columns,
    ]
    prediction_required = [
        "split_strategy",
        "split_index",
        "model_variant",
        spec["identifier_column"],
        "actual_target",
        "constrained_prediction",
        "absolute_error",
        "descriptor_seen_in_train",
        "formula_seen_in_train",
        "chemical_system_seen_in_train",
        "negative_prediction",
    ]
    missing_analysis = [column for column in analysis_required if column not in analysis.columns]
    missing_prediction = [column for column in prediction_required if column not in predictions.columns]
    if missing_analysis:
        raise ValueError("Missing analysis column(s): " + ", ".join(missing_analysis))
    if missing_prediction:
        raise ValueError("Missing prediction column(s): " + ", ".join(missing_prediction))


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


def _summary_metric(
    comparison: pd.DataFrame,
    strategy: str,
    model_variant: str,
    metric: str,
    value_column: str,
) -> float:
    subset = comparison[
        comparison["strategy"].eq(strategy)
        & comparison["model_variant"].eq(model_variant)
        & comparison["metric"].eq(metric)
    ]
    if subset.empty:
        return np.nan
    return float(subset[value_column].iloc[0])


def _screening_improved_count(screening: pd.DataFrame, model_variant: str) -> int:
    rows = 0
    for strategy in sorted(screening["strategy"].dropna().unique()):
        model_value = _screening_metric(screening, strategy, model_variant)
        dummy_value = _screening_metric(screening, strategy, "dummy_median")
        if pd.notna(model_value) and pd.notna(dummy_value) and model_value > dummy_value:
            rows += 1
    return rows


def _screening_metric(screening: pd.DataFrame, strategy: str, model_variant: str) -> float:
    subset = screening[
        screening["strategy"].eq(strategy)
        & screening["model_variant"].eq(model_variant)
        & screening["metric"].eq("precision_at_10pct")
    ]
    if subset.empty:
        return np.nan
    return float(subset["median"].iloc[0])


def _positive(value: float) -> bool:
    return pd.notna(value) and value > 0


def _eligibility_basis(status: str) -> str:
    if status == "eligible_for_interpretation":
        return "passes conservative predictive interpretation gate"
    if status == "diagnostic_only":
        return "some metric signal exists, but group-aware validation is insufficient"
    return "does not improve enough over dummy or has unstable validation metrics"


def _best_median(comparison: pd.DataFrame, strategy: str, metric: str, *, maximize: bool) -> float:
    subset = comparison[comparison["strategy"].eq(strategy) & comparison["metric"].eq(metric)]
    if subset.empty:
        return np.nan
    values = pd.to_numeric(subset["median"], errors="coerce").dropna()
    if values.empty:
        return np.nan
    return float(values.max() if maximize else values.min())


def _median_column(df: pd.DataFrame, strategy: str, column: str) -> float:
    subset = df[df["split_strategy"].eq(strategy)]
    if subset.empty or column not in subset.columns:
        return np.nan
    values = pd.to_numeric(subset[column], errors="coerce").dropna()
    return float(values.median()) if len(values) else np.nan


def _distance_utility_label(correlation: float) -> str:
    if pd.isna(correlation):
        return "insufficient_variation"
    if correlation >= 0.3:
        return "moderate_positive_proxy"
    if correlation >= 0.15:
        return "weak_positive_proxy"
    return "weak_or_inconsistent_proxy"


def _fmt(value: float) -> str:
    return "nan" if pd.isna(value) else f"{float(value):.4f}"


def _validate_no_credentials_or_absolute_paths(df: pd.DataFrame, name: str) -> None:
    text = df.to_csv(index=False)
    patterns = [
        (r"[A-Za-z]:\\", "Windows absolute path"),
        (r"/home/|/Users/|/mnt/", "Unix-like absolute path"),
        (r"api[_-]?key|secret|credential|token", "credential-like string"),
    ]
    for pattern, label in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            raise RuntimeError(f"{label} detected in output: {name}")


def _write_csv(df: pd.DataFrame, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)


if __name__ == "__main__":
    main()
