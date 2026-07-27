"""Tests for the cross-repository characterization feature handoff."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from loaders.characterization_features import (
    integrate_process_and_characterization,
    load_characterization_features,
    pivot_characterization_features,
    run_characterization_handoff,
    validate_characterization_features,
)


def _row(
    sample: str,
    measurement: str,
    instrument: str,
    name: str,
    value: float,
    unit: str,
    *,
    label: str | None = None,
    method: str = "method_v1",
    preprocessing: str = "preprocessing_v1",
    flag: str = "ok",
) -> dict[str, object]:
    return {
        "sample_id": sample,
        "measurement_id": measurement,
        "instrument": instrument,
        "feature_name": name,
        "feature_label": label,
        "value": value,
        "unit": unit,
        "method": method,
        "source_file": None,
        "source_sha256": None,
        "preprocessing_id": preprocessing,
        "quality_flag": flag,
    }


def test_validate_requires_complete_contract() -> None:
    table = pd.DataFrame(
        [_row("s1", "m1", "xrd", "peak_count", 1, "count")]
    ).drop(columns="unit")
    with pytest.raises(ValueError, match="missing required"):
        validate_characterization_features(table)


def test_validate_rejects_nonfinite_value_and_invalid_hash() -> None:
    nonfinite = pd.DataFrame(
        [_row("s1", "m1", "xrd", "peak_count", float("inf"), "count")]
    )
    with pytest.raises(ValueError, match="non-finite"):
        validate_characterization_features(nonfinite)

    invalid_hash = pd.DataFrame(
        [_row("s1", "m1", "xrd", "peak_count", 1, "count")]
    )
    invalid_hash.loc[0, "source_sha256"] = "not-a-sha256"
    with pytest.raises(ValueError, match="source_sha256"):
        validate_characterization_features(invalid_hash)


def test_measurement_id_cannot_cross_sample_or_instrument(
    tmp_path: Path,
) -> None:
    table = pd.DataFrame(
        [
            _row("s1", "m1", "xrd", "peak_count", 1, "count"),
            _row("s2", "m1", "xrd", "mean_fwhm", 2, "deg_2theta"),
        ]
    )
    path = tmp_path / "features.csv"
    table.to_csv(path, index=False)

    with pytest.raises(ValueError, match="measurement_id"):
        load_characterization_features([path])


def test_duplicate_semantic_feature_is_not_aggregated() -> None:
    table = pd.DataFrame(
        [
            _row("s1", "m1", "xrd", "peak_count", 1, "count"),
            _row("s1", "m2", "xrd", "peak_count", 2, "count"),
        ]
    )
    with pytest.raises(ValueError, match="predeclare an aggregation"):
        pivot_characterization_features(table)


def test_mixed_method_or_preprocessing_is_rejected() -> None:
    mixed_method = pd.DataFrame(
        [
            _row(
                "s1",
                "m1",
                "xrd",
                "peak_count",
                1,
                "count",
                method="method_a",
            ),
            _row(
                "s2",
                "m2",
                "xrd",
                "peak_count",
                2,
                "count",
                method="method_b",
            ),
        ]
    )
    with pytest.raises(ValueError, match="mixed method"):
        pivot_characterization_features(mixed_method)

    mixed_preprocessing = pd.DataFrame(
        [
            _row(
                "s1",
                "m1",
                "xrd",
                "peak_count",
                1,
                "count",
                preprocessing="preprocessing_a",
            ),
            _row(
                "s2",
                "m2",
                "xrd",
                "peak_count",
                2,
                "count",
                preprocessing="preprocessing_b",
            ),
        ]
    )
    with pytest.raises(ValueError, match="mixed preprocessing"):
        pivot_characterization_features(mixed_preprocessing)


def test_join_uses_sample_id_not_row_order() -> None:
    process = pd.DataFrame(
        {
            "sample_id": ["s2", "s1", "s3"],
            "temperature_c": [200, 100, 300],
        }
    )
    wide = pd.DataFrame(
        {
            "sample_id": ["s1", "s2", "s4"],
            "char__xrd__peak_count__count": [10, 20, 40],
        }
    )

    integrated, audit = integrate_process_and_characterization(process, wide)
    indexed = integrated.set_index("sample_id")
    assert indexed.loc["s1", "temperature_c"] == 100
    assert indexed.loc["s1", "char__xrd__peak_count__count"] == 10
    statuses = dict(
        audit[["sample_id", "join_status"]].itertuples(
            index=False, name=None
        )
    )
    assert statuses == {
        "s1": "matched",
        "s2": "matched",
        "s3": "process_only",
        "s4": "characterization_only",
    }


def test_end_to_end_outputs_are_deterministic(tmp_path: Path) -> None:
    features = pd.DataFrame(
        [
            _row("s2", "s2-xrd", "xrd", "peak_count", 2, "count"),
            _row("s1", "s1-xrd", "xrd", "peak_count", 1, "count"),
            _row(
                "s1",
                "s1-eds",
                "eds",
                "element_weight_percent",
                20,
                "percent",
                label="Fe",
                flag="review_required",
            ),
            _row(
                "s2",
                "s2-eds",
                "eds",
                "element_weight_percent",
                30,
                "percent",
                label="Fe",
                flag="review_required",
            ),
        ]
    )
    feature_path = tmp_path / "features.csv"
    features.to_csv(feature_path, index=False)

    process = pd.DataFrame(
        {
            "sample_id": ["s2", "s1", "s3"],
            "process_temperature_c": [700, 650, 725],
        }
    )
    process_path = tmp_path / "process.csv"
    process.to_csv(process_path, index=False)

    outputs_a = run_characterization_handoff(
        [feature_path], tmp_path / "out_a", process_table_path=process_path
    )
    outputs_b = run_characterization_handoff(
        [feature_path], tmp_path / "out_b", process_table_path=process_path
    )

    assert (
        outputs_a["wide_features"].read_text(encoding="utf-8")
        == outputs_b["wide_features"].read_text(encoding="utf-8")
    )
    assert (
        outputs_a["integrated_table"].read_text(encoding="utf-8")
        == outputs_b["integrated_table"].read_text(encoding="utf-8")
    )

    manifest = json.loads(outputs_a["manifest"].read_text(encoding="utf-8"))
    assert manifest["counts"]["sample_count"] == 2
    assert manifest["join_summary"] == {
        "matched": 2,
        "process_only": 1,
        "characterization_only": 0,
    }
    assert manifest["scientific_boundary"]["row_order_join_used"] is False
    assert (
        manifest["scientific_boundary"]["scientific_validation"]
        == "not_established_by_handoff"
    )


def test_cli_runs_tracked_synthetic_example(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_characterization_handoff.py",
            "--characterization",
            "data/sample/synthetic_characterization_features_long.csv",
            "--process-table",
            "data/sample/synthetic_process_characterization_samples.csv",
            "--output",
            str(tmp_path / "handoff"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Characterization handoff completed." in completed.stdout
    integrated = pd.read_csv(tmp_path / "handoff" / "integrated_sample_table.csv")
    assert integrated["sample_id"].tolist() == [
        "sample_001",
        "sample_002",
        "sample_003",
    ]
