"""Regression tests for unlabeled characterization feature keys."""
from __future__ import annotations

import numpy as np
import pandas as pd

from loaders.characterization_features import feature_key, pivot_characterization_features


def _row(label: object) -> dict[str, object]:
    return {
        "sample_id": "sample_001",
        "measurement_id": "sample_001-xrd",
        "instrument": "xrd",
        "feature_name": "detected_peak_count",
        "feature_label": label,
        "value": 5.0,
        "unit": "count",
        "method": "scipy_find_peaks",
        "source_file": None,
        "source_sha256": None,
        "preprocessing_id": "xrd-preprocessing-v1",
        "quality_flag": "ok",
    }


def test_feature_key_omits_missing_label_values() -> None:
    expected = "char__xrd__detected_peak_count__count"
    assert feature_key("xrd", "detected_peak_count", None, "count") == expected
    assert feature_key("xrd", "detected_peak_count", np.nan, "count") == expected
    assert feature_key("xrd", "detected_peak_count", pd.NA, "count") == expected


def test_pivot_does_not_emit_nan_label_segment() -> None:
    wide = pivot_characterization_features(pd.DataFrame([_row(None)]))

    assert wide.columns.tolist() == [
        "sample_id",
        "char__xrd__detected_peak_count__count",
    ]
    assert not any("__nan__" in column for column in wide.columns)
