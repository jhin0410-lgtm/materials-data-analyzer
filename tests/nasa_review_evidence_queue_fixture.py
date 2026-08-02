from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_nasa_pcoe_review_evidence.ps1"


def _queue() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "battery_id": "A",
                "review_order": 1,
                "review_tier": 2,
                "review_tier_label": "source_quality_plus_error_influence",
                "review_dimensions": "source_quality;error_influence;rated_reference_context",
                "is_evaluated": True,
                "prediction_count": 2,
                "reference_start_context_flag": True,
                "reference_context_only": False,
                "source_quality_issue": True,
                "trajectory_continuity_issue": False,
                "evaluation_coverage_issue": False,
                "structural_or_coverage_issue": True,
                "disproportionate_error_influence": True,
                "context_reasons": "first_target_not_near_rated_capacity",
                "structural_review_reasons": "invalid_capacity_quarantine",
                "influence_review_reasons": "disproportionate_error_influence",
                "persistence_mae": 1.5,
                "ridge_mae": 2.5,
                "ridge_minus_persistence_mae": 1.0,
                "excluded_discharge_operation_count": 1,
                "invalid_capacity_operation_count": 1,
                "cycle_gap_count": 0,
                "maximum_absolute_adjacent_target_change_percent": 5.0,
                "ambient_temperature_median_c": 25.0,
                "imported_discharge_operation_count": 4,
            },
            {
                "battery_id": "B",
                "review_order": 2,
                "review_tier": 1,
                "review_tier_label": "evaluation_coverage",
                "review_dimensions": "evaluation_coverage;rated_reference_context",
                "is_evaluated": False,
                "prediction_count": 0,
                "reference_start_context_flag": True,
                "reference_context_only": False,
                "source_quality_issue": False,
                "trajectory_continuity_issue": False,
                "evaluation_coverage_issue": True,
                "structural_or_coverage_issue": True,
                "disproportionate_error_influence": False,
                "context_reasons": "first_target_not_near_rated_capacity",
                "structural_review_reasons": "no_exact_horizon_forecast_rows",
                "influence_review_reasons": "",
                "persistence_mae": None,
                "ridge_mae": None,
                "ridge_minus_persistence_mae": None,
                "excluded_discharge_operation_count": 0,
                "invalid_capacity_operation_count": 0,
                "cycle_gap_count": 0,
                "maximum_absolute_adjacent_target_change_percent": 2.0,
                "ambient_temperature_median_c": 4.0,
                "imported_discharge_operation_count": 3,
            },
        ]
    )
