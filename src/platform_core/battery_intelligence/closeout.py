"""Scientific evidence closeout for battery intelligence runs."""
from __future__ import annotations

import math
from typing import Any, Mapping

import pandas as pd

from .common import _json_safe


def scientific_closeout(
    *,
    readiness: Mapping[str, Any],
    trajectory_diagnostics: pd.DataFrame,
    validation: Mapping[str, Any],
    raw_signal_available: bool,
    error_diagnostics: Mapping[str, Any] | None = None,
    raw_signal_admission: Mapping[str, Any] | None = None,
    signal_feature_comparison: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = validation["summary"]
    evaluated_batteries = int(result["evaluated_battery_count"])
    best_baseline_name = str(result.get("best_baseline_name", "persistence"))
    best_baseline_metrics = result.get(
        "best_baseline_metrics", result["persistence_metrics"]
    )
    improvement = float(
        result.get(
            "ridge_improvement_percent_vs_best_baseline",
            result["ridge_improvement_percent"],
        )
    )
    improved_count = int(
        result.get(
            "improved_vs_best_baseline_battery_count",
            result["improved_battery_count"],
        )
    )
    improved_fraction = (
        float(improved_count / evaluated_batteries) if evaluated_batteries else 0.0
    )
    leakage_safe = result["train_test_group_overlap_count"] == 0
    interval_available = result["interval_prediction_count"] > 0
    coverage = result["conformal_observed_coverage"]
    coverage_acceptable = (
        math.isfinite(float(coverage))
        and float(coverage) >= float(result["conformal_target_coverage"]) - 0.05
    )

    if not leakage_safe:
        evidence_level = "Unsupported"
        conclusion = (
            "Validation contains battery-identity leakage and cannot support "
            "a predictive result."
        )
    elif evaluated_batteries < 5:
        evidence_level = "Inconclusive"
        conclusion = (
            "Too few independent batteries were available for a defensible "
            "generalization assessment."
        )
    elif improvement <= 0 or improved_fraction <= 0.5:
        evidence_level = "Unsupported"
        conclusion = (
            f"The fixed Ridge model did not consistently improve over the strongest "
            f"origin-only baseline ({best_baseline_name}) across independent batteries."
        )
    elif not interval_available or not coverage_acceptable:
        evidence_level = "Diagnostic"
        conclusion = (
            "Ridge improved point predictions over the strongest origin-only baseline, "
            "but uncertainty calibration is not adequate for engineering decisions."
        )
    else:
        evidence_level = "Diagnostic"
        conclusion = (
            "Leakage-safe cross-battery improvement over the strongest origin-only "
            "baseline and approximate interval coverage were observed, but external "
            "protocol-comparable validation is still required."
        )

    status = trajectory_diagnostics["status"]
    knee_candidate_count = int((status == "candidate").sum())
    weak_knee_candidate_count = int((status == "weak_candidate").sum())
    knee_uncertainty_available_count = int(
        trajectory_diagnostics["knee_ci_low"].notna().sum()
    )

    raw_admitted = bool(
        raw_signal_admission
        and raw_signal_admission.get("admitted_for_predictive_comparison")
    )
    if not raw_signal_available:
        raw_signal_status = "Inconclusive"
        raw_signal_value_status = "Inconclusive"
    elif not raw_admitted:
        raw_signal_status = "Unsupported"
        raw_signal_value_status = "Inconclusive"
    else:
        raw_signal_status = "Supported"
        if signal_feature_comparison is None:
            raw_signal_value_status = "Inconclusive"
        elif float(signal_feature_comparison.get("improvement_percent", 0.0)) > 0:
            raw_signal_value_status = "Diagnostic"
        else:
            raw_signal_value_status = "Unsupported"

    component_statuses = {
        "runtime_execution": {
            "status": "Supported",
            "scope": "The workflow completed and generated the declared artifacts.",
        },
        "input_contract_validation": {
            "status": "Supported",
            "scope": "Required identities, cycle ordering, numeric values, and duplicates were checked.",
        },
        "battery_disjoint_leakage_control": {
            "status": "Supported" if leakage_safe else "Unsupported",
            "scope": "Battery identities were held out as complete validation groups.",
        },
        "trajectory_and_knee_diagnostics": {
            "status": "Diagnostic",
            "scope": "Detected changes are algorithmic candidates, not physical mechanisms.",
        },
        "uncertainty_estimation": {
            "status": "Diagnostic" if interval_available else "Inconclusive",
            "scope": "Nested grouped residual intervals describe same-source forecast error only.",
        },
        "ridge_predictive_hypothesis": {
            "status": evidence_level,
            "scope": f"Ridge versus strongest origin-only baseline: {best_baseline_name}.",
        },
        "raw_signal_provenance_admission": {
            "status": raw_signal_status,
            "scope": "Checksum, units, source metadata, and battery-cycle mapping admission.",
        },
        "raw_signal_predictive_value": {
            "status": raw_signal_value_status,
            "scope": "Incremental value of admitted signal-derived features on held-out batteries.",
        },
        "external_generalization": {
            "status": "Inconclusive",
            "scope": "No independent protocol-comparable external cohort was evaluated.",
        },
        "engineering_decision_readiness": {
            "status": "Not ready",
            "scope": "Results are not validated for engineering decisions or production control.",
        },
    }

    limitations = [
        "No electrochemical degradation mechanism is inferred from statistical features.",
        "The forecast is warm-start cross-battery, not zero-shot lifetime or RUL prediction.",
        "External protocol-comparable validation is not provided by this workflow.",
        "Knee points are algorithm- and parameter-sensitive candidates, not ground truth events.",
        "Lifecycle and knee-phase error strata are post-hoc diagnostics and are not forecast inputs.",
    ]
    if not raw_signal_available:
        limitations.append(
            "Raw voltage/current/temperature trajectories were unavailable; "
            "signal-derived diagnostics were not evaluated."
        )
    elif not raw_admitted:
        limitations.append(
            "Raw signals were not admitted for predictive comparison because the "
            "provenance, checksum, unit, identity, or coverage contract was incomplete."
        )

    primary_limitation = (
        "The available cycle-summary features do not establish improvement over the "
        f"strongest origin-only baseline ({best_baseline_name}), and no independent "
        "protocol-comparable external cohort is available."
    )
    return {
        "primary_claim": "ridge_exact_horizon_cross_battery_prediction",
        "evidence_level": evidence_level,
        "result": conclusion,
        "component_statuses": component_statuses,
        "strongest_evidence": {
            "battery_disjoint_validation": leakage_safe,
            "evaluated_battery_count": evaluated_batteries,
            "best_baseline_name": best_baseline_name,
            "best_baseline_mae": float(best_baseline_metrics["mae"]),
            "ridge_mae": float(result["ridge_metrics"]["mae"]),
            "ridge_improvement_percent_vs_best_baseline": improvement,
            "improved_vs_best_baseline_battery_fraction": improved_fraction,
            "conformal_observed_coverage": coverage,
            "knee_candidate_count": knee_candidate_count,
            "weak_knee_candidate_count": weak_knee_candidate_count,
            "knee_uncertainty_available_count": knee_uncertainty_available_count,
            "error_diagnostics": _json_safe(error_diagnostics),
        },
        "primary_limitation": primary_limitation,
        "evidence_that_would_change_the_conclusion": [
            "Stable improvement over every predeclared origin-only baseline across held-out batteries.",
            "Admitted raw-signal coverage sufficient to test whether physical signal features add predictive value.",
            "A parent- and battery-disjoint external cohort with compatible cycling protocol and units.",
            "Prediction intervals with stable coverage across batteries, regimes, and external data.",
        ],
        "suitability": {
            "exploration": True,
            "engineering_decision": False,
            "scientific_claim": False,
            "production_control": False,
        },
        "readiness": _json_safe(readiness),
        "raw_signal_admission": _json_safe(raw_signal_admission),
        "signal_feature_comparison": _json_safe(signal_feature_comparison),
        "limitations": limitations,
    }
