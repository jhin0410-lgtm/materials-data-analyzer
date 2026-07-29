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
) -> dict[str, Any]:
    result = validation["summary"]
    evaluated_batteries = int(result["evaluated_battery_count"])
    improvement = float(result["ridge_improvement_percent"])
    improved_fraction = (
        float(result["improved_battery_count"] / evaluated_batteries)
        if evaluated_batteries
        else 0.0
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
            "The fixed Ridge model did not consistently improve over persistence "
            "across independent batteries."
        )
    elif not interval_available or not coverage_acceptable:
        evidence_level = "Diagnostic"
        conclusion = (
            "The model improved point predictions, but uncertainty calibration "
            "is not yet adequate for engineering decisions."
        )
    else:
        evidence_level = "Diagnostic"
        conclusion = (
            "Leakage-safe cross-battery improvement and approximate interval "
            "coverage were observed, but external protocol-comparable validation "
            "is still required."
        )

    knee_candidate_count = int(
        trajectory_diagnostics["status"].isin(["candidate", "weak_candidate"]).sum()
    )
    limitations = [
        "No electrochemical degradation mechanism is inferred from statistical features.",
        "The forecast is warm-start cross-battery, not zero-shot lifetime or RUL prediction.",
        "External protocol-comparable validation is not provided by this workflow.",
        "Knee points are algorithm- and parameter-sensitive candidates, not ground truth events.",
    ]
    if not raw_signal_available:
        limitations.append(
            "Raw voltage/current/temperature trajectories were unavailable; "
            "signal-derived diagnostics were not evaluated."
        )

    return {
        "evidence_level": evidence_level,
        "result": conclusion,
        "strongest_evidence": {
            "battery_disjoint_validation": leakage_safe,
            "evaluated_battery_count": evaluated_batteries,
            "ridge_improvement_percent_vs_persistence": improvement,
            "improved_battery_fraction": improved_fraction,
            "conformal_observed_coverage": coverage,
            "knee_candidate_count": knee_candidate_count,
        },
        "primary_limitation": (
            "No independent protocol-comparable external validation cohort is available."
        ),
        "evidence_that_would_change_the_conclusion": [
            "A parent- and battery-disjoint external cohort with compatible cycling protocol and units.",
            "Raw signal coverage sufficient to test whether physically interpretable features improve held-out batteries.",
            "Stable improvement over persistence across batteries with calibrated prediction intervals.",
        ],
        "suitability": {
            "exploration": True,
            "engineering_decision": False,
            "scientific_claim": False,
            "production_control": False,
        },
        "readiness": _json_safe(readiness),
        "limitations": limitations,
    }
