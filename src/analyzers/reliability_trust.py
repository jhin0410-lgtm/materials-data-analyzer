"""Reliability trust-boundary aggregation from compact validation artifacts.

This module reads existing compact reliability classification outputs and
derives model eligibility, validation stability, operational boundaries, and
claim boundaries. It does not fit models, tune thresholds, generate features,
call networks, or read raw row-level prediction files.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PRIMARY_VALIDATION_TYPES = {
    "primary_asset_disjoint",
    "primary_time_aware",
    "primary_combined_asset_time",
}
COMBINED_VALIDATION_TYPE = "primary_combined_asset_time"
RANDOM_VALIDATION_TYPE = "optimistic_random_reference"
COMBINED_SPLIT_ID = "combined_asset_disjoint_future_holdout"


@dataclass(frozen=True)
class ReliabilityTrustConfig:
    """Configuration for reliability closeout rules."""

    case_study_version: str
    source_artifact: str
    source_sha256: str
    baseline_model_name: str
    eligible_origins: int
    positive_rows: int
    positive_assets: int
    total_assets: int
    top_risk_reference_fraction: float = 0.01
    min_candidate_combined_lift_over_prevalence: float = 0.02
    min_candidate_top_1_lift: float = 5.0
    min_candidate_top_1_failed_asset_capture: float = 0.20

    @property
    def row_prevalence(self) -> float:
        """Return the global row-level prevalence for the fixed 7-day task."""
        return self.positive_rows / self.eligible_origins if self.eligible_origins else np.nan

    @property
    def positive_asset_prevalence(self) -> float:
        """Return the positive asset prevalence among all assets."""
        return self.positive_assets / self.total_assets if self.total_assets else np.nan


def calculate_file_sha256(path: str | Path) -> str:
    """Calculate SHA-256 for an existing file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_reliability_trust_outputs(
    *,
    metrics: pd.DataFrame,
    split_diagnostics: pd.DataFrame,
    model_summary: pd.DataFrame,
    top_risk_summary: pd.DataFrame,
    threshold_summary: pd.DataFrame,
    error_structure_summary: pd.DataFrame,
    classification_conclusion: pd.DataFrame,
    full_readiness_summary: pd.DataFrame,
    event_integrity_summary: pd.DataFrame,
    censoring_summary: pd.DataFrame,
    config: ReliabilityTrustConfig,
) -> dict[str, pd.DataFrame]:
    """Build all v1.5.5 reliability trust-boundary tables."""
    validate_input_schemas(
        metrics=metrics,
        split_diagnostics=split_diagnostics,
        model_summary=model_summary,
        top_risk_summary=top_risk_summary,
        threshold_summary=threshold_summary,
    )
    stability = build_validation_stability_summary(metrics, model_summary, config)
    weighting = build_weighting_dependency_summary(model_summary, top_risk_summary, config)
    resource = build_resource_boundary(metrics, model_summary, config)
    eligibility = build_model_eligibility(
        metrics=metrics,
        model_summary=model_summary,
        top_risk_summary=top_risk_summary,
        threshold_summary=threshold_summary,
        validation_stability=stability,
        weighting_dependency=weighting,
        config=config,
    )
    operational = build_operational_boundary(
        metrics=metrics,
        top_risk_summary=top_risk_summary,
        threshold_summary=threshold_summary,
        error_structure_summary=error_structure_summary,
        config=config,
    )
    claims = build_claim_boundary(eligibility, config)
    trust = build_trust_summary(
        eligibility=eligibility,
        validation_stability=stability,
        weighting_dependency=weighting,
        operational_boundary=operational,
        split_diagnostics=split_diagnostics,
        classification_conclusion=classification_conclusion,
        full_readiness_summary=full_readiness_summary,
        event_integrity_summary=event_integrity_summary,
        censoring_summary=censoring_summary,
        config=config,
    )
    closeout = build_closeout_conclusion(trust, eligibility, config)
    return {
        "model_eligibility": eligibility,
        "validation_stability_summary": stability,
        "weighting_dependency_summary": weighting,
        "resource_boundary": resource,
        "operational_boundary": operational,
        "claim_boundary": claims,
        "trust_summary": trust,
        "closeout_conclusion": closeout,
    }


def validate_input_schemas(
    *,
    metrics: pd.DataFrame,
    split_diagnostics: pd.DataFrame,
    model_summary: pd.DataFrame,
    top_risk_summary: pd.DataFrame,
    threshold_summary: pd.DataFrame,
) -> None:
    """Validate required compact input schemas."""
    required: list[tuple[str, pd.DataFrame, set[str]]] = [
        (
            "classification_metrics",
            metrics,
            {
                "split_id",
                "validation_type",
                "model_name",
                "feature_set",
                "weighting_policy",
                "average_precision",
                "roc_auc",
                "brier_score",
                "fit_train_rows",
                "fit_train_assets",
                "fit_train_positives",
                "training_subsample_status",
                "status",
            },
        ),
        (
            "split_diagnostics",
            split_diagnostics,
            {
                "split_id",
                "split_type",
                "train_rows",
                "test_rows",
                "asset_overlap_count",
                "temporal_overlap",
                "leakage_status",
            },
        ),
        (
            "classification_model_summary",
            model_summary,
            {
                "model_name",
                "feature_set",
                "weighting_policy",
                "model_status",
                "primary_median_pr_auc",
                "combined_pr_auc",
                "random_reference_pr_auc",
                "dummy_primary_median_pr_auc",
                "resource_status",
            },
        ),
        (
            "top_risk_summary",
            top_risk_summary,
            {
                "split_id",
                "model_name",
                "feature_set",
                "weighting_policy",
                "top_fraction",
                "top_n",
                "positive_rows_in_top",
                "precision_at_top_fraction",
                "lift_over_prevalence",
                "failed_asset_capture_rate",
            },
        ),
        (
            "threshold_summary",
            threshold_summary,
            {
                "split_id",
                "model_name",
                "feature_set",
                "weighting_policy",
                "threshold",
                "false_positive",
                "false_negative",
                "true_positive",
                "precision",
                "recall",
                "mcc",
                "status",
            },
        ),
    ]
    for name, frame, columns in required:
        missing = sorted(columns - set(frame.columns))
        if missing:
            raise ValueError(f"Missing {name} column(s): " + ", ".join(missing))


def build_model_eligibility(
    *,
    metrics: pd.DataFrame,
    model_summary: pd.DataFrame,
    top_risk_summary: pd.DataFrame,
    threshold_summary: pd.DataFrame,
    validation_stability: pd.DataFrame,
    weighting_dependency: pd.DataFrame,
    config: ReliabilityTrustConfig,
) -> pd.DataFrame:
    """Build model x feature-set x weighting eligibility rows."""
    rows: list[dict[str, Any]] = []
    for _, summary in _sort_combo_rows(model_summary).iterrows():
        combo = _combo(summary)
        combo_metrics = _combo_filter(metrics, combo)
        primary = combo_metrics[combo_metrics["validation_type"].isin(PRIMARY_VALIDATION_TYPES)]
        top = _combined_top_risk(top_risk_summary, combo, config.top_risk_reference_fraction)
        threshold = _threshold_primary_median(threshold_summary, combo)
        stability = _lookup_combo(validation_stability, combo)
        weighting = _lookup_weighting_gap(weighting_dependency, combo)
        rejection_reasons = _eligibility_rejection_reasons(
            summary=summary,
            top=top,
            threshold=threshold,
            config=config,
        )
        eligibility_status = _eligibility_status(
            model_name=str(summary["model_name"]),
            rejection_reasons=rejection_reasons,
            top=top,
            summary=summary,
            config=config,
        )
        rows.append(
            {
                "case_study_version": config.case_study_version,
                "source_artifact": config.source_artifact,
                "source_sha256": config.source_sha256,
                "model_name": combo["model_name"],
                "feature_set": combo["feature_set"],
                "weighting_policy": combo["weighting_policy"],
                "input_model_status": summary["model_status"],
                "primary_median_pr_auc": _num(summary, "primary_median_pr_auc"),
                "primary_min_pr_auc": _num(stability, "primary_min_pr_auc"),
                "primary_max_pr_auc": _num(stability, "primary_max_pr_auc"),
                "primary_iqr_pr_auc": _num(stability, "primary_iqr_pr_auc"),
                "asset_disjoint_pr_auc": _split_metric(combo_metrics, "primary_asset_disjoint"),
                "time_aware_pr_auc": _split_metric(combo_metrics, "primary_time_aware"),
                "combined_pr_auc": _split_metric(combo_metrics, COMBINED_VALIDATION_TYPE),
                "random_reference_pr_auc": _split_metric(combo_metrics, RANDOM_VALIDATION_TYPE),
                "dummy_pr_auc": _num(summary, "dummy_primary_median_pr_auc"),
                "prevalence_baseline": config.row_prevalence,
                "lift_over_prevalence_abs": _num(summary, "primary_median_pr_auc")
                - config.row_prevalence,
                "lift_over_prevalence_ratio": _safe_ratio(
                    _num(summary, "primary_median_pr_auc"),
                    config.row_prevalence,
                ),
                "random_primary_gap": _num(summary, "random_primary_pr_auc_gap"),
                "top_0_1_precision": _top_precision(
                    top_risk_summary,
                    combo,
                    0.001,
                ),
                "top_0_5_precision": _top_precision(
                    top_risk_summary,
                    combo,
                    0.005,
                ),
                "top_1_precision": _num(top, "precision_at_top_fraction"),
                "top_5_precision": _top_precision(
                    top_risk_summary,
                    combo,
                    0.05,
                ),
                "top_1_lift": _num(top, "lift_over_prevalence"),
                "top_1_failed_asset_capture": _num(top, "failed_asset_capture_rate"),
                "threshold_0_5_precision": threshold["precision"],
                "threshold_0_5_recall": threshold["recall"],
                "threshold_0_5_mcc": threshold["mcc"],
                "brier_score": _median(primary, "brier_score"),
                "training_row_count": _median(primary, "fit_train_rows"),
                "training_asset_count": _median(primary, "fit_train_assets"),
                "training_positive_count": _median(primary, "fit_train_positives"),
                "training_subsample_status": _combine_status(primary, "training_subsample_status"),
                "resource_status": summary["resource_status"],
                "weighting_dependency_status": weighting,
                "repeated_origin_dependency": "high_repeated_origin_dependency",
                "eligibility_status": eligibility_status,
                "representative_model_selected": False,
                "rejection_reasons": "; ".join(rejection_reasons),
            }
        )
    return pd.DataFrame(rows)


def build_validation_stability_summary(
    metrics: pd.DataFrame,
    model_summary: pd.DataFrame,
    config: ReliabilityTrustConfig,
) -> pd.DataFrame:
    """Summarize asset/time/combined/random stability by combo."""
    rows: list[dict[str, Any]] = []
    for _, summary in _sort_combo_rows(model_summary).iterrows():
        combo = _combo(summary)
        combo_metrics = _combo_filter(metrics, combo)
        primary = combo_metrics[combo_metrics["validation_type"].isin(PRIMARY_VALIDATION_TYPES)]
        pr_values = _numeric(primary, "average_precision")
        random_pr = _split_metric(combo_metrics, RANDOM_VALIDATION_TYPE)
        primary_median = _median(primary, "average_precision")
        combined = _split_metric(combo_metrics, COMBINED_VALIDATION_TYPE)
        rows.append(
            {
                "case_study_version": config.case_study_version,
                "source_artifact": config.source_artifact,
                "source_sha256": config.source_sha256,
                "model_name": combo["model_name"],
                "feature_set": combo["feature_set"],
                "weighting_policy": combo["weighting_policy"],
                "asset_disjoint_pr_auc": _split_metric(combo_metrics, "primary_asset_disjoint"),
                "time_aware_pr_auc": _split_metric(combo_metrics, "primary_time_aware"),
                "combined_pr_auc": combined,
                "random_reference_pr_auc": random_pr,
                "primary_median_pr_auc": primary_median,
                "primary_min_pr_auc": float(pr_values.min()) if len(pr_values) else np.nan,
                "primary_max_pr_auc": float(pr_values.max()) if len(pr_values) else np.nan,
                "primary_iqr_pr_auc": _iqr(pr_values),
                "random_minus_primary_median_pr_auc": _subtract_or_nan(random_pr, primary_median),
                "combined_minus_primary_median_pr_auc": _subtract_or_nan(combined, primary_median),
                "stability_status": _stability_status(pr_values, random_pr, primary_median),
                "interpretation": _stability_interpretation(pr_values, random_pr, primary_median),
            }
        )
    return pd.DataFrame(rows)


def build_weighting_dependency_summary(
    model_summary: pd.DataFrame,
    top_risk_summary: pd.DataFrame,
    config: ReliabilityTrustConfig,
) -> pd.DataFrame:
    """Compare asset-balanced and raw-row results for each model/feature set."""
    rows: list[dict[str, Any]] = []
    pairs = model_summary[["model_name", "feature_set"]].drop_duplicates()
    for _, pair in pairs.sort_values(["model_name", "feature_set"]).iterrows():
        model_name = str(pair["model_name"])
        feature_set = str(pair["feature_set"])
        asset = _summary_row(model_summary, model_name, feature_set, "asset_balanced")
        raw = _summary_row(model_summary, model_name, feature_set, "raw_row")
        if asset.empty or raw.empty:
            continue
        asset_combo = {
            "model_name": model_name,
            "feature_set": feature_set,
            "weighting_policy": "asset_balanced",
        }
        raw_combo = {
            "model_name": model_name,
            "feature_set": feature_set,
            "weighting_policy": "raw_row",
        }
        asset_top = _combined_top_risk(top_risk_summary, asset_combo, 0.01)
        raw_top = _combined_top_risk(top_risk_summary, raw_combo, 0.01)
        primary_gap = _num(raw.iloc[0], "primary_median_pr_auc") - _num(
            asset.iloc[0],
            "primary_median_pr_auc",
        )
        combined_gap = _num(raw.iloc[0], "combined_pr_auc") - _num(
            asset.iloc[0],
            "combined_pr_auc",
        )
        top_gap = _num(raw_top, "precision_at_top_fraction") - _num(
            asset_top,
            "precision_at_top_fraction",
        )
        rows.append(
            {
                "case_study_version": config.case_study_version,
                "source_artifact": config.source_artifact,
                "source_sha256": config.source_sha256,
                "model_name": model_name,
                "feature_set": feature_set,
                "asset_balanced_primary_median_pr_auc": _num(
                    asset.iloc[0],
                    "primary_median_pr_auc",
                ),
                "raw_row_primary_median_pr_auc": _num(raw.iloc[0], "primary_median_pr_auc"),
                "raw_minus_asset_primary_median_pr_auc": primary_gap,
                "asset_balanced_combined_pr_auc": _num(asset.iloc[0], "combined_pr_auc"),
                "raw_row_combined_pr_auc": _num(raw.iloc[0], "combined_pr_auc"),
                "raw_minus_asset_combined_pr_auc": combined_gap,
                "asset_balanced_top_1_precision": _num(asset_top, "precision_at_top_fraction"),
                "raw_row_top_1_precision": _num(raw_top, "precision_at_top_fraction"),
                "raw_minus_asset_top_1_precision": top_gap,
                "dependency_status": _weighting_dependency_status(
                    primary_gap,
                    combined_gap,
                    top_gap,
                ),
                "interpretation": "Daily origins from the same asset are dependent; raw-row gains can reflect long-lived asset dominance.",
            }
        )
    return pd.DataFrame(rows)


def build_resource_boundary(
    metrics: pd.DataFrame,
    model_summary: pd.DataFrame,
    config: ReliabilityTrustConfig,
) -> pd.DataFrame:
    """Summarize training resource and subsampling boundaries."""
    rows: list[dict[str, Any]] = []
    for _, summary in _sort_combo_rows(model_summary).iterrows():
        combo = _combo(summary)
        primary = _combo_filter(metrics, combo)
        primary = primary[primary["validation_type"].isin(PRIMARY_VALIDATION_TYPES)]
        resource_status = str(summary["resource_status"])
        rows.append(
            {
                "case_study_version": config.case_study_version,
                "source_artifact": config.source_artifact,
                "source_sha256": config.source_sha256,
                "model_name": combo["model_name"],
                "feature_set": combo["feature_set"],
                "weighting_policy": combo["weighting_policy"],
                "resource_status": resource_status,
                "training_subsample_status": _combine_status(
                    primary,
                    "training_subsample_status",
                ),
                "fit_train_rows_median": _median(primary, "fit_train_rows"),
                "fit_train_assets_median": _median(primary, "fit_train_assets"),
                "fit_train_positives_median": _median(primary, "fit_train_positives"),
                "test_set_subsampled_any": bool(
                    primary["test_set_subsampled"].astype(str).str.lower().eq("true").any()
                )
                if "test_set_subsampled" in primary.columns
                else False,
                "boundary_status": "not_full_data_evidence"
                if "resource_limited" in resource_status
                else "full_training_or_baseline",
                "decision": "Do not treat resource-limited subsampled training as production-grade full-data validation.",
            }
        )
    return pd.DataFrame(rows)


def build_operational_boundary(
    *,
    metrics: pd.DataFrame,
    top_risk_summary: pd.DataFrame,
    threshold_summary: pd.DataFrame,
    error_structure_summary: pd.DataFrame,
    config: ReliabilityTrustConfig,
) -> pd.DataFrame:
    """Build top-risk, threshold, calibration, and task-boundary rows."""
    rows: list[dict[str, Any]] = []
    for _, top in _combined_top_rows(top_risk_summary, 0.01).iterrows():
        top_n = _num(top, "top_n")
        positives = _num(top, "positive_rows_in_top")
        rows.append(
            {
                "case_study_version": config.case_study_version,
                "source_artifact": config.source_artifact,
                "source_sha256": config.source_sha256,
                "boundary_type": "combined_top_1_percent_ranking",
                "model_name": top["model_name"],
                "feature_set": top["feature_set"],
                "weighting_policy": top["weighting_policy"],
                "alerted_row_count": top_n,
                "positive_rows_in_alerted": positives,
                "false_positive_row_burden": max(top_n - positives, 0),
                "precision": _num(top, "precision_at_top_fraction"),
                "recall": np.nan,
                "mcc": np.nan,
                "lift": _num(top, "lift_over_prevalence"),
                "failed_asset_capture": _num(top, "failed_asset_capture_rate"),
                "status": "offline_ranking_diagnostic",
                "decision": "Top-risk concentration can prioritize retrospective inspection, not production alerts.",
            }
        )
    for _, thresh in _combined_threshold_rows(threshold_summary).iterrows():
        predicted_positive = _num(thresh, "true_positive") + _num(thresh, "false_positive")
        rows.append(
            {
                "case_study_version": config.case_study_version,
                "source_artifact": config.source_artifact,
                "source_sha256": config.source_sha256,
                "boundary_type": "fixed_threshold_0_5",
                "model_name": thresh["model_name"],
                "feature_set": thresh["feature_set"],
                "weighting_policy": thresh["weighting_policy"],
                "alerted_row_count": predicted_positive,
                "positive_rows_in_alerted": _num(thresh, "true_positive"),
                "false_positive_row_burden": _num(thresh, "false_positive"),
                "precision": _num(thresh, "precision"),
                "recall": _num(thresh, "recall"),
                "mcc": _num(thresh, "mcc"),
                "lift": _safe_ratio(_num(thresh, "precision"), config.row_prevalence),
                "failed_asset_capture": np.nan,
                "status": _threshold_status(thresh),
                "decision": "0.5 threshold was predeclared and is not tuned for operational alerting.",
            }
        )
    rows.extend(
        [
            _boundary_row(config, "calibration", "all_models", "all", "all", "uncalibrated_score_only", "Brier/log-loss are diagnostic; no calibrated probability claim is allowed."),
            _boundary_row(config, "survival_model", "all_models", "all", "all", "deferred_not_ready", "Censoring and exit reasons are uncertain; no survival model is fit."),
            _boundary_row(config, "rul_model", "all_models", "all", "all", "deferred_not_ready", "RUL targets are not constructed or modeled in v1.5."),
            _boundary_row(config, "recurrent_event_model", "all_models", "all", "all", "not_ready", "Repeated failure events are not established as recurrent events."),
            _boundary_row(config, "explainability", "all_models", "all", "all", "shap_deferred_not_justified", "No representative model exists and SMART feature semantics are limited."),
        ]
    )
    if not error_structure_summary.empty:
        rows.append(
            _boundary_row(
                config,
                "error_structure",
                "all_models",
                "all",
                "all",
                "descriptive_summary_only",
                "False-positive and false-negative summaries do not establish root cause.",
            )
        )
    return pd.DataFrame(rows)


def build_claim_boundary(
    eligibility: pd.DataFrame,
    config: ReliabilityTrustConfig,
) -> pd.DataFrame:
    """Build allowed/prohibited/conditional claim boundary table."""
    rows = [
        _claim(config, "retrospective offline failure-risk ranking", "allowed", "Asset/time-aware compact metrics exist; no deployment claim follows."),
        _claim(config, "asset/time-aware validation framework demonstration", "allowed", "Asset-disjoint, time-aware, and combined validation outputs are available."),
        _claim(config, "top-risk concentration as diagnostic screening signal", "conditional", "Combined top-risk rows show concentration but include substantial false-positive burden and repeated-origin dependence."),
        _claim(config, "candidate for further validation", "conditional", "Some v1.5.4 model-status rows show signal, but trust closeout does not select a representative model."),
        _claim(config, "production-ready failure prediction", "prohibited", "No production_ready state exists and no representative model is selected."),
        _claim(config, "calibrated 7-day failure probability", "prohibited", "No calibration model, independent calibration period, or operational probability validation is used."),
        _claim(config, "84.6 percent prediction success", "prohibited", "Top-risk failed-asset capture is not accuracy and is affected by repeated daily origins."),
        _claim(config, "maintenance recommendation or replacement automation", "prohibited", "No intervention effect, cost model, or prospective deployment evidence exists."),
        _claim(config, "survival probability or RUL estimate", "prohibited", "Survival and RUL modeling are deferred/not ready."),
        _claim(config, "root-cause discovery from SMART features", "prohibited", "Feature importance/SHAP is not run and SMART semantics are not causal evidence."),
        _claim(config, "generalization beyond Backblaze 2013", "prohibited", "No external year, company, fleet, or drive-population holdout is validated."),
    ]
    return pd.DataFrame(rows)


def build_trust_summary(
    *,
    eligibility: pd.DataFrame,
    validation_stability: pd.DataFrame,
    weighting_dependency: pd.DataFrame,
    operational_boundary: pd.DataFrame,
    split_diagnostics: pd.DataFrame,
    classification_conclusion: pd.DataFrame,
    full_readiness_summary: pd.DataFrame,
    event_integrity_summary: pd.DataFrame,
    censoring_summary: pd.DataFrame,
    config: ReliabilityTrustConfig,
) -> pd.DataFrame:
    """Build compact key-value trust summary."""
    best_primary = _max(eligibility, "primary_median_pr_auc")
    best_combined = _max(eligibility, "combined_pr_auc")
    selected = bool(eligibility["representative_model_selected"].astype(bool).any())
    combined_top = operational_boundary[
        operational_boundary["boundary_type"].eq("combined_top_1_percent_ranking")
    ]
    reference_top = _reference_combined_top_1(combined_top)
    event = event_integrity_summary.iloc[0] if not event_integrity_summary.empty else pd.Series()
    readiness = full_readiness_summary.iloc[0] if not full_readiness_summary.empty else pd.Series()
    post_failure_assets = _value(event, "failure_followed_by_later_observation_asset_count")
    missing_history_assets = _value(event, "failure_asset_missing_previous_history_count")
    rows = [
        ("audit_verdict", "passed", "All required v1.5.4 compact artifacts were available and parsed."),
        ("row_prevalence_baseline", _fmt(config.row_prevalence), f"{config.positive_rows}/{config.eligible_origins} positive 7-day labels."),
        ("positive_asset_prevalence", _fmt(config.positive_asset_prevalence), f"{config.positive_assets}/{config.total_assets} assets have positive labels."),
        ("best_primary_median_pr_auc", _fmt(best_primary), "Best median over asset-disjoint, time-aware, and combined primary splits."),
        ("best_combined_pr_auc", _fmt(best_combined), "Combined asset/time validation is the strictest evidence."),
        ("representative_model_selected", str(selected).lower(), "No model is promoted to representative status."),
        ("representative_model", "none", "Resource-limited training, repeated origins, threshold burden, and external-validation gaps block selection."),
        ("v1_5_4_model_status_counts", _status_counts(eligibility, "input_model_status"), "Input v1.5.4 statuses are preserved separately from trust eligibility."),
        ("v1_5_5_eligibility_status_counts", _status_counts(eligibility, "eligibility_status"), "Trust closeout applies stricter representative-model gates."),
        ("random_reference_boundary", _random_boundary(validation_stability), "Random row split is optimistic reference only."),
        ("weighting_boundary", _weighting_boundary(weighting_dependency), "Raw-row gains can reflect repeated-origin and long-lived-asset dominance."),
        ("resource_boundary", "all_non_dummy_models_resource_limited", "Non-dummy models use deterministic training-only subsampling; test sets are not subsampled."),
        ("combined_top_1_reference_model", _top_reference_label(reference_top), "Reference top-risk row is fixed for interpretation and is not a representative model selection."),
        ("combined_top_1_precision", _fmt(_value(reference_top, "precision")), "Precision is not calibrated failure probability."),
        ("combined_top_1_lift", _fmt(_value(reference_top, "lift")), "Lift must be read with absolute precision and false-positive burden."),
        ("combined_top_1_failed_asset_capture", _fmt(_value(reference_top, "failed_asset_capture")), "Capture rate is retrospective ranking concentration, not prediction accuracy."),
        ("threshold_boundary", "ranking_only_not_operational_threshold", "0.5 threshold rows are diagnostic and not tuned with test labels."),
        ("calibration_boundary", "uncalibrated_relative_score_only", "No independent calibration set or calibration model is used."),
        ("event_boundary", f"post_failure_anomalies={post_failure_assets}; no_prior_history_failures={missing_history_assets}", "Event anomalies are retained as limitations, not silently removed from the audit."),
        ("censoring_boundary", _censoring_statuses(censoring_summary), "Non-failure exits may be administrative, retirement, removal, or unknown."),
        ("survival_model_status", "deferred_not_ready", "Operational censoring distribution and exit reasons are unresolved."),
        ("rul_model_status", "deferred_not_ready", "No RUL target is constructed or modeled."),
        ("shap_status", "deferred_not_justified", "No representative model exists and causal/root-cause claims are prohibited."),
        ("overall_readiness", str(_value(readiness, "overall_readiness")), "Case study is complete as trust-boundary demonstration, not production model."),
    ]
    return pd.DataFrame(rows, columns=["field", "value", "evidence"])


def build_closeout_conclusion(
    trust_summary: pd.DataFrame,
    eligibility: pd.DataFrame,
    config: ReliabilityTrustConfig,
) -> pd.DataFrame:
    """Build final closeout conclusion rows."""
    selected = bool(eligibility["representative_model_selected"].astype(bool).any())
    rows = [
        ("v1_5_release_readiness", "release_ready", "Reliability case study is complete as a bounded offline trust-boundary demonstration."),
        ("representative_model", "none_selected", "No model satisfies representative-model criteria."),
        ("model_eligibility", _status_counts(eligibility, "eligibility_status"), "v1.5.5 applies conservative trust-boundary rules to v1.5.4 outputs."),
        ("representative_model_selected", str(selected).lower(), "Production-ready status does not exist."),
        ("allowed_use", "retrospective_offline_ranking_diagnostic", "Use for portfolio demonstration of reliability validation and trust boundaries."),
        ("not_allowed_use", "production_alert_or_maintenance_automation", "No calibrated probability, cost model, intervention evidence, or prospective validation exists."),
        ("future_data_requirements", "multi_year_external_holdout_retirement_reason_maintenance_logs_failure_modes_calibration_period", "Further data structure is more valuable than tuning current baselines."),
        ("recommended_next_phase", "v1_5_release_documentation_or_next_domain_contract", "Do not proceed to SHAP, tuning, survival, or RUL until stronger evidence exists."),
    ]
    return pd.DataFrame(rows, columns=["field", "value", "evidence"])


def validate_no_forbidden_output_content(outputs: dict[str, pd.DataFrame]) -> None:
    """Reject absolute paths, credentials, and raw serial identifiers in tracked outputs."""
    forbidden_patterns = [
        "KAGGLE_KEY=",
        "KAGGLE_USERNAME=",
        "password=",
        "secret=",
        "token=",
        "C:\\",
        "/Users/",
        "/home/",
    ]
    for name, frame in outputs.items():
        text = frame.to_csv(index=False)
        lower = text.lower()
        if "serial_number" in lower:
            raise ValueError(f"Raw serial identifier column leaked into {name}.")
        for pattern in forbidden_patterns:
            if pattern.lower() in lower:
                raise ValueError(f"Forbidden content `{pattern}` found in {name}.")


def _eligibility_rejection_reasons(
    *,
    summary: pd.Series,
    top: pd.Series,
    threshold: dict[str, float],
    config: ReliabilityTrustConfig,
) -> list[str]:
    model_name = str(summary["model_name"])
    if model_name == config.baseline_model_name:
        return ["baseline_model_not_candidate"]
    reasons: list[str] = []
    combined_lift = _num(summary, "combined_pr_auc") - config.row_prevalence
    if combined_lift < config.min_candidate_combined_lift_over_prevalence:
        reasons.append("combined_lift_over_prevalence_too_small")
    if _num(top, "lift_over_prevalence") < config.min_candidate_top_1_lift:
        reasons.append("top_1_lift_too_small")
    if _num(top, "failed_asset_capture_rate") < config.min_candidate_top_1_failed_asset_capture:
        reasons.append("top_1_failed_asset_capture_too_small")
    if "resource_limited" in str(summary["resource_status"]):
        reasons.append("resource_limited_subsampled_training_only")
    if threshold["precision"] < 0.05:
        reasons.append("fixed_threshold_precision_too_low")
    if str(summary["weighting_policy"]) == "raw_row":
        reasons.append("raw_row_weighting_sensitive_to_repeated_origins")
    reasons.append("external_validation_absent")
    reasons.append("calibration_not_established")
    return reasons


def _eligibility_status(
    *,
    model_name: str,
    rejection_reasons: list[str],
    top: pd.Series,
    summary: pd.Series,
    config: ReliabilityTrustConfig,
) -> str:
    if model_name == config.baseline_model_name:
        return "descriptive_only"
    if "resource_limited_subsampled_training_only" in rejection_reasons:
        return "diagnostic_only"
    if not rejection_reasons:
        return "candidate_for_further_validation"
    if _num(summary, "combined_pr_auc") > config.row_prevalence and _num(
        top,
        "lift_over_prevalence",
    ) > 1:
        return "limited_predictive_evidence"
    return "diagnostic_only"


def _sort_combo_rows(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values(["model_name", "feature_set", "weighting_policy"]).reset_index(
        drop=True
    )


def _combo(row: pd.Series) -> dict[str, str]:
    return {
        "model_name": str(row["model_name"]),
        "feature_set": str(row["feature_set"]),
        "weighting_policy": str(row["weighting_policy"]),
    }


def _combo_filter(frame: pd.DataFrame, combo: dict[str, str]) -> pd.DataFrame:
    return frame[
        frame["model_name"].astype(str).eq(combo["model_name"])
        & frame["feature_set"].astype(str).eq(combo["feature_set"])
        & frame["weighting_policy"].astype(str).eq(combo["weighting_policy"])
    ].copy()


def _lookup_combo(frame: pd.DataFrame, combo: dict[str, str]) -> pd.Series:
    subset = _combo_filter(frame, combo)
    return subset.iloc[0] if not subset.empty else pd.Series(dtype=object)


def _lookup_weighting_gap(frame: pd.DataFrame, combo: dict[str, str]) -> str:
    subset = frame[
        frame["model_name"].astype(str).eq(combo["model_name"])
        & frame["feature_set"].astype(str).eq(combo["feature_set"])
    ]
    if subset.empty:
        return "unknown"
    return str(subset.iloc[0]["dependency_status"])


def _summary_row(
    frame: pd.DataFrame,
    model_name: str,
    feature_set: str,
    weighting_policy: str,
) -> pd.DataFrame:
    return frame[
        frame["model_name"].astype(str).eq(model_name)
        & frame["feature_set"].astype(str).eq(feature_set)
        & frame["weighting_policy"].astype(str).eq(weighting_policy)
    ]


def _combined_top_risk(
    frame: pd.DataFrame,
    combo: dict[str, str],
    fraction: float,
) -> pd.Series:
    subset = _combo_filter(frame, combo)
    subset = subset[
        subset["split_id"].astype(str).eq(COMBINED_SPLIT_ID)
        & np.isclose(pd.to_numeric(subset["top_fraction"], errors="coerce"), fraction)
    ]
    return subset.iloc[0] if not subset.empty else pd.Series(dtype=object)


def _combined_top_rows(frame: pd.DataFrame, fraction: float) -> pd.DataFrame:
    return frame[
        frame["split_id"].astype(str).eq(COMBINED_SPLIT_ID)
        & np.isclose(pd.to_numeric(frame["top_fraction"], errors="coerce"), fraction)
    ].copy()


def _combined_threshold_rows(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[
        frame["split_id"].astype(str).eq(COMBINED_SPLIT_ID)
        & np.isclose(pd.to_numeric(frame["threshold"], errors="coerce"), 0.5)
        & frame["status"].astype(str).eq("valid")
    ].copy()


def _top_precision(frame: pd.DataFrame, combo: dict[str, str], fraction: float) -> float:
    top = _combined_top_risk(frame, combo, fraction)
    return _num(top, "precision_at_top_fraction")


def _threshold_primary_median(
    threshold_summary: pd.DataFrame,
    combo: dict[str, str],
) -> dict[str, float]:
    rows = _combo_filter(threshold_summary, combo)
    rows = rows[
        rows["validation_type"].isin(PRIMARY_VALIDATION_TYPES)
        & rows["status"].astype(str).eq("valid")
        & np.isclose(pd.to_numeric(rows["threshold"], errors="coerce"), 0.5)
    ]
    return {
        "precision": _median(rows, "precision"),
        "recall": _median(rows, "recall"),
        "mcc": _median(rows, "mcc"),
    }


def _split_metric(frame: pd.DataFrame, validation_type: str) -> float:
    rows = frame[frame["validation_type"].astype(str).eq(validation_type)]
    return _median(rows, "average_precision")


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").dropna()


def _median(frame: pd.DataFrame, column: str) -> float:
    values = _numeric(frame, column)
    return float(values.median()) if len(values) else np.nan


def _max(frame: pd.DataFrame, column: str) -> float:
    values = _numeric(frame, column)
    return float(values.max()) if len(values) else np.nan


def _iqr(values: pd.Series) -> float:
    return float(values.quantile(0.75) - values.quantile(0.25)) if len(values) else np.nan


def _num(row: pd.Series, column: str) -> float:
    if row.empty or column not in row.index:
        return np.nan
    value = pd.to_numeric(pd.Series([row[column]]), errors="coerce").iloc[0]
    return float(value) if pd.notna(value) else np.nan


def _value(row: pd.Series, column: str) -> Any:
    if row.empty or column not in row.index:
        return "unavailable"
    return row[column]


def _subtract_or_nan(left: float, right: float) -> float:
    if pd.isna(left) or pd.isna(right):
        return np.nan
    return float(left - right)


def _safe_ratio(left: float, right: float) -> float:
    if pd.isna(left) or pd.isna(right) or right == 0:
        return np.nan
    return float(left / right)


def _combine_status(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return "unavailable"
    values = sorted(frame[column].dropna().astype(str).unique())
    return "|".join(values) if values else "unavailable"


def _stability_status(values: pd.Series, random_pr: float, primary_median: float) -> str:
    if values.empty:
        return "not_available"
    if pd.notna(random_pr) and pd.notna(primary_median) and random_pr - primary_median > 0.05:
        return "random_optimistic"
    if _iqr(values) > 0.05:
        return "primary_split_variation"
    return "primary_splits_available"


def _stability_interpretation(values: pd.Series, random_pr: float, primary_median: float) -> str:
    if values.empty:
        return "No valid primary PR-AUC values are available."
    if pd.notna(random_pr) and pd.notna(primary_median) and random_pr - primary_median > 0.05:
        return "Random row split is materially higher than primary validation; same-asset dependence or temporal structure may be optimistic."
    return "Primary validation results are available, but representative-model selection still requires resource and trust-boundary review."


def _weighting_dependency_status(primary_gap: float, combined_gap: float, top_gap: float) -> str:
    gaps = [value for value in [primary_gap, combined_gap, top_gap] if pd.notna(value)]
    if not gaps:
        return "inconclusive"
    if any(value > 0.02 for value in gaps):
        return "raw_row_higher_repeated_origin_risk"
    if any(value < -0.02 for value in gaps):
        return "asset_balanced_higher"
    return "mixed_or_small_gap"


def _threshold_status(row: pd.Series) -> str:
    precision = _num(row, "precision")
    false_positive = _num(row, "false_positive")
    if pd.isna(precision):
        return "insufficient_threshold_evidence"
    if precision < 0.05 or false_positive > 1000:
        return "operationally_unusable"
    return "diagnostic_binary_only"


def _boundary_row(
    config: ReliabilityTrustConfig,
    boundary_type: str,
    model_name: str,
    feature_set: str,
    weighting_policy: str,
    status: str,
    decision: str,
) -> dict[str, Any]:
    return {
        "case_study_version": config.case_study_version,
        "source_artifact": config.source_artifact,
        "source_sha256": config.source_sha256,
        "boundary_type": boundary_type,
        "model_name": model_name,
        "feature_set": feature_set,
        "weighting_policy": weighting_policy,
        "alerted_row_count": np.nan,
        "positive_rows_in_alerted": np.nan,
        "false_positive_row_burden": np.nan,
        "precision": np.nan,
        "recall": np.nan,
        "mcc": np.nan,
        "lift": np.nan,
        "failed_asset_capture": np.nan,
        "status": status,
        "decision": decision,
    }


def _claim(
    config: ReliabilityTrustConfig,
    claim: str,
    status: str,
    evidence: str,
) -> dict[str, Any]:
    return {
        "case_study_version": config.case_study_version,
        "source_artifact": config.source_artifact,
        "source_sha256": config.source_sha256,
        "claim": claim,
        "status": status,
        "evidence": evidence,
    }


def _status_counts(frame: pd.DataFrame, column: str) -> str:
    counts = frame[column].astype(str).value_counts().sort_index()
    return "; ".join(f"{index}={count}" for index, count in counts.items())


def _random_boundary(stability: pd.DataFrame) -> str:
    statuses = set(stability["stability_status"].astype(str))
    if "random_optimistic" in statuses:
        return "random_optimistic_for_some_combinations"
    return "random_reference_not_primary"


def _weighting_boundary(weighting: pd.DataFrame) -> str:
    statuses = set(weighting["dependency_status"].astype(str))
    if "raw_row_higher_repeated_origin_risk" in statuses:
        return "raw_row_dependency_detected"
    return "weighting_effect_mixed_or_small"


def _censoring_statuses(censoring: pd.DataFrame) -> str:
    if censoring.empty:
        return "unavailable"
    pairs = [
        f"{row['censoring_status']}={row['asset_count']}"
        for _, row in censoring.iterrows()
        if "censoring_status" in row.index and "asset_count" in row.index
    ]
    return "; ".join(pairs)


def _reference_combined_top_1(combined_top: pd.DataFrame) -> pd.Series:
    """Return the predeclared interpretation row for combined top-risk results."""
    preferred = combined_top[
        combined_top["model_name"].astype(str).eq("random_forest")
        & combined_top["feature_set"].astype(str).eq("smart_plus_safe_operational_metadata")
        & combined_top["weighting_policy"].astype(str).eq("asset_balanced")
    ]
    if not preferred.empty:
        return preferred.iloc[0]
    return combined_top.sort_values("lift", ascending=False).iloc[0] if not combined_top.empty else pd.Series(dtype=object)


def _top_reference_label(row: pd.Series) -> str:
    if row.empty:
        return "unavailable"
    return f"{row['model_name']}|{row['feature_set']}|{row['weighting_policy']}"


def _fmt(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(numeric):
        return "nan"
    return f"{numeric:.6g}"
