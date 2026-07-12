from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from features.temporal_asset_features import (  # noqa: E402
    TemporalAssetFeatureConfig,
    build_temporal_asset_feature_table,
    label_failure_within_horizon,
    lookback_window_start,
    write_temporal_asset_feature_dataset_from_csv,
)


def _history() -> pd.DataFrame:
    rows = []
    for day in range(16):
        rows.append(
            {
                "serial_number": "asset_a",
                "observation_date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=day),
                "model": "model_a",
                "capacity_bytes": 1000,
                "failure": int(day == 12),
                "source_order_index": day,
                "observation_number_within_asset": day + 1,
                "days_since_first_observation": day,
                "post_failure_status": "pre_failure_or_no_failure",
                "smart_1_raw": float(day),
                "smart_5_raw": 10.0 + day,
            }
        )
    for day in [0, 2, 9]:
        rows.append(
            {
                "serial_number": "asset_b",
                "observation_date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=day),
                "model": "model_b",
                "capacity_bytes": 2000,
                "failure": 0,
                "source_order_index": 100 + day,
                "observation_number_within_asset": len(rows) + 1,
                "days_since_first_observation": day,
                "post_failure_status": "pre_failure_or_no_failure",
                "smart_1_raw": float(day * 2),
                "smart_5_raw": None if day == 2 else float(day),
            }
        )
    return pd.DataFrame(rows)


def test_7_day_label_excludes_same_day_and_respects_boundary() -> None:
    failure = pd.Timestamp("2020-01-08").date()
    assert label_failure_within_horizon(
        origin=pd.Timestamp("2020-01-01").date(),
        first_failure_date=failure,
        horizon_days=7,
    ) == 1
    assert label_failure_within_horizon(
        origin=pd.Timestamp("2020-01-08").date(),
        first_failure_date=failure,
        horizon_days=7,
    ) == 0
    assert label_failure_within_horizon(
        origin=pd.Timestamp("2019-12-31").date(),
        first_failure_date=failure,
        horizon_days=7,
    ) == 0


def test_lookback_window_is_origin_inclusive_calendar_window() -> None:
    origin = pd.Timestamp("2020-01-10").date()
    assert lookback_window_start(origin, 7) == pd.Timestamp("2020-01-04").date()


def test_feature_table_excludes_right_edge_and_post_failure_rows() -> None:
    config = TemporalAssetFeatureConfig(feature_columns=("smart_1_raw", "smart_5_raw"))
    features = build_temporal_asset_feature_table(_history(), config)

    assert "2020-01-13" not in set(features["prediction_origin"])
    assert "2020-01-16" not in set(features["prediction_origin"])
    assert features["target_failure_within_7d"].sum() > 0
    assert features["eligibility_status"].eq("eligible").all()


def test_feature_table_uses_past_and_current_rows_only() -> None:
    config = TemporalAssetFeatureConfig(feature_columns=("smart_1_raw", "smart_5_raw"))
    features = build_temporal_asset_feature_table(_history(), config)
    row = features[
        (features["serial_number"].eq("asset_a"))
        & (features["prediction_origin"].eq("2020-01-07"))
    ].iloc[0]

    assert row["smart_1_raw__current"] == 6.0
    assert row["smart_1_raw__max_7d"] == 6.0
    assert row["smart_1_raw__min_7d"] == 0.0
    assert row["smart_1_raw__slope_7d"] > 0


def test_streaming_writer_creates_local_feature_dataset(tmp_path: Path) -> None:
    source = tmp_path / "analysis_ready.csv"
    output = tmp_path / "features.csv"
    _history().to_csv(source, index=False)
    config = TemporalAssetFeatureConfig(
        feature_columns=("smart_1_raw", "smart_5_raw"),
        source_sha256="synthetic_sha",
    )

    summary = write_temporal_asset_feature_dataset_from_csv(
        input_path=source,
        output_path=output,
        config=config,
        chunksize=4,
    )
    written = pd.read_csv(output)

    assert summary["row_count"] == len(written)
    assert summary["positive_rows"] == int(written["target_failure_within_7d"].sum())
    assert "serial_number" in written.columns
    assert "asset_id_hash" in written.columns
    assert written["source_sha256"].eq("synthetic_sha").all()
