"""Generic trust-boundary summaries for classification validation outputs.

The functions here aggregate existing compact validation artifacts. They do
not fit models, tune thresholds, call networks, or inspect row-level source
data.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ClassificationTrustConfig:
    """Configuration for fixed trust-boundary rules."""

    case_study_version: str
    source_artifact: str
    source_sha256: str
    baseline_model_name: str
    global_row_count: int
    global_failure_count: int
    min_temporal_pr_auc_lift_over_prevalence: float = 0.05
    min_final_pr_auc_lift_over_prevalence: float = 0.05
    min_temporal_dummy_lift_fold_rate: float = 0.60
    max_temporal_iqr_pr_auc: float = 0.08
    max_random_temporal_pr_auc_gap: float = 0.05
    min_threshold_recall: float = 0.20
    min_threshold_precision: float = 0.05
    min_supported_fold_count: int = 3

    @property
    def prevalence_baseline(self) -> float:
        """Return the global failure prevalence baseline."""
        return self.global_failure_count / self.global_row_count if self.global_row_count else np.nan


def calculate_file_sha256(path: str | Path) -> str:
    """Calculate SHA-256 without modifying a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_trust_outputs(
    *,
    metrics: pd.DataFrame,
    split_diagnostics: pd.DataFrame,
    model_summary: pd.DataFrame,
    random_temporal_gap: pd.DataFrame,
    threshold_summary: pd.DataFrame,
    error_structure: pd.DataFrame,
    classification_conclusion: pd.DataFrame,
    config: ClassificationTrustConfig,
) -> dict[str, pd.DataFrame]:
    """Build all compact trust-boundary output tables."""
    temporal = build_temporal_stability_summary(metrics, config)
    eligibility = build_model_eligibility(
        metrics=metrics,
        temporal_stability=temporal,
        model_summary=model_summary,
        random_temporal_gap=random_temporal_gap,
        threshold_summary=threshold_summary,
        config=config,
    )
    operational = build_operational_boundary(
        threshold_summary=threshold_summary,
        error_structure=error_structure,
        config=config,
    )
    claims = build_claim_boundary(eligibility, config)
    trust = build_trust_summary(
        eligibility=eligibility,
        temporal_stability=temporal,
        random_temporal_gap=random_temporal_gap,
        threshold_summary=threshold_summary,
        split_diagnostics=split_diagnostics,
        classification_conclusion=classification_conclusion,
        config=config,
    )
    closeout = build_closeout_conclusion(eligibility, trust, config)
    return {
        "model_eligibility": eligibility,
        "temporal_stability_summary": temporal,
        "operational_boundary": operational,
        "claim_boundary": claims,
        "trust_summary": trust,
        "closeout_conclusion": closeout,
    }


def build_temporal_stability_summary(
    metrics: pd.DataFrame,
    config: ClassificationTrustConfig,
) -> pd.DataFrame:
    """Summarize temporal PR-AUC stability by model."""
    valid = metrics[metrics["status"].eq("valid")].copy()
    temporal = valid[valid["validation_type"].eq("primary_temporal")].copy()
    dummy = temporal[temporal["model_name"].eq(config.baseline_model_name)][
        ["split_id", "average_precision"]
    ].rename(columns={"average_precision": "dummy_average_precision"})
    rows: list[dict[str, Any]] = []
    for model_name in sorted(valid["model_name"].dropna().unique()):
        model_rows = temporal[temporal["model_name"].eq(model_name)].copy()
        values = pd.to_numeric(model_rows["average_precision"], errors="coerce").dropna()
        joined = model_rows.merge(dummy, on="split_id", how="left", validate="many_to_one")
        lift = pd.to_numeric(joined["average_precision"], errors="coerce") - pd.to_numeric(
            joined["dummy_average_precision"],
            errors="coerce",
        )
        final = model_rows[model_rows["split_id"].astype(str).str.contains("final_holdout")]
        final_value = _median(final, "average_precision")
        median_value = float(values.median()) if len(values) else np.nan
        rows.append(
            {
                "case_study_version": config.case_study_version,
                "source_artifact": config.source_artifact,
                "source_sha256": config.source_sha256,
                "model_name": model_name,
                "fold_count": int(len(model_rows)),
                "supported_fold_count": int(
                    model_rows["test_failures"].fillna(0).astype(float).gt(0).sum()
                ),
                "temporal_mean_pr_auc": _mean(values),
                "temporal_median_pr_auc": median_value,
                "temporal_min_pr_auc": _min(values),
                "temporal_max_pr_auc": _max(values),
                "temporal_std_pr_auc": _std(values),
                "temporal_iqr_pr_auc": _iqr(values),
                "temporal_cv_pr_auc": _cv(values),
                "positive_lift_fold_count": int(lift.gt(0).sum()),
                "negative_or_zero_lift_fold_count": int(lift.le(0).sum()),
                "positive_lift_fold_rate": float(lift.gt(0).mean()) if len(lift) else np.nan,
                "final_holdout_pr_auc": final_value,
                "final_holdout_deviation_from_temporal_median": _subtract_or_nan(
                    final_value,
                    median_value,
                ),
                "prevalence_baseline": config.prevalence_baseline,
                "temporal_lift_over_prevalence": _subtract_or_nan(
                    median_value,
                    config.prevalence_baseline,
                ),
                "final_lift_over_prevalence": _subtract_or_nan(
                    final_value,
                    config.prevalence_baseline,
                ),
                "stability_note": _stability_note(values, final_value, median_value),
            }
        )
    return pd.DataFrame(rows)


def build_model_eligibility(
    *,
    metrics: pd.DataFrame,
    temporal_stability: pd.DataFrame,
    model_summary: pd.DataFrame,
    random_temporal_gap: pd.DataFrame,
    threshold_summary: pd.DataFrame,
    config: ClassificationTrustConfig,
) -> pd.DataFrame:
    """Apply predeclared eligibility rules to each model."""
    rows: list[dict[str, Any]] = []
    summary = model_summary.set_index("model_name") if not model_summary.empty else pd.DataFrame()
    for _, temporal in temporal_stability.iterrows():
        model_name = str(temporal["model_name"])
        threshold = _threshold_medians(threshold_summary, model_name)
        brier_score = _primary_metric_median(metrics, model_name, "brier_score")
        random_gap = _gap_value(random_temporal_gap, model_name, "average_precision")
        dummy_temporal = _model_summary_value(summary, model_name, "dummy_temporal_median_pr_auc")
        rejection_reasons = _eligibility_rejection_reasons(
            model_name=model_name,
            temporal=temporal,
            threshold=threshold,
            random_temporal_gap=random_gap,
            config=config,
        )
        if model_name == config.baseline_model_name:
            eligibility_status = "descriptive_only"
        elif not rejection_reasons:
            eligibility_status = "candidate_for_further_validation"
        elif temporal["supported_fold_count"] > 0 or _has_any_signal(temporal, threshold):
            eligibility_status = "diagnostic_only"
        else:
            eligibility_status = "descriptive_only"
        rows.append(
            {
                "case_study_version": config.case_study_version,
                "source_artifact": config.source_artifact,
                "source_sha256": config.source_sha256,
                "model_name": model_name,
                "temporal_median_pr_auc": temporal["temporal_median_pr_auc"],
                "temporal_min_pr_auc": temporal["temporal_min_pr_auc"],
                "temporal_max_pr_auc": temporal["temporal_max_pr_auc"],
                "temporal_iqr_pr_auc": temporal["temporal_iqr_pr_auc"],
                "final_holdout_pr_auc": temporal["final_holdout_pr_auc"],
                "random_reference_pr_auc": _model_summary_value(
                    summary,
                    model_name,
                    "random_reference_pr_auc",
                ),
                "dummy_temporal_pr_auc": dummy_temporal,
                "prevalence_baseline": config.prevalence_baseline,
                "temporal_lift_over_prevalence": temporal["temporal_lift_over_prevalence"],
                "final_lift_over_prevalence": temporal["final_lift_over_prevalence"],
                "random_temporal_gap": random_gap,
                "threshold_recall": threshold["recall"],
                "threshold_precision": threshold["precision"],
                "threshold_mcc": threshold["mcc"],
                "brier_score": brier_score,
                "fold_count": temporal["fold_count"],
                "supported_fold_count": temporal["supported_fold_count"],
                "convergence_status": _convergence_status(metrics, model_name),
                "eligibility_status": eligibility_status,
                "representative_model_selected": False,
                "rejection_reasons": "; ".join(rejection_reasons)
                if rejection_reasons
                else "passes_predeclared_candidate_gate_but_not_auto_selected",
            }
        )
    return pd.DataFrame(rows)


def build_operational_boundary(
    *,
    threshold_summary: pd.DataFrame,
    error_structure: pd.DataFrame,
    config: ClassificationTrustConfig,
) -> pd.DataFrame:
    """Summarize threshold, calibration, SPC, and deployment boundaries."""
    temporal = threshold_summary[
        threshold_summary["validation_type"].eq("primary_temporal")
        & threshold_summary["status"].eq("valid")
    ]
    rows: list[dict[str, Any]] = []
    for model_name in sorted(temporal["model_name"].dropna().unique()):
        model_rows = temporal[temporal["model_name"].eq(model_name)]
        predicted_positive = pd.to_numeric(
            model_rows["true_positive"],
            errors="coerce",
        ) + pd.to_numeric(model_rows["false_positive"], errors="coerce")
        rows.append(
            {
                "case_study_version": config.case_study_version,
                "boundary_type": "fixed_threshold_0_5",
                "model_name": model_name,
                "predicted_positive_count_median": float(predicted_positive.median()),
                "recall_median": _median(model_rows, "recall"),
                "precision_median": _median(model_rows, "precision"),
                "specificity_median": _median(model_rows, "specificity"),
                "negative_predictive_value_median": _median(
                    model_rows,
                    "negative_predictive_value",
                ),
                "f1_median": _median(model_rows, "f1"),
                "mcc_median": _median(model_rows, "mcc"),
                "false_negative_count_median": _median(model_rows, "false_negative"),
                "false_positive_count_median": _median(model_rows, "false_positive"),
                "status": "risk_ranking_diagnostic_only",
                "decision": "not_valid_for_binary_failure_decision_or_production_alert",
            }
        )
    rows.extend(
        [
            _boundary_row(
                config,
                "calibration",
                "all_models",
                "uncalibrated_score_only",
                "No calibration model or independent calibration set is available; Brier/log-loss are diagnostic only.",
            ),
            _boundary_row(
                config,
                "applicability",
                "all_models",
                "same_dataset_retrospective_only",
                "No equipment, lot, product, recipe, or external fab holdout supports broader generalization.",
            ),
            _boundary_row(
                config,
                "spc_i_mr",
                "all_models",
                "conditional_exploratory_only",
                "I-MR would require justified stable baseline selection; no chart is generated in v1.4.5.",
            ),
            _boundary_row(
                config,
                "xbar_r_or_xbar_s",
                "all_models",
                "not_ready_no_rational_subgroup",
                "SECOM lacks rational subgroup identifiers.",
            ),
            _boundary_row(
                config,
                "p_np",
                "all_models",
                "conditional_chronological_aggregation_required",
                "Aggregation would need a justified time unit and is not implemented here.",
            ),
            _boundary_row(
                config,
                "capability_indices",
                "all_models",
                "not_ready_no_specification_limits",
                "Cp/Cpk/Pp/Ppk are not computed because specification limits are absent.",
            ),
            _boundary_row(
                config,
                "drift_model",
                "all_models",
                "deferred",
                "Temporal variation is observed, but predictive evidence and group semantics are insufficient for a drift model.",
            ),
            _boundary_row(
                config,
                "anomaly_model",
                "all_models",
                "deferred",
                "No anomaly model is added without stable baseline and operational context.",
            ),
            _boundary_row(
                config,
                "explainability",
                "all_models",
                "shap_deferred_not_justified",
                "No representative model exists and features are anonymized.",
            ),
        ]
    )
    if not error_structure.empty:
        rows.append(
            {
                "case_study_version": config.case_study_version,
                "boundary_type": "error_structure",
                "model_name": "all_models",
                "predicted_positive_count_median": np.nan,
                "recall_median": np.nan,
                "precision_median": np.nan,
                "specificity_median": np.nan,
                "negative_predictive_value_median": np.nan,
                "f1_median": np.nan,
                "mcc_median": np.nan,
                "false_negative_count_median": np.nan,
                "false_positive_count_median": np.nan,
                "status": "descriptive_summary_available",
                "decision": "Error structure can describe false positives/negatives by time and missingness, not root cause.",
            }
        )
    return pd.DataFrame(rows)


def build_claim_boundary(
    eligibility: pd.DataFrame,
    config: ClassificationTrustConfig,
) -> pd.DataFrame:
    """Build allowed and prohibited claim rows."""
    any_candidate = eligibility["eligibility_status"].eq("candidate_for_further_validation").any()
    rows = [
        _claim(
            config,
            "offline retrospective diagnostic comparison",
            "allowed",
            "Chronological validation artifacts exist and use train-only preprocessing.",
        ),
        _claim(
            config,
            "random split as optimistic reference",
            "allowed",
            "Random-reference rows are labeled secondary and not primary evidence.",
        ),
        _claim(
            config,
            "no representative production model selected",
            "allowed",
            "No non-dummy model passes the predeclared candidate gate.",
        ),
        _claim(
            config,
            "accurate failure prediction",
            "prohibited",
            "Temporal PR-AUC is close to prevalence and all non-dummy models remain diagnostic_only.",
        ),
        _claim(
            config,
            "production-ready model",
            "prohibited",
            "The model-status vocabulary has no production_ready state.",
        ),
        _claim(
            config,
            "calibrated probability",
            "prohibited",
            "No calibration model or independent calibration set is used.",
        ),
        _claim(
            config,
            "causal root cause",
            "prohibited",
            "Features are anonymized and validation is predictive/diagnostic only.",
        ),
        _claim(
            config,
            "equipment lot product generalization",
            "prohibited",
            "SECOM lacks explicit equipment, lot, product, and recipe identifiers.",
        ),
        _claim(
            config,
            "real-time monitoring solution",
            "prohibited",
            "The workflow is offline and retrospective.",
        ),
        _claim(
            config,
            "process optimization achieved",
            "prohibited",
            "No intervention, optimization, or causal evidence is present.",
        ),
    ]
    if any_candidate:
        rows.append(
            _claim(
                config,
                "candidate for further validation",
                "conditional",
                "At least one model passes the candidate gate, but no automatic deployment claim follows.",
            )
        )
    return pd.DataFrame(rows)


def build_trust_summary(
    *,
    eligibility: pd.DataFrame,
    temporal_stability: pd.DataFrame,
    random_temporal_gap: pd.DataFrame,
    threshold_summary: pd.DataFrame,
    split_diagnostics: pd.DataFrame,
    classification_conclusion: pd.DataFrame,
    config: ClassificationTrustConfig,
) -> pd.DataFrame:
    """Build a compact closeout trust summary."""
    non_dummy = eligibility[~eligibility["model_name"].eq(config.baseline_model_name)]
    selected_count = int(eligibility["representative_model_selected"].astype(bool).sum())
    temporal_splits = split_diagnostics[split_diagnostics["validation_type"].eq("primary_temporal")]
    best_temporal = _max_or_nan(non_dummy["temporal_median_pr_auc"])
    best_final = _max_or_nan(non_dummy["final_holdout_pr_auc"])
    best_random = _max_or_nan(non_dummy["random_reference_pr_auc"])
    best_status = (
        non_dummy.sort_values("temporal_median_pr_auc", ascending=False).iloc[0][
            "eligibility_status"
        ]
        if not non_dummy.empty
        else "descriptive_only"
    )
    rows = [
        ("audit_verdict", "passed", "All required compact v1.4.4 artifacts were available."),
        (
            "prevalence_baseline",
            _fmt(config.prevalence_baseline),
            f"{config.global_failure_count}/{config.global_row_count} failures.",
        ),
        (
            "primary_validation",
            "chronological_time_aware",
            f"Primary temporal split count: {len(temporal_splits)}.",
        ),
        (
            "best_temporal_median_pr_auc",
            _fmt(best_temporal),
            "Best non-dummy median over primary temporal folds.",
        ),
        (
            "best_final_holdout_pr_auc",
            _fmt(best_final),
            "Best non-dummy final chronological holdout PR-AUC.",
        ),
        (
            "best_random_reference_pr_auc",
            _fmt(best_random),
            "Random split is optimistic reference only.",
        ),
        (
            "representative_model_selected",
            "false" if selected_count == 0 else "true",
            "Strict candidate and trust rules do not select a representative model.",
        ),
        (
            "strongest_model_status",
            str(best_status),
            "Status is based on predeclared eligibility rules.",
        ),
        (
            "threshold_boundary",
            "not_valid_for_binary_failure_decision",
            "0.5 threshold results are diagnostic and not tuned with test labels.",
        ),
        (
            "calibration_boundary",
            "uncalibrated_score_only",
            "Brier/log-loss are diagnostic; calibrated probability is not claimed.",
        ),
        (
            "random_temporal_interpretation",
            _overall_random_temporal_status(random_temporal_gap),
            "Random-reference performance does not establish robust temporal generalization.",
        ),
        (
            "group_generalization",
            "unavailable",
            "No explicit equipment, lot, product, or recipe identifiers exist.",
        ),
        (
            "spc_capability",
            "capability_not_ready",
            "Specification limits and rational subgroups are absent.",
        ),
        (
            "shap_decision",
            "deferred_not_justified",
            "No representative model exists and feature semantics are anonymized.",
        ),
        (
            "drift_anomaly_decision",
            "deferred",
            "Temporal variation exists, but a drift/anomaly model is not justified in v1.4.",
        ),
        (
            "classification_conclusion_source",
            str(classification_conclusion.shape[0]),
            "Rows from v1.4.4 classification conclusion were read without refitting.",
        ),
    ]
    return pd.DataFrame(rows, columns=["field", "value", "evidence"])


def build_closeout_conclusion(
    eligibility: pd.DataFrame,
    trust_summary: pd.DataFrame,
    config: ClassificationTrustConfig,
) -> pd.DataFrame:
    """Build final release-readiness and next-step conclusion rows."""
    non_dummy = eligibility[~eligibility["model_name"].eq(config.baseline_model_name)]
    all_diagnostic = bool(non_dummy["eligibility_status"].eq("diagnostic_only").all())
    release_readiness = "release_ready" if all_diagnostic else "conditional"
    rows = [
        (
            "v1_4_release_readiness",
            release_readiness,
            "The case study is complete as a trust-boundary demonstration with weak/diagnostic modeling results preserved.",
        ),
        (
            "representative_model",
            "none",
            "No model satisfies the predeclared trust gate.",
        ),
        (
            "allowed_use",
            "retrospective_offline_diagnostic_framework",
            "Use results to demonstrate time-aware validation and trust-boundary reporting.",
        ),
        (
            "not_allowed_use",
            "production_decision_or_calibrated_failure_probability",
            "Evidence is insufficient for deployment, root-cause, or calibrated probability claims.",
        ),
        (
            "future_data_requirements",
            "equipment_lot_product_recipe_ids_spec_limits_more_failures_external_holdout",
            "Additional data structure is more important than tuning current models.",
        ),
        (
            "recommended_next_phase",
            "v1_5_generic_reliability_or_v1_4_docs_closeout",
            "Avoid SHAP, drift models, or further tuning until stronger data support exists.",
        ),
    ]
    return pd.DataFrame(rows, columns=["field", "value", "evidence"])


def _eligibility_rejection_reasons(
    *,
    model_name: str,
    temporal: pd.Series,
    threshold: dict[str, float],
    random_temporal_gap: float,
    config: ClassificationTrustConfig,
) -> list[str]:
    if model_name == config.baseline_model_name:
        return ["baseline_model_not_candidate"]
    reasons = []
    if temporal["supported_fold_count"] < config.min_supported_fold_count:
        reasons.append("insufficient_supported_temporal_folds")
    if temporal["temporal_lift_over_prevalence"] < config.min_temporal_pr_auc_lift_over_prevalence:
        reasons.append("temporal_pr_auc_lift_over_prevalence_too_small")
    if temporal["final_lift_over_prevalence"] < config.min_final_pr_auc_lift_over_prevalence:
        reasons.append("final_holdout_lift_over_prevalence_too_small")
    if temporal["positive_lift_fold_rate"] < config.min_temporal_dummy_lift_fold_rate:
        reasons.append("not_enough_temporal_folds_above_dummy")
    if temporal["temporal_iqr_pr_auc"] > config.max_temporal_iqr_pr_auc:
        reasons.append("temporal_pr_auc_variation_too_high")
    if pd.notna(random_temporal_gap) and random_temporal_gap > config.max_random_temporal_pr_auc_gap:
        reasons.append("random_temporal_gap_too_large")
    if pd.isna(threshold["recall"]) or threshold["recall"] < config.min_threshold_recall:
        reasons.append("threshold_recall_too_low")
    if pd.isna(threshold["precision"]) or threshold["precision"] < config.min_threshold_precision:
        reasons.append("threshold_precision_too_low")
    return reasons


def _threshold_medians(threshold_summary: pd.DataFrame, model_name: str) -> dict[str, float]:
    rows = threshold_summary[
        threshold_summary["validation_type"].eq("primary_temporal")
        & threshold_summary["model_name"].eq(model_name)
        & threshold_summary["status"].eq("valid")
    ]
    return {
        "recall": _median(rows, "recall"),
        "precision": _median(rows, "precision"),
        "mcc": _median(rows, "mcc"),
    }


def _primary_metric_median(metrics: pd.DataFrame, model_name: str, metric: str) -> float:
    rows = metrics[
        metrics["validation_type"].eq("primary_temporal")
        & metrics["model_name"].eq(model_name)
        & metrics["status"].eq("valid")
    ]
    return _median(rows, metric)


def _gap_value(random_temporal_gap: pd.DataFrame, model_name: str, metric: str) -> float:
    subset = random_temporal_gap[
        random_temporal_gap["model_name"].eq(model_name)
        & random_temporal_gap["metric"].eq(metric)
    ]
    if subset.empty:
        return np.nan
    return float(pd.to_numeric(subset["random_minus_temporal_gap"], errors="coerce").iloc[0])


def _convergence_status(metrics: pd.DataFrame, model_name: str) -> str:
    rows = metrics[metrics["model_name"].eq(model_name)]
    invalid = rows[~rows["status"].eq("valid")]
    if invalid.empty:
        return "valid"
    return "invalid_rows:" + "|".join(sorted(invalid["invalid_reason"].dropna().astype(str).unique()))


def _has_any_signal(temporal: pd.Series, threshold: dict[str, float]) -> bool:
    values = [
        temporal.get("temporal_lift_over_prevalence", np.nan),
        temporal.get("final_lift_over_prevalence", np.nan),
        threshold.get("recall", np.nan),
        threshold.get("precision", np.nan),
    ]
    return any(pd.notna(value) and value > 0 for value in values)


def _boundary_row(
    config: ClassificationTrustConfig,
    boundary_type: str,
    model_name: str,
    status: str,
    decision: str,
) -> dict[str, Any]:
    return {
        "case_study_version": config.case_study_version,
        "boundary_type": boundary_type,
        "model_name": model_name,
        "predicted_positive_count_median": np.nan,
        "recall_median": np.nan,
        "precision_median": np.nan,
        "specificity_median": np.nan,
        "negative_predictive_value_median": np.nan,
        "f1_median": np.nan,
        "mcc_median": np.nan,
        "false_negative_count_median": np.nan,
        "false_positive_count_median": np.nan,
        "status": status,
        "decision": decision,
    }


def _claim(
    config: ClassificationTrustConfig,
    claim: str,
    status: str,
    evidence: str,
) -> dict[str, Any]:
    return {
        "case_study_version": config.case_study_version,
        "claim": claim,
        "status": status,
        "evidence": evidence,
    }


def _model_summary_value(summary: pd.DataFrame, model_name: str, column: str) -> float:
    if summary.empty or model_name not in summary.index or column not in summary.columns:
        return np.nan
    return float(pd.to_numeric(pd.Series([summary.loc[model_name, column]]), errors="coerce").iloc[0])


def _overall_random_temporal_status(random_temporal_gap: pd.DataFrame) -> str:
    pr_auc = random_temporal_gap[random_temporal_gap["metric"].eq("average_precision")]
    gaps = pd.to_numeric(pr_auc["random_minus_temporal_gap"], errors="coerce").dropna()
    if gaps.empty:
        return "inconclusive"
    if (gaps > 0.05).any():
        return "random_optimistic"
    if (gaps.abs() <= 0.03).all():
        return "random_consistent_with_temporal"
    return "temporal_unstable"


def _stability_note(values: pd.Series, final_value: float, median_value: float) -> str:
    if values.empty:
        return "no_valid_temporal_metric"
    if pd.notna(final_value) and pd.notna(median_value) and final_value > median_value:
        return "final_holdout_above_median_but_not_robust_alone"
    if _iqr(values) > 0.08:
        return "high_temporal_variation"
    return "compact_temporal_summary"


def _mean(values: pd.Series) -> float:
    return float(values.mean()) if len(values) else np.nan


def _median(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return np.nan
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    return float(values.median()) if len(values) else np.nan


def _min(values: pd.Series) -> float:
    return float(values.min()) if len(values) else np.nan


def _max(values: pd.Series) -> float:
    return float(values.max()) if len(values) else np.nan


def _std(values: pd.Series) -> float:
    return float(values.std(ddof=0)) if len(values) else np.nan


def _iqr(values: pd.Series) -> float:
    return float(values.quantile(0.75) - values.quantile(0.25)) if len(values) else np.nan


def _cv(values: pd.Series) -> float:
    median = float(values.median()) if len(values) else np.nan
    if pd.isna(median) or median == 0:
        return np.nan
    return float(values.std(ddof=0) / abs(median))


def _subtract_or_nan(left: float, right: float) -> float:
    if pd.isna(left) or pd.isna(right):
        return np.nan
    return float(left - right)


def _max_or_nan(values: pd.Series) -> float:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    return float(numeric.max()) if len(numeric) else np.nan


def _fmt(value: float) -> str:
    return "nan" if pd.isna(value) else f"{float(value):.6g}"
