from __future__ import annotations

import pandas as pd

from nasa_review_evidence_queue_fixture import _queue


def _predictions() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "battery_id": "A",
                "actual": 90.0,
                "persistence_prediction": 91.0,
                "ridge_prediction": 92.0,
            },
            {
                "battery_id": "A",
                "actual": 80.0,
                "persistence_prediction": 82.0,
                "ridge_prediction": 83.0,
            },
        ]
    )


def _excluded() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_location": "archive.zip!A.mat",
                "battery_id": "A",
                "source_operation_index": 5,
                "cycle_index": 3,
                "capacity_issue": "nonpositive",
                "observed_value": "nonpositive:0.0",
                "severity": "warning",
                "code": "invalid_discharge_capacity_excluded",
                "message": "No value was imputed.",
            }
        ]
    )


def _protocol() -> pd.DataFrame:
    return _queue()[["battery_id", "ambient_temperature_median_c"]].copy()


def _inventory() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "battery_id": "A",
                "skip_reason": "",
                "imported_discharge_operation_count": 4,
                "excluded_discharge_operation_count": 1,
                "invalid_capacity_operation_count": 1,
            },
            {
                "battery_id": "B",
                "skip_reason": "",
                "imported_discharge_operation_count": 3,
                "excluded_discharge_operation_count": 0,
                "invalid_capacity_operation_count": 0,
            },
            {
                "battery_id": "A",
                "skip_reason": "duplicate_identical_source_copy",
                "imported_discharge_operation_count": 4,
                "excluded_discharge_operation_count": 1,
                "invalid_capacity_operation_count": 1,
            },
        ]
    )
